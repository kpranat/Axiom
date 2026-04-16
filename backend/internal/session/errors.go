package session

import (
	"errors"

	"axiom/backend/internal/models"
)

var (
	ErrSessionNotFound   = errors.New("session not found")
	ErrUserNotFound      = errors.New("user not found")
	ErrUserAlreadyExists = errors.New("user already exists")
)

func CloneSession(session *models.Session) *models.Session {
	if session == nil {
		return nil
	}

	cloned := *session
	cloned.Messages = append([]models.Message(nil), session.Messages...)
	return &cloned
}
