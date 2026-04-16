package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"axiom/backend/internal/auth"
	"axiom/backend/internal/models"
	"axiom/backend/internal/orchestrator"
)

type Service interface {
	Signup(ctx context.Context, email, password, plan string) (orchestrator.AuthResponse, error)
	Login(ctx context.Context, email, password string) (orchestrator.AuthResponse, error)
	CurrentUser(token string) (orchestrator.AuthResponse, error)
	UserFromToken(token string) (*models.User, error)
	CreateSession(ctx context.Context, userID string) (*models.Session, error)
	Chat(ctx context.Context, sessionID, prompt string) (orchestrator.ChatResponse, error)
	GetMetrics(sessionID string) (models.SessionMetrics, error)
	GetSession(sessionID string) (*models.Session, error)
	ListUserSessions(userID string) ([]orchestrator.SessionSummary, error)
	UserOwnsSession(userID, sessionID string) (bool, error)
}

type Handler struct {
	service Service
}

type createSessionResponse struct {
	SessionID string `json:"session_id"`
}

type createSessionRequest struct {
	UserID string `json:"user_id"`
}

type chatRequest struct {
	SessionID string `json:"session_id"`
	Prompt    string `json:"prompt"`
}

type authRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	Plan     string `json:"plan,omitempty"`
}

func NewHandler(service Service) *Handler {
	return &Handler{service: service}
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	h.registerRoutes(mux, "")
	h.registerRoutes(mux, "/api")
	return withCORS(mux)
}

func (h *Handler) registerRoutes(mux *http.ServeMux, prefix string) {
	mux.HandleFunc(prefix+"/health", h.handleHealth)
	mux.HandleFunc(prefix+"/auth/signup", h.handleSignup)
	mux.HandleFunc(prefix+"/auth/login", h.handleLogin)
	mux.HandleFunc(prefix+"/auth/me", h.handleMe)
	mux.HandleFunc(prefix+"/session", h.handleSession)
	mux.HandleFunc(prefix+"/sessions/", h.handleSessionByID)
	mux.HandleFunc(prefix+"/chat", h.handleChat)
	mux.HandleFunc(prefix+"/metrics/", h.handleMetrics)
	mux.HandleFunc(prefix+"/users/", h.handleUsers)
}

func (h *Handler) handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodGet {
		methodNotAllowed(w)
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (h *Handler) handleSignup(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodPost {
		methodNotAllowed(w)
		return
	}

	var payload authRequest
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		writeError(w, http.StatusBadRequest, errors.New("invalid json body"))
		return
	}

	response, err := h.service.Signup(r.Context(), payload.Email, payload.Password, payload.Plan)
	if err != nil {
		switch {
		case orchestrator.IsUserExists(err):
			writeError(w, http.StatusConflict, err)
		case strings.Contains(err.Error(), "password"):
			writeError(w, http.StatusBadRequest, err)
		default:
			writeError(w, http.StatusBadGateway, err)
		}
		return
	}

	writeJSON(w, http.StatusCreated, response)
}

func (h *Handler) handleLogin(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodPost {
		methodNotAllowed(w)
		return
	}

	var payload authRequest
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		writeError(w, http.StatusBadRequest, errors.New("invalid json body"))
		return
	}

	response, err := h.service.Login(r.Context(), payload.Email, payload.Password)
	if err != nil {
		if orchestrator.IsInvalidCredentials(err) {
			writeError(w, http.StatusUnauthorized, err)
			return
		}
		writeError(w, http.StatusBadGateway, err)
		return
	}

	writeJSON(w, http.StatusOK, response)
}

func (h *Handler) handleMe(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodGet {
		methodNotAllowed(w)
		return
	}

	token, err := auth.ExtractBearer(r.Header.Get("Authorization"))
	if err != nil {
		writeError(w, http.StatusUnauthorized, err)
		return
	}

	response, err := h.service.CurrentUser(token)
	if err != nil {
		if orchestrator.IsUnauthorized(err) {
			writeError(w, http.StatusUnauthorized, err)
			return
		}
		writeError(w, http.StatusBadGateway, err)
		return
	}

	writeJSON(w, http.StatusOK, response)
}

func (h *Handler) handleSession(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodPost {
		methodNotAllowed(w)
		return
	}

	var payload createSessionRequest
	if r.ContentLength > 0 {
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			writeError(w, http.StatusBadRequest, errors.New("invalid json body"))
			return
		}
	}

	authUser, _ := h.optionalUser(r)
	if authUser != nil {
		payload.UserID = authUser.ID
	}

	session, err := h.service.CreateSession(r.Context(), payload.UserID)
	if err != nil {
		writeError(w, http.StatusBadGateway, err)
		return
	}

	writeJSON(w, http.StatusCreated, createSessionResponse{SessionID: session.ID})
}

