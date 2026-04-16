package session

import (
	"slices"
	"sync"
	"time"

	"axiom/backend/internal/models"
)

type Store struct {
	mu       sync.RWMutex
	sessions map[string]*models.Session
}

func NewStore() *Store {
	return &Store{
		sessions: make(map[string]*models.Session),
	}
}

func (s *Store) Create(userID string) (*models.Session, error) {
	now := time.Now().UTC()
	session := &models.Session{
		ID:        NewID(),
		UserID:    userID,
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

	return CloneSession(session), nil
}

func (s *Store) Update(session *models.Session) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, ok := s.sessions[session.ID]; !ok {
		return ErrSessionNotFound
	}

	session.UpdatedAt = time.Now().UTC()
	s.sessions[session.ID] = CloneSession(session)
	return nil
}

func (s *Store) ListByUser(userID string) ([]*models.Session, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	sessions := make([]*models.Session, 0)
	for _, current := range s.sessions {
		if current.UserID == userID {
			sessions = append(sessions, CloneSession(current))
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

func cloneSession(session *models.Session) *models.Session {
	if session == nil {
		return nil
	}

	cloned := *session
	cloned.Messages = append([]models.Message(nil), session.Messages...)
	return &cloned
}
