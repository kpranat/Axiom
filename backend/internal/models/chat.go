package models

import "time"

type Message struct {
	ID        string    `json:"id,omitempty"`
	Role      string    `json:"role"`
	Content   string    `json:"content"`
	Timestamp time.Time `json:"timestamp,omitempty"`
}

type SessionMetrics struct {
	TokensUsed  int     `json:"tokens_used"`
	TokensSaved int     `json:"tokens_saved"`
	CacheHits   int     `json:"cache_hits"`
	CacheMisses int     `json:"cache_misses"`
	CostSaved   float64 `json:"cost_saved"`
}

type Session struct {
	ID                     string
	UserID                 string
	Messages               []Message
	Summary                string
	SummarizedMessageCount int
	Metrics                SessionMetrics
	CreatedAt              time.Time
	UpdatedAt              time.Time
}