func (h *Handler) handleSessionByID(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodGet {
		methodNotAllowed(w)
		return
	}

	path := r.URL.Path
	sessionID := strings.TrimPrefix(path, "/sessions/")
	if strings.HasPrefix(path, "/api/sessions/") {
		sessionID = strings.TrimPrefix(path, "/api/sessions/")
	}
	if sessionID == "" || strings.Contains(sessionID, "/") {
		writeError(w, http.StatusBadRequest, errors.New("session_id is required"))
		return
	}

	if authUser, err := h.optionalUser(r); err != nil {
		writeError(w, http.StatusUnauthorized, err)
		return
	} else if authUser != nil {
		owned, ownErr := h.service.UserOwnsSession(authUser.ID, sessionID)
		if ownErr != nil {
			if orchestrator.IsSessionNotFound(ownErr) {
				writeError(w, http.StatusNotFound, ownErr)
				return
			}
			writeError(w, http.StatusInternalServerError, ownErr)
			return
		}
		if !owned {
			writeError(w, http.StatusForbidden, errors.New("forbidden"))
			return
		}
	}

	current, err := h.service.GetSession(sessionID)
	if err != nil {
		if orchestrator.IsSessionNotFound(err) {
			writeError(w, http.StatusNotFound, err)
			return
		}
		writeError(w, http.StatusInternalServerError, err)
		return
	}

	writeJSON(w, http.StatusOK, current)
}

func (h *Handler) handleChat(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodPost {
		methodNotAllowed(w)
		return
	}

	var payload chatRequest
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		writeError(w, http.StatusBadRequest, errors.New("invalid json body"))
		return
	}

	if authUser, err := h.optionalUser(r); err != nil {
		writeError(w, http.StatusUnauthorized, err)
		return
	} else if authUser != nil {
		owned, ownErr := h.service.UserOwnsSession(authUser.ID, payload.SessionID)
		if ownErr != nil {
			if orchestrator.IsSessionNotFound(ownErr) {
				writeError(w, http.StatusNotFound, ownErr)
				return
			}
			writeError(w, http.StatusInternalServerError, ownErr)
			return
		}
		if !owned {
			writeError(w, http.StatusForbidden, errors.New("forbidden"))
			return
		}
	}

	response, err := h.service.Chat(r.Context(), payload.SessionID, payload.Prompt)
	if err != nil {
		switch {
		case orchestrator.IsSessionNotFound(err):
			writeError(w, http.StatusNotFound, err)
		case strings.Contains(err.Error(), "prompt is required"):
			writeError(w, http.StatusBadRequest, err)
		default:
			writeError(w, http.StatusBadGateway, err)
		}
		return
	}

	writeJSON(w, http.StatusOK, response)
}

func (h *Handler) handleMetrics(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodGet {
		methodNotAllowed(w)
		return
	}

	path := r.URL.Path
	sessionID := strings.TrimPrefix(path, "/metrics/")
	if strings.HasPrefix(path, "/api/metrics/") {
		sessionID = strings.TrimPrefix(path, "/api/metrics/")
	}
	if sessionID == "" || strings.Contains(sessionID, "/") {
		writeError(w, http.StatusBadRequest, errors.New("session_id is required"))
		return
	}

	if authUser, err := h.optionalUser(r); err != nil {
		writeError(w, http.StatusUnauthorized, err)
		return
	} else if authUser != nil {
		owned, ownErr := h.service.UserOwnsSession(authUser.ID, sessionID)
		if ownErr != nil {
			if orchestrator.IsSessionNotFound(ownErr) {
				writeError(w, http.StatusNotFound, ownErr)
				return
			}
			writeError(w, http.StatusInternalServerError, ownErr)
			return
		}
		if !owned {
			writeError(w, http.StatusForbidden, errors.New("forbidden"))
			return
		}
	}

	metrics, err := h.service.GetMetrics(sessionID)
	if err != nil {
		if orchestrator.IsSessionNotFound(err) {
			writeError(w, http.StatusNotFound, err)
			return
		}
		writeError(w, http.StatusInternalServerError, err)
		return
	}

	writeJSON(w, http.StatusOK, metrics)
}

func (h *Handler) handleUsers(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodGet {
		methodNotAllowed(w)
		return
	}

	path := strings.TrimPrefix(r.URL.Path, "/users/")
	if strings.HasPrefix(r.URL.Path, "/api/users/") {
		path = strings.TrimPrefix(r.URL.Path, "/api/users/")
	}
	parts := strings.Split(path, "/")
	if len(parts) != 2 || parts[0] == "" || parts[1] != "sessions" {
		writeError(w, http.StatusNotFound, errors.New("route not found"))
		return
	}

	if authUser, err := h.optionalUser(r); err != nil {
		writeError(w, http.StatusUnauthorized, err)
		return
	} else if authUser != nil && authUser.ID != parts[0] {
		writeError(w, http.StatusForbidden, errors.New("forbidden"))
		return
	}

	sessions, err := h.service.ListUserSessions(parts[0])
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}

	writeJSON(w, http.StatusOK, sessions)
}

func methodNotAllowed(w http.ResponseWriter) {
	writeError(w, http.StatusMethodNotAllowed, errors.New("method not allowed"))
}

func writeError(w http.ResponseWriter, status int, err error) {
	writeJSON(w, status, map[string]string{"error": err.Error()})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func withCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}

		next.ServeHTTP(w, r)
	})
}

func (h *Handler) optionalUser(r *http.Request) (*models.User, error) {
	header := strings.TrimSpace(r.Header.Get("Authorization"))
	if header == "" {
		return nil, nil
	}

	token, err := auth.ExtractBearer(header)
	if err != nil {
		return nil, err
	}

	user, err := h.service.UserFromToken(token)
	if err != nil {
		return nil, err
	}

	return user, nil
}
