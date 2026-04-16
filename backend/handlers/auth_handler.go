package handlers

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"axiom/backend/internal/auth"
	"axiom/backend/internal/orchestrator"
)

type AuthService interface {
	Signup(ctx context.Context, email, password, plan string) (orchestrator.AuthResponse, error)
	Login(ctx context.Context, email, password string) (orchestrator.AuthResponse, error)
	CurrentUser(token string) (orchestrator.AuthResponse, error)
}

type AuthHandler struct {
	service AuthService
}

type authRequest struct {
	Name     string `json:"name,omitempty"`
	Email    string `json:"email"`
	Password string `json:"password"`
	Plan     string `json:"plan,omitempty"`
}

func NewAuthHandler(service AuthService) *AuthHandler {
	return &AuthHandler{service: service}
}

func (h *AuthHandler) Signup(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, errors.New("method not allowed"))
		return
	}

	var payload authRequest
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		writeError(w, http.StatusBadRequest, errors.New("invalid json body"))
		return
	}

	response, err := h.service.Signup(r.Context(), payload.Email, payload.Password, payload.Plan)
	if err != nil {
		switch {
		case orchestrator.IsUserExists(err):
			writeError(w, http.StatusConflict, err)
		case strings.Contains(strings.ToLower(err.Error()), "password") || strings.Contains(strings.ToLower(err.Error()), "email"):
			writeError(w, http.StatusBadRequest, err)
		default:
			writeError(w, http.StatusInternalServerError, err)
		}
		return
	}

	writeJSON(w, http.StatusCreated, response)
}

func (h *AuthHandler) Login(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, errors.New("method not allowed"))
		return
	}

	var payload authRequest
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		writeError(w, http.StatusBadRequest, errors.New("invalid json body"))
		return
	}

	response, err := h.service.Login(r.Context(), payload.Email, payload.Password)
	if err != nil {
		if orchestrator.IsInvalidCredentials(err) {
			writeError(w, http.StatusUnauthorized, auth.ErrInvalidCredentials)
			return
		}
		writeError(w, http.StatusInternalServerError, err)
		return
	}

	writeJSON(w, http.StatusOK, response)
}

func (h *AuthHandler) Me(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, errors.New("method not allowed"))
		return
	}

	token, err := auth.ExtractBearer(r.Header.Get("Authorization"))
	if err != nil {
		writeError(w, http.StatusUnauthorized, err)
		return
	}

	response, err := h.service.CurrentUser(token)
	if err != nil {
		if errors.Is(err, auth.ErrExpiredToken) {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "token_expired"})
			return
		}
		if orchestrator.IsUnauthorized(err) {
			writeError(w, http.StatusUnauthorized, err)
			return
		}
		writeError(w, http.StatusInternalServerError, err)
		return
	}

	writeJSON(w, http.StatusOK, response)
}

func (h *AuthHandler) Logout(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, errors.New("method not allowed"))
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{
		"status":  "ok",
		"message": "Logged out. Stateless JWT mode requires client token deletion.",
	})
}

func writeError(w http.ResponseWriter, status int, err error) {
	writeJSON(w, status, map[string]string{"error": err.Error()})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
