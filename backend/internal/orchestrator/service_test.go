package orchestrator

import (
	"context"
	"slices"
	"sync"
	"testing"
	"time"

	"axiom/backend/internal/config"
	"axiom/backend/internal/ml"
	"axiom/backend/internal/models"
	"axiom/backend/internal/session"
)

type fakeStore struct {
	mu       sync.RWMutex
	sessions map[string]*models.Session
}

func newFakeStore() *fakeStore {
	return &fakeStore{sessions: make(map[string]*models.Session)}
}

func (s *fakeStore) Create(userID string) (*models.Session, error) {
	now := time.Now().UTC()
	current := &models.Session{
		ID:        session.NewID(),
		UserID:    userID,
		CreatedAt: now,
		UpdatedAt: now,
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	s.sessions[current.ID] = session.CloneSession(current)
	return session.CloneSession(current), nil
}

func (s *fakeStore) Get(sessionID string) (*models.Session, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	current, ok := s.sessions[sessionID]
	if !ok {
		return nil, session.ErrSessionNotFound
	}

	return session.CloneSession(current), nil
}

func (s *fakeStore) Update(current *models.Session) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, ok := s.sessions[current.ID]; !ok {
		return session.ErrSessionNotFound
	}

	current.UpdatedAt = time.Now().UTC()
	s.sessions[current.ID] = session.CloneSession(current)
	return nil
}

func (s *fakeStore) ListByUser(userID string) ([]*models.Session, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	sessions := make([]*models.Session, 0)
	for _, current := range s.sessions {
		if current.UserID == userID {
			sessions = append(sessions, session.CloneSession(current))
		}
	}

	slices.SortFunc(sessions, func(a, b *models.Session) int {
		switch {
		case a.UpdatedAt.After(b.UpdatedAt):
			return -1
		case a.UpdatedAt.Before(b.UpdatedAt):
			return 1
		default:
			return 0
		}
	})

	return sessions, nil
}

type stubMLClient struct {
	summariseCalls       int
	lastRoute            ml.RouteRequest
	classifyNeedsContext bool
	classifyConfigured   bool
}

func (s *stubMLClient) Health(context.Context) error {
	return nil
}

func (s *stubMLClient) Summarise(_ context.Context, payload ml.SummariseRequest) (ml.SummariseResponse, error) {
	s.summariseCalls++
	return ml.SummariseResponse{
		Summary:     "rolling summary",
		TokensSaved: 12,
		TokenBreakdown: ml.TokenIO{
			InputTokens:  24,
			OutputTokens: 12,
			TotalTokens:  36,
		},
	}, nil
}

func (s *stubMLClient) QueryCache(context.Context, ml.CacheQueryRequest) (ml.CacheQueryResponse, error) {
	return ml.CacheQueryResponse{
		CacheHit:   false,
		CacheLayer: "miss",
		Classified: "GENERIC",
	}, nil
}

func (s *stubMLClient) StoreCache(context.Context, ml.CacheStoreRequest) (ml.CacheStoreResponse, error) {
	return ml.CacheStoreResponse{Status: "ok", Message: "stored", StoredLayer: "global"}, nil
}

func (s *stubMLClient) Classify(context.Context, ml.ClassifyRequest) (ml.ClassifyResponse, error) {
	needsContext := true
	if s.classifyConfigured {
		needsContext = s.classifyNeedsContext
	}
	return ml.ClassifyResponse{NeedsContext: needsContext, Confidence: 0.93, Reason: "test"}, nil
}

func (s *stubMLClient) Route(_ context.Context, payload ml.RouteRequest) (ml.RouteResponse, error) {
	s.lastRoute = payload
	return ml.RouteResponse{
		PromptToSend:    "optimized prompt",
		Tier:            2,
		Reason:          "test",
		OriginalTokens:  20,
		OptimizedTokens: 12,
		TokensSaved:     8,
		TokenBreakdown: ml.RouteTokenBreakdown{
			OptimizePrompt: ml.TokenIO{
				InputTokens:  10,
				OutputTokens: 6,
				TotalTokens:  16,
			},
		},
	}, nil
}

