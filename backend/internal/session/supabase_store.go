package session

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"time"

	"axiom/backend/internal/models"
)

type SupabaseStore struct {
	baseURL    string
	apiKey     string
	httpClient *http.Client
}

type sessionRecord struct {
	ID                     string    `json:"id"`
	UserID                 string    `json:"user_id"`
	Summary                string    `json:"summary"`
	SummarizedMessageCount int       `json:"summarized_message_count"`
	TokensUsed             int       `json:"tokens_used"`
	TokensSaved            int       `json:"tokens_saved"`
	CacheHits              int       `json:"cache_hits"`
	CacheMisses            int       `json:"cache_misses"`
	CostSaved              float64   `json:"cost_saved"`
	CreatedAt              time.Time `json:"created_at"`
	UpdatedAt              time.Time `json:"updated_at"`
}

type messageRecord struct {
	ID        string    `json:"id"`
	SessionID string    `json:"session_id"`
	Role      string    `json:"role"`
	Content   string    `json:"content"`
	CreatedAt time.Time `json:"created_at"`
}

type userRecord struct {
	ID           string    `json:"id"`
	Email        string    `json:"email"`
	PasswordHash string    `json:"password_hash"`
	PasswordSalt string    `json:"password_salt"`
	Plan         string    `json:"plan"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}

func NewSupabaseStore(baseURL, apiKey string, httpClient *http.Client) (*SupabaseStore, error) {
	baseURL = strings.TrimRight(baseURL, "/")
	if baseURL == "" || apiKey == "" {
		return nil, errors.New("supabase url and key are required")
	}

	return &SupabaseStore{
		baseURL:    baseURL,
		apiKey:     apiKey,
		httpClient: httpClient,
	}, nil
}

func (s *SupabaseStore) Create(userID string) (*models.Session, error) {
	now := time.Now().UTC()
	current := &models.Session{
		ID:        NewID(),
		UserID:    userID,
		Messages:  []models.Message{},
		CreatedAt: now,
		UpdatedAt: now,
	}

	if err := s.Update(current); err != nil {
		return nil, err
	}

	return CloneSession(current), nil
}

func (s *SupabaseStore) Get(sessionID string) (*models.Session, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	sessionRows, err := s.selectSessions(ctx, "id=eq."+url.QueryEscape(sessionID), "")
	if err != nil {
		return nil, err
	}
	if len(sessionRows) == 0 {
		return nil, ErrSessionNotFound
	}

	messageRows, err := s.selectMessages(ctx, "session_id=eq."+url.QueryEscape(sessionID), "created_at.asc")
	if err != nil {
		return nil, err
	}

	return hydrateSession(sessionRows[0], messageRows), nil
}

func (s *SupabaseStore) Update(current *models.Session) error {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	if current.ID == "" {
		current.ID = NewID()
	}
	if current.CreatedAt.IsZero() {
		current.CreatedAt = time.Now().UTC()
	}
	current.UpdatedAt = time.Now().UTC()

	if err := s.upsert(ctx, "/rest/v1/chat_sessions", []sessionRecord{{
		ID:                     current.ID,
		UserID:                 current.UserID,
		Summary:                current.Summary,
		SummarizedMessageCount: current.SummarizedMessageCount,
		TokensUsed:             current.Metrics.TokensUsed,
		TokensSaved:            current.Metrics.TokensSaved,
		CacheHits:              current.Metrics.CacheHits,
		CacheMisses:            current.Metrics.CacheMisses,
		CostSaved:              current.Metrics.CostSaved,
		CreatedAt:              current.CreatedAt,
		UpdatedAt:              current.UpdatedAt,
	}}, "resolution=merge-duplicates"); err != nil {
		return err
	}

	if len(current.Messages) == 0 {
		return nil
	}

	records := make([]messageRecord, 0, len(current.Messages))
	for i := range current.Messages {
		message := current.Messages[i]
		if message.ID == "" {
			message.ID = NewID()
			current.Messages[i].ID = message.ID
		}
		if message.Timestamp.IsZero() {
			message.Timestamp = time.Now().UTC()
			current.Messages[i].Timestamp = message.Timestamp
		}
		records = append(records, messageRecord{
			ID:        message.ID,
			SessionID: current.ID,
			Role:      message.Role,
			Content:   message.Content,
			CreatedAt: message.Timestamp,
		})
	}

	return s.upsert(ctx, "/rest/v1/chat_messages", records, "resolution=merge-duplicates")
}

func (s *SupabaseStore) ListByUser(userID string) ([]*models.Session, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	rows, err := s.selectSessions(ctx, "user_id=eq."+url.QueryEscape(userID), "updated_at.desc")
	if err != nil {
		return nil, err
	}

	sessions := make([]*models.Session, 0, len(rows))
	for _, row := range rows {
		sessions = append(sessions, hydrateSession(row, nil))
	}

	return sessions, nil
}

func (s *SupabaseStore) CreateUser(email, passwordHash, passwordSalt, plan string) (*models.User, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	now := time.Now().UTC()
	rows, err := s.insertUsers(ctx, []userRecord{{
		ID:           NewID(),
		Email:        email,
		PasswordHash: passwordHash,
		PasswordSalt: passwordSalt,
		Plan:         plan,
		CreatedAt:    now,
		UpdatedAt:    now,
	}})
	if err != nil {
		lower := strings.ToLower(err.Error())
		if strings.Contains(lower, "duplicate") || strings.Contains(lower, "unique") {
			return nil, ErrUserAlreadyExists
		}
		return nil, err
	}
	if len(rows) == 0 {
		return nil, errors.New("supabase user create returned no rows")
	}

	return hydrateUser(rows[0]), nil
}

func (s *SupabaseStore) GetUserByEmail(email string) (*models.AuthUserRecord, error) {
	rows, err := s.selectUsers("email=eq."+url.QueryEscape(email), "")
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, ErrUserNotFound
	}

	return hydrateAuthUser(rows[0]), nil
}

func (s *SupabaseStore) GetUserByID(userID string) (*models.AuthUserRecord, error) {
	rows, err := s.selectUsers("id=eq."+url.QueryEscape(userID), "")
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, ErrUserNotFound
	}

	return hydrateAuthUser(rows[0]), nil
}

func (s *SupabaseStore) selectSessions(ctx context.Context, filter, order string) ([]sessionRecord, error) {
	path := "/rest/v1/chat_sessions?select=*"
	if filter != "" {
		path += "&" + filter
	}
	if order != "" {
		path += "&order=" + order
	}

	var rows []sessionRecord
	if err := s.getJSON(ctx, path, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func (s *SupabaseStore) selectMessages(ctx context.Context, filter, order string) ([]messageRecord, error) {
	path := "/rest/v1/chat_messages?select=*"
	if filter != "" {
		path += "&" + filter
	}
	if order != "" {
		path += "&order=" + order
	}

	var rows []messageRecord
	if err := s.getJSON(ctx, path, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func (s *SupabaseStore) selectUsers(filter, order string) ([]userRecord, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	path := "/rest/v1/app_users?select=*"
	if filter != "" {
		path += "&" + filter
	}
	if order != "" {
		path += "&order=" + order
	}

	var rows []userRecord
	if err := s.getJSON(ctx, path, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func (s *SupabaseStore) insertUsers(ctx context.Context, payload []userRecord) ([]userRecord, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, s.baseURL+"/rest/v1/app_users?select=id,email,plan,created_at,updated_at", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	s.applyHeaders(req)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Prefer", "return=representation")

	res, err := s.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()

	raw, err := io.ReadAll(io.LimitReader(res.Body, 1<<20))
	if err != nil {
		return nil, err
	}
	if res.StatusCode >= http.StatusBadRequest {
		return nil, fmt.Errorf("supabase insert users failed: status=%d body=%s", res.StatusCode, strings.TrimSpace(string(raw)))
	}

	var rows []userRecord
	if err := json.Unmarshal(raw, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func (s *SupabaseStore) getJSON(ctx context.Context, path string, target any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, s.baseURL+path, nil)
	if err != nil {
		return err
	}
	s.applyHeaders(req)

	res, err := s.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()

	raw, err := io.ReadAll(io.LimitReader(res.Body, 1<<20))
	if err != nil {
		return err
	}
	if res.StatusCode >= http.StatusBadRequest {
		return fmt.Errorf("supabase get %s failed: status=%d body=%s", path, res.StatusCode, strings.TrimSpace(string(raw)))
	}
	return json.Unmarshal(raw, target)
}

func (s *SupabaseStore) upsert(ctx context.Context, path string, payload any, prefer string) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, s.baseURL+path, bytes.NewReader(body))
	if err != nil {
		return err
	}
	s.applyHeaders(req)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Prefer", prefer)

	res, err := s.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()

	raw, err := io.ReadAll(io.LimitReader(res.Body, 1<<20))
	if err != nil {
		return err
	}
	if res.StatusCode >= http.StatusBadRequest {
		return fmt.Errorf("supabase upsert %s failed: status=%d body=%s", path, res.StatusCode, strings.TrimSpace(string(raw)))
	}
	return nil
}

func (s *SupabaseStore) applyHeaders(req *http.Request) {
	req.Header.Set("apikey", s.apiKey)
	req.Header.Set("Authorization", "Bearer "+s.apiKey)
}

func hydrateSession(row sessionRecord, messages []messageRecord) *models.Session {
	current := &models.Session{
		ID:                     row.ID,
		UserID:                 row.UserID,
		Messages:               []models.Message{},
		Summary:                row.Summary,
		SummarizedMessageCount: row.SummarizedMessageCount,
		Metrics: models.SessionMetrics{
			TokensUsed:  row.TokensUsed,
			TokensSaved: row.TokensSaved,
			CacheHits:   row.CacheHits,
			CacheMisses: row.CacheMisses,
			CostSaved:   row.CostSaved,
		},
		CreatedAt: row.CreatedAt,
		UpdatedAt: row.UpdatedAt,
	}

	sort.Slice(messages, func(i, j int) bool {
		return messages[i].CreatedAt.Before(messages[j].CreatedAt)
	})

	for _, message := range messages {
		current.Messages = append(current.Messages, models.Message{
			ID:        message.ID,
			Role:      message.Role,
			Content:   message.Content,
			Timestamp: message.CreatedAt,
		})
	}

	return current
}

func hydrateUser(row userRecord) *models.User {
	return &models.User{
		ID:        row.ID,
		Email:     row.Email,
		Plan:      row.Plan,
		CreatedAt: row.CreatedAt,
		UpdatedAt: row.UpdatedAt,
	}
}

func hydrateAuthUser(row userRecord) *models.AuthUserRecord {
	return &models.AuthUserRecord{
		User:         *hydrateUser(row),
		PasswordHash: row.PasswordHash,
		PasswordSalt: row.PasswordSalt,
	}
}
