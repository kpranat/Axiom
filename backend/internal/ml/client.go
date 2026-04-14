package ml

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"

	"axiom/backend/internal/models"
)

type Client struct {
	baseURL    string
	httpClient *http.Client
}

type SummariseRequest struct {
	Messages []models.Message `json:"messages"`
}

type SummariseResponse struct {
	Summary     string `json:"summary"`
	TokensSaved int    `json:"tokens_saved"`
}

type ClassifyRequest struct {
	Prompt string `json:"prompt"`
}

type ClassifyResponse struct {
	NeedsContext bool    `json:"needs_context"`
	Confidence   float64 `json:"confidence"`
	Reason       string  `json:"reason"`
}

type CacheQueryRequest struct {
	Prompt string `json:"prompt"`
	UserID string `json:"user_id"`
}

type CacheQueryResponse struct {
	CacheHit   bool     `json:"cache_hit"`
	Response   *string  `json:"response"`
	CacheLayer string   `json:"cache_layer"`
	Classified string   `json:"classified"`
	Score      *float64 `json:"score"`
}

type CacheStoreRequest struct {
	Prompt     string `json:"prompt"`
	UserID     string `json:"user_id"`
	Response   string `json:"response"`
	Classified string `json:"classified,omitempty"`
}

type CacheStoreResponse struct {
	Status      string `json:"status"`
	Message     string `json:"message"`
	StoredLayer string `json:"stored_layer"`
}

type RouteRequest struct {
	Prompt  string `json:"prompt"`
	Context string `json:"context,omitempty"`
	UserID  string `json:"user_id"`
}

type RouteResponse struct {
	PromptToSend    string `json:"prompt_to_send"`
	Tier            int    `json:"tier"`
	Reason          string `json:"reason"`
	OriginalTokens  int    `json:"original_tokens"`
	OptimizedTokens int    `json:"optimized_tokens"`
	TokensSaved     int    `json:"tokens_saved"`
}

type InvokeRequest struct {
	PromptToSend string `json:"prompt_to_send"`
	Tier         int    `json:"tier"`
}

type InvokeResponse struct {
	TierNumber        int      `json:"tier_number"`
	TierName          string   `json:"tier_name"`
	ModelUsed         string   `json:"model_used"`
	ModelsTried       []string `json:"models_tried"`
	SimulatedResponse string   `json:"simulated_response"`
}

func NewClient(baseURL string, httpClient *http.Client) *Client {
	return &Client{
		baseURL:    strings.TrimRight(baseURL, "/"),
		httpClient: httpClient,
	}
}

func (c *Client) Health(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/health", nil)
	if err != nil {
		return err
	}

	res, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()

	if res.StatusCode >= http.StatusBadRequest {
		body, _ := io.ReadAll(io.LimitReader(res.Body, 4096))
		return fmt.Errorf("ml health failed: %s", strings.TrimSpace(string(body)))
	}

	return nil
}

func (c *Client) Summarise(ctx context.Context, payload SummariseRequest) (SummariseResponse, error) {
	var response SummariseResponse
	err := c.postJSON(ctx, "/summarise/", payload, &response)
	return response, err
}

func (c *Client) Classify(ctx context.Context, payload ClassifyRequest) (ClassifyResponse, error) {
	var response ClassifyResponse
	err := c.postJSON(ctx, "/classify/", payload, &response)
	return response, err
}

func (c *Client) QueryCache(ctx context.Context, payload CacheQueryRequest) (CacheQueryResponse, error) {
	var response CacheQueryResponse
	err := c.postJSON(ctx, "/cache/query", payload, &response)
	return response, err
}

func (c *Client) StoreCache(ctx context.Context, payload CacheStoreRequest) (CacheStoreResponse, error) {
	var response CacheStoreResponse
	err := c.postJSON(ctx, "/cache/store", payload, &response)
	return response, err
}

func (c *Client) Route(ctx context.Context, payload RouteRequest) (RouteResponse, error) {
	var response RouteResponse
	err := c.postJSON(ctx, "/route", payload, &response)
	return response, err
}

func (c *Client) Invoke(ctx context.Context, payload InvokeRequest) (InvokeResponse, error) {
	var response InvokeResponse
	err := c.postJSON(ctx, "/llm/invoke", payload, &response)
	return response, err
}

func (c *Client) postJSON(ctx context.Context, path string, payload any, target any) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	res, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()

	raw, err := io.ReadAll(io.LimitReader(res.Body, 1<<20))
	if err != nil {
		return err
	}

	if res.StatusCode >= http.StatusBadRequest {
		return fmt.Errorf("ml request %s failed: status=%d body=%s", path, res.StatusCode, strings.TrimSpace(string(raw)))
	}

	if err := json.Unmarshal(raw, target); err != nil {
		return fmt.Errorf("decode %s response: %w", path, err)
	}

	return nil
}
