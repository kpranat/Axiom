package orchestrator

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"axiom/backend/internal/config"
	"axiom/backend/internal/ml"
	"axiom/backend/internal/models"
	"axiom/backend/internal/session"
)

type SessionStore interface {
	Create(userID string) *models.Session
	Get(sessionID string) (*models.Session, error)
	Update(session *models.Session) error
	ListByUser(userID string) ([]*models.Session, error)
}

type MLClient interface {
	Health(ctx context.Context) error
	Summarise(ctx context.Context, payload ml.SummariseRequest) (ml.SummariseResponse, error)
	Route(ctx context.Context, payload ml.RouteRequest) (ml.RouteResponse, error)
	Invoke(ctx context.Context, payload ml.InvokeRequest) (ml.InvokeResponse, error)
}

type Service struct {
	store           SessionStore
	mlClient        MLClient
	summaryInterval int
	locker          *sessionLocker
}

type ChatResponse struct {
	Response    string `json:"response"`
	ModelUsed   string `json:"model_used"`
	TokensUsed  int    `json:"tokens_used"`
	TokensSaved int    `json:"tokens_saved"`
	CacheHit    bool   `json:"cache_hit"`
}

type SessionSummary struct {
	ID           string    `json:"id"`
	UserID       string    `json:"user_id,omitempty"`
	Summary      string    `json:"summary"`
	MessageCount int       `json:"message_count"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
	LastMessage  string    `json:"last_message,omitempty"`
	TokensUsed   int       `json:"tokens_used"`
	TokensSaved  int       `json:"tokens_saved"`
}

func NewService(store SessionStore, mlClient MLClient, cfg config.Config) *Service {
	return &Service{
		store:           store,
		mlClient:        mlClient,
		summaryInterval: cfg.SummaryInterval,
		locker:          newSessionLocker(),
	}
}

func (s *Service) CreateSession(ctx context.Context, userID string) (*models.Session, error) {
	return s.store.Create(strings.TrimSpace(userID)), nil
}

func (s *Service) GetMetrics(sessionID string) (models.SessionMetrics, error) {
	current, err := s.store.Get(sessionID)
	if err != nil {
		return models.SessionMetrics{}, err
	}
	return current.Metrics, nil
}

func (s *Service) GetSession(sessionID string) (*models.Session, error) {
	return s.store.Get(sessionID)
}

func (s *Service) ListUserSessions(userID string) ([]SessionSummary, error) {
	sessions, err := s.store.ListByUser(strings.TrimSpace(userID))
	if err != nil {
		return nil, err
	}

	result := make([]SessionSummary, 0, len(sessions))
	for _, current := range sessions {
		lastMessage := ""
		if len(current.Messages) > 0 {
			lastMessage = current.Messages[len(current.Messages)-1].Content
		}

		result = append(result, SessionSummary{
			ID:           current.ID,
			UserID:       current.UserID,
			Summary:      current.Summary,
			MessageCount: len(current.Messages),
			CreatedAt:    current.CreatedAt,
			UpdatedAt:    current.UpdatedAt,
			LastMessage:  lastMessage,
			TokensUsed:   current.Metrics.TokensUsed,
			TokensSaved:  current.Metrics.TokensSaved,
		})
	}

	return result, nil
}

func (s *Service) Chat(ctx context.Context, sessionID, prompt string) (ChatResponse, error) {
	prompt = strings.TrimSpace(prompt)
	if prompt == "" {
		return ChatResponse{}, errors.New("prompt is required")
	}

	unlock := s.locker.Lock(sessionID)
	defer unlock()

	current, err := s.store.Get(sessionID)
	if err != nil {
		return ChatResponse{}, err
	}

	userMessage := models.Message{
		ID:        session.NewID(),
		Role:      "user",
		Content:   prompt,
		Timestamp: time.Now().UTC(),
	}
	current.Messages = append(current.Messages, userMessage)

	contextSummary := strings.TrimSpace(current.Summary)
	if contextSummary == "" {
		contextSummary = buildTranscript(current.Messages[:len(current.Messages)-1])
	}

	routeResponse, err := s.mlClient.Route(ctx, ml.RouteRequest{
		Prompt:  prompt,
		Context: contextSummary,
		UserID:  current.ID,
	})
	if err != nil {
		return ChatResponse{}, err
	}

	invokeResponse, err := s.mlClient.Invoke(ctx, ml.InvokeRequest{
		PromptToSend: routeResponse.PromptToSend,
		Tier:         routeResponse.Tier,
	})
	if err != nil {
		return ChatResponse{}, err
	}

	assistantMessage := models.Message{
		ID:        session.NewID(),
		Role:      "assistant",
		Content:   invokeResponse.SimulatedResponse,
		Timestamp: time.Now().UTC(),
	}
	current.Messages = append(current.Messages, assistantMessage)

	current.Metrics.TokensUsed += routeResponse.OptimizedTokens
	current.Metrics.TokensSaved += routeResponse.TokensSaved
	current.Metrics.CostSaved = estimateCostSaved(current.Metrics.TokensSaved)

	summarySaved, err := s.maybeSummarise(ctx, current)
	if err != nil {
		return ChatResponse{}, err
	}
	current.Metrics.TokensSaved += summarySaved
	current.Metrics.CostSaved = estimateCostSaved(current.Metrics.TokensSaved)

	if err := s.store.Update(current); err != nil {
		return ChatResponse{}, err
	}

	return ChatResponse{
		Response:    invokeResponse.SimulatedResponse,
		ModelUsed:   invokeResponse.ModelUsed,
		TokensUsed:  routeResponse.OptimizedTokens,
		TokensSaved: routeResponse.TokensSaved + summarySaved,
		CacheHit:    false,
	}, nil
}

func (s *Service) maybeSummarise(ctx context.Context, current *models.Session) (int, error) {
	pending := current.Messages[current.SummarizedMessageCount:]
	if countUserMessages(pending) < s.summaryInterval {
		return 0, nil
	}

	messages := make([]models.Message, 0, len(pending)+1)
	if current.Summary != "" {
		messages = append(messages, models.Message{
			Role:    "system",
			Content: "Existing conversation summary:\n" + current.Summary,
		})
	}
	messages = append(messages, pending...)

	summaryResponse, err := s.mlClient.Summarise(ctx, ml.SummariseRequest{
		Messages: messages,
	})
	if err != nil {
		return 0, fmt.Errorf("summarise conversation: %w", err)
	}

	current.Summary = strings.TrimSpace(summaryResponse.Summary)
	current.SummarizedMessageCount = len(current.Messages)
	return summaryResponse.TokensSaved, nil
}

func buildTranscript(messages []models.Message) string {
	if len(messages) == 0 {
		return ""
	}

	lines := make([]string, 0, len(messages))
	for _, message := range messages {
		lines = append(lines, fmt.Sprintf("%s: %s", strings.ToUpper(message.Role), message.Content))
	}

	return strings.Join(lines, "\n")
}

func estimateCostSaved(tokensSaved int) float64 {
	return float64(tokensSaved) * 0.000002
}

func countUserMessages(messages []models.Message) int {
	count := 0
	for _, message := range messages {
		if strings.EqualFold(message.Role, "user") {
			count++
		}
	}
	return count
}

func IsSessionNotFound(err error) bool {
	return errors.Is(err, session.ErrSessionNotFound)
}
