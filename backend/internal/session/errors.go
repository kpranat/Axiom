package session

import (
	"errors"

	"axiom/backend/internal/models"
)

var ErrSessionNotFound = errors.New("session not found")

func CloneSession(session *models.Session) *models.Session {
	if session == nil {
		return nil
	}

	cloned := *session
	cloned.Messages = append([]models.Message(nil), session.Messages...)
	return &cloned
}