func (s *stubMLClient) Invoke(context.Context, ml.InvokeRequest) (ml.InvokeResponse, error) {
	return ml.InvokeResponse{
		ModelUsed:         "gemini-flash",
		ModelsTried:       []string{"gemini-flash"},
		SimulatedResponse: "assistant reply",
		TokenBreakdown: ml.InvokeTokenBreakdown{
			ModelCascade: ml.TokenIO{
				InputTokens:  12,
				OutputTokens: 18,
				TotalTokens:  30,
			},
		},
	}, nil
}

func TestChatTriggersSummaryAtFiveMessages(t *testing.T) {
	store := newFakeStore()
	client := &stubMLClient{}
	service := NewService(store, client, config.Config{SummaryInterval: 5})

	current, err := store.Create("")
	if err != nil {
		t.Fatalf("create session: %v", err)
	}
	current.Messages = []models.Message{
		{Role: "user", Content: "u1"},
		{Role: "assistant", Content: "a1"},
		{Role: "user", Content: "u2"},
		{Role: "assistant", Content: "a2"},
		{Role: "user", Content: "u3"},
		{Role: "assistant", Content: "a3"},
		{Role: "user", Content: "u4"},
		{Role: "assistant", Content: "a4"},
	}
	if err := store.Update(current); err != nil {
		t.Fatalf("seed session: %v", err)
	}

	response, err := service.Chat(context.Background(), current.ID, "u5")
	if err != nil {
		t.Fatalf("chat failed: %v", err)
	}

	if response.ModelUsed != "gemini-flash" {
		t.Fatalf("unexpected model: %s", response.ModelUsed)
	}

	updated, err := store.Get(current.ID)
	if err != nil {
		t.Fatalf("load updated session: %v", err)
	}

	if client.summariseCalls != 1 {
		t.Fatalf("expected 1 summarise call, got %d", client.summariseCalls)
	}

	if updated.Summary != "rolling summary" {
		t.Fatalf("expected rolling summary, got %q", updated.Summary)
	}

	if updated.SummarizedMessageCount == 0 {
		t.Fatalf("expected summarized message count to be updated")
	}
}

func TestChatDoesNotTriggerSummaryBeforeFiveUserMessages(t *testing.T) {
	store := newFakeStore()
	client := &stubMLClient{}
	service := NewService(store, client, config.Config{SummaryInterval: 5})

	current, err := store.Create("")
	if err != nil {
		t.Fatalf("create session: %v", err)
	}
	current.Messages = []models.Message{
		{Role: "user", Content: "u1"},
		{Role: "assistant", Content: "a1"},
		{Role: "user", Content: "u2"},
		{Role: "assistant", Content: "a2"},
		{Role: "user", Content: "u3"},
		{Role: "assistant", Content: "a3"},
	}
	if err := store.Update(current); err != nil {
		t.Fatalf("seed session: %v", err)
	}

	if _, err := service.Chat(context.Background(), current.ID, "u4"); err != nil {
		t.Fatalf("chat failed: %v", err)
	}

	if client.summariseCalls != 1 {
		t.Fatalf("expected a context summary refresh call, got %d", client.summariseCalls)
	}
}

func TestChatUsesExistingSummaryAsContext(t *testing.T) {
	store := newFakeStore()
	client := &stubMLClient{}
	service := NewService(store, client, config.Config{SummaryInterval: 5})

	current, err := store.Create("")
	if err != nil {
		t.Fatalf("create session: %v", err)
	}
	current.Summary = "existing summary"
	if err := store.Update(current); err != nil {
		t.Fatalf("seed session: %v", err)
	}

	if _, err := service.Chat(context.Background(), current.ID, "new prompt"); err != nil {
		t.Fatalf("chat failed: %v", err)
	}

	if client.lastRoute.Context != "existing summary" {
		t.Fatalf("expected route context to use existing summary, got %q", client.lastRoute.Context)
	}
}

