package session

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"sync"
	"time"

	"axiom/backend/internal/models"
)

var ErrSessionNotFound = errors.New("session not found")

type Store struct {
	mu       sync.RWMutex
	sessions map[string]*models.Session
}

func NewStore() *Store {
	return &Store{
		sessions: make(map[string]*models.Session),
	}
}

func (s *Store) Create() *models.Session {
	now := time.Now().UTC()
	session := &models.Session{
		ID:        newID(),
		CreatedAt: now,
		UpdatedAt: now,
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	s.sessions[session.ID] = session
	return cloneSession(session)
}

func (s *Store) Get(sessionID string) (*models.Session, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	session, ok := s.sessions[sessionID]
	if !ok {
		return nil, ErrSessionNotFound
	}

	return cloneSession(session), nil
}

func (s *Store) Update(session *models.Session) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, ok := s.sessions[session.ID]; !ok {
		return ErrSessionNotFound
	}

	session.UpdatedAt = time.Now().UTC()
	s.sessions[session.ID] = cloneSession(session)
	return nil
}

func cloneSession(session *models.Session) *models.Session {
	if session == nil {
		return nil
	}

	cloned := *session
	cloned.Messages = append([]models.Message(nil), session.Messages...)
	return &cloned
}

func newID() string {
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		return strconvTimeFallback()
	}
	return hex.EncodeToString(buf)
}

func strconvTimeFallback() string {
	return hex.EncodeToString([]byte(time.Now().UTC().Format("20060102150405.000000000")))
}
