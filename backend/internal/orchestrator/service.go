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
	QueryCache(ctx context.Context, payload ml.CacheQueryRequest) (ml.CacheQueryResponse, error)
	StoreCache(ctx context.Context, payload ml.CacheStoreRequest) (ml.CacheStoreResponse, error)
	Classify(ctx context.Context, payload ml.ClassifyRequest) (ml.ClassifyResponse, error)
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

	cacheQuery, cacheErr := s.mlClient.QueryCache(ctx, ml.CacheQueryRequest{
		Prompt: prompt,
		UserID: current.ID,
	})
	if cacheErr != nil {
		fmt.Printf("[CACHE] query failed, continuing without cache: %v\n", cacheErr)
	}

	if cacheErr == nil && cacheQuery.CacheHit && cacheQuery.Response != nil {
		assistantMessage := models.Message{
			Role:      "assistant",
			Content:   *cacheQuery.Response,
			Timestamp: time.Now().UTC(),
		}
		current.Messages = append(current.Messages, assistantMessage)
		current.Metrics.CacheHits++

		if err := s.store.Update(current); err != nil {
			return ChatResponse{}, err
		}

		return ChatResponse{
			Response:    *cacheQuery.Response,
			ModelUsed:   "semantic-cache",
			TokensUsed:  0,
			TokensSaved: 0,
			CacheHit:    true,
		}, nil
	}

	current.Metrics.CacheMisses++

	var contextSummary string
	classifyResp, classifyErr := s.mlClient.Classify(ctx, ml.ClassifyRequest{Prompt: prompt})
	needsContext := false
	if classifyErr != nil {
		fmt.Printf("[CLASSIFY] classify failed, falling back to prompt-only: %v\n", classifyErr)
	} else {
		needsContext = classifyResp.NeedsContext
	}

	if needsContext {
		contextSummary = strings.TrimSpace(current.Summary)
		if contextSummary == "" {
			refreshedSummary, err := s.refreshContextSummary(ctx, current)
			if err != nil {
				fmt.Printf("[CONTEXT] summary refresh failed, using prompt-only fallback: %v\n", err)
			} else {
				contextSummary = strings.TrimSpace(refreshedSummary)
			}
		}
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

	classified := cacheQuery.Classified
	if _, err := s.mlClient.StoreCache(ctx, ml.CacheStoreRequest{
		Prompt:     prompt,
		UserID:     current.ID,
		Response:   invokeResponse.SimulatedResponse,
		Classified: classified,
	}); err != nil {
		fmt.Printf("[CACHE] store failed, continuing without cache write-back: %v\n", err)
	}

	summarySaved, err := s.maybeSummarise(ctx, current)
	if err != nil {
		fmt.Printf("[SUMMARISE] periodic summary failed, continuing: %v\n", err)
		summarySaved = 0
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

func (s *Service) refreshContextSummary(ctx context.Context, current *models.Session) (string, error) {
	priorCount := len(current.Messages) - 1
	if priorCount <= 0 {
		return "", nil
	}

	messages := make([]models.Message, 0, priorCount+1)
	if current.Summary != "" {
		messages = append(messages, models.Message{
			Role:    "system",
			Content: "Existing conversation summary:\n" + current.Summary,
		})
	}
	messages = append(messages, current.Messages[:priorCount]...)

	summaryResponse, err := s.mlClient.Summarise(ctx, ml.SummariseRequest{Messages: messages})
	if err != nil {
		return "", fmt.Errorf("refresh conversation summary: %w", err)
	}

	updated := strings.TrimSpace(summaryResponse.Summary)
	if updated == "" {
		return "", nil
	}

	current.Summary = updated
	current.SummarizedMessageCount = priorCount
	return updated, nil
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
