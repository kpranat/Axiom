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
	Create() *models.Session
	Get(sessionID string) (*models.Session, error)
	Update(session *models.Session) error
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

func NewService(store SessionStore, mlClient MLClient, cfg config.Config) *Service {
	return &Service{
		store:           store,
		mlClient:        mlClient,
		summaryInterval: cfg.SummaryInterval,
		locker:          newSessionLocker(),
	}
}

func (s *Service) CreateSession(ctx context.Context) (*models.Session, error) {
	return s.store.Create(), nil
}

func (s *Service) GetMetrics(sessionID string) (models.SessionMetrics, error) {
	current, err := s.store.Get(sessionID)
	if err != nil {
		return models.SessionMetrics{}, err
	}
	return current.Metrics, nil
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