func TestCreateSessionDoesNotDependOnMLHealth(t *testing.T) {
	store := newFakeStore()
	client := &stubMLClient{}
	service := NewService(store, client, config.Config{SummaryInterval: 5})

	session, err := service.CreateSession(context.Background(), "user-1")
	if err != nil {
		t.Fatalf("create session failed: %v", err)
	}

	if session.ID == "" {
		t.Fatalf("expected session id to be populated")
	}
	if session.UserID != "user-1" {
		t.Fatalf("expected user id to be populated")
	}
}

func TestConcurrentChatPreservesAllMessages(t *testing.T) {
	store := newFakeStore()
	client := &stubMLClient{}
	service := NewService(store, client, config.Config{SummaryInterval: 100})

	current, err := store.Create("")
	if err != nil {
		t.Fatalf("create session: %v", err)
	}

	var wg sync.WaitGroup
	prompts := []string{"first", "second"}
	for _, prompt := range prompts {
		wg.Add(1)
		go func(prompt string) {
			defer wg.Done()
			if _, err := service.Chat(context.Background(), current.ID, prompt); err != nil {
				t.Errorf("chat failed for %q: %v", prompt, err)
			}
		}(prompt)
	}
	wg.Wait()

	updated, err := store.Get(current.ID)
	if err != nil {
		t.Fatalf("load updated session: %v", err)
	}

	if len(updated.Messages) != 4 {
		t.Fatalf("expected 4 messages after 2 concurrent chats, got %d", len(updated.Messages))
	}

	if updated.Metrics.CacheMisses != 2 {
		t.Fatalf("expected 2 cache misses after concurrent requests, got %d", updated.Metrics.CacheMisses)
	}
}

func TestListUserSessions(t *testing.T) {
	store := newFakeStore()
	client := &stubMLClient{}
	service := NewService(store, client, config.Config{SummaryInterval: 5})

	first, err := store.Create("user-1")
	if err != nil {
		t.Fatalf("create first session: %v", err)
	}
	first.Messages = []models.Message{{ID: "m1", Role: "user", Content: "hello"}}
	first.Summary = "first summary"
	if err := store.Update(first); err != nil {
		t.Fatalf("update first session: %v", err)
	}

	second, err := store.Create("user-1")
	if err != nil {
		t.Fatalf("create second session: %v", err)
	}
	if err := store.Update(second); err != nil {
		t.Fatalf("update second session: %v", err)
	}

	third, err := store.Create("user-2")
	if err != nil {
		t.Fatalf("create third session: %v", err)
	}
	if err := store.Update(third); err != nil {
		t.Fatalf("update third session: %v", err)
	}

	sessions, err := service.ListUserSessions("user-1")
	if err != nil {
		t.Fatalf("list sessions failed: %v", err)
	}

	if len(sessions) != 2 {
		t.Fatalf("expected 2 sessions, got %d", len(sessions))
	}
}

func TestChatSkipsSummaryWhenContextNotNeeded(t *testing.T) {
	store := newFakeStore()
	client := &stubMLClient{classifyConfigured: true, classifyNeedsContext: false}
	service := NewService(store, client, config.Config{SummaryInterval: 5})

	current, err := store.Create("")
	if err != nil {
		t.Fatalf("create session: %v", err)
	}
	current.Messages = []models.Message{
		{Role: "user", Content: "u1"},
		{Role: "assistant", Content: "a1"},
		{Role: "user", Content: "u2"},
	}
	if err := store.Update(current); err != nil {
		t.Fatalf("seed session: %v", err)
	}

	if _, err := service.Chat(context.Background(), current.ID, "u3"); err != nil {
		t.Fatalf("chat failed: %v", err)
	}

	if client.summariseCalls != 0 {
		t.Fatalf("expected no summarise calls when context is not needed, got %d", client.summariseCalls)
	}

	if client.lastRoute.Context != "" {
		t.Fatalf("expected empty route context when context is not needed, got %q", client.lastRoute.Context)
	}
}
