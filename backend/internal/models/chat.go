package models

import "time"

type Message struct {
	ID        string    `json:"id,omitempty"`
	Role      string    `json:"role"`
	Content   string    `json:"content"`
	Timestamp time.Time `json:"timestamp,omitempty"`
}

type SessionMetrics struct {
	InputTokensUsed  int     `json:"input_tokens_used"`
	OutputTokensUsed int     `json:"output_tokens_used"`
	TokensUsed       int     `json:"tokens_used"`
	TokensSaved      int     `json:"tokens_saved"`
	CacheHits        int     `json:"cache_hits"`
	CacheMisses      int     `json:"cache_misses"`
	CostSaved        float64 `json:"cost_saved"`
}

type Session struct {
	ID                     string         `json:"id"`
	UserID                 string         `json:"user_id,omitempty"`
	Messages               []Message      `json:"messages"`
	Summary                string         `json:"summary"`
	SummarizedMessageCount int            `json:"summarized_message_count"`
	Metrics                SessionMetrics `json:"metrics"`
	CreatedAt              time.Time      `json:"created_at"`
	UpdatedAt              time.Time      `json:"updated_at"`
}
