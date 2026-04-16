package httpapi

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"axiom/backend/internal/config"
	"axiom/backend/internal/models"
	"axiom/backend/internal/orchestrator"
)

type mockService struct {
	usersByToken map[string]*models.User
}

func (m *mockService) Signup(context.Context, string, string, string) (orchestrator.AuthResponse, error) {
	return orchestrator.AuthResponse{}, nil
}

func (m *mockService) Login(context.Context, string, string) (orchestrator.AuthResponse, error) {
	return orchestrator.AuthResponse{}, nil
}

func (m *mockService) CurrentUser(string) (orchestrator.AuthResponse, error) {
	return orchestrator.AuthResponse{}, nil
}

func (m *mockService) UserFromToken(token string) (*models.User, error) {
	if user, ok := m.usersByToken[token]; ok {
		return user, nil
	}
	return nil, nil
}

func (m *mockService) CreateSession(context.Context, string) (*models.Session, error) {
	return &models.Session{ID: "session-1"}, nil
}

func (m *mockService) Chat(context.Context, string, string) (orchestrator.ChatResponse, error) {
	return orchestrator.ChatResponse{}, nil
}

func (m *mockService) GetMetrics(string) (models.SessionMetrics, error) {
	return models.SessionMetrics{}, nil
}

func (m *mockService) GetSession(string) (*models.Session, error) {
	return &models.Session{}, nil
}

func (m *mockService) ListUserSessions(string) ([]orchestrator.SessionSummary, error) {
	return nil, nil
}

func (m *mockService) UserOwnsSession(string, string) (bool, error) {
	return true, nil
}

func TestRateLimitBlocksAfterConfiguredRequests(t *testing.T) {
	handler := NewHandler(&mockService{}, config.Config{
		RateLimitRequests: 2,
		RateLimitWindow:   time.Hour,
	})
	routes := handler.Routes()

	for attempt := 0; attempt < 2; attempt++ {
		request := httptest.NewRequest(http.MethodGet, "/health", nil)
		request.RemoteAddr = "127.0.0.1:1234"
		recorder := httptest.NewRecorder()
		routes.ServeHTTP(recorder, request)

		if recorder.Code != http.StatusOK {
			t.Fatalf("attempt %d expected 200, got %d", attempt+1, recorder.Code)
		}
	}

	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	request.RemoteAddr = "127.0.0.1:1234"
	recorder := httptest.NewRecorder()
	routes.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusTooManyRequests {
		t.Fatalf("expected 429, got %d", recorder.Code)
	}
	if recorder.Header().Get("Retry-After") == "" {
		t.Fatalf("expected Retry-After header")
	}
}

func TestRateLimitTreatsRootAndAPIPathsAsSameEndpoint(t *testing.T) {
	handler := NewHandler(&mockService{}, config.Config{
		RateLimitRequests: 2,
		RateLimitWindow:   time.Hour,
	})
	routes := handler.Routes()

	for _, path := range []string{"/health", "/api/health"} {
		request := httptest.NewRequest(http.MethodGet, path, nil)
		request.RemoteAddr = "127.0.0.1:2234"
		recorder := httptest.NewRecorder()
		routes.ServeHTTP(recorder, request)

		if recorder.Code != http.StatusOK {
			t.Fatalf("path %s expected 200, got %d", path, recorder.Code)
		}
	}

	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	request.RemoteAddr = "127.0.0.1:2234"
	recorder := httptest.NewRecorder()
	routes.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusTooManyRequests {
		t.Fatalf("expected shared bucket to return 429, got %d", recorder.Code)
	}
}

func TestRateLimitUsesAuthenticatedUserBuckets(t *testing.T) {
	handler := NewHandler(&mockService{
		usersByToken: map[string]*models.User{
			"token-a": {ID: "user-a"},
			"token-b": {ID: "user-b"},
		},
	}, config.Config{
		RateLimitRequests: 1,
		RateLimitWindow:   time.Hour,
	})
	routes := handler.Routes()

	requestA := httptest.NewRequest(http.MethodGet, "/health", nil)
	requestA.RemoteAddr = "127.0.0.1:3234"
	requestA.Header.Set("Authorization", "Bearer token-a")
	recorderA := httptest.NewRecorder()
	routes.ServeHTTP(recorderA, requestA)
	if recorderA.Code != http.StatusOK {
		t.Fatalf("expected first authenticated request to pass, got %d", recorderA.Code)
	}

	requestB := httptest.NewRequest(http.MethodGet, "/health", nil)
	requestB.RemoteAddr = "127.0.0.1:3234"
	requestB.Header.Set("Authorization", "Bearer token-b")
	recorderB := httptest.NewRecorder()
	routes.ServeHTTP(recorderB, requestB)
	if recorderB.Code != http.StatusOK {
		t.Fatalf("expected second user to have independent bucket, got %d", recorderB.Code)
	}
}
