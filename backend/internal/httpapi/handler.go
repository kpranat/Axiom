package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"axiom/backend/internal/models"
	"axiom/backend/internal/orchestrator"
)

type Service interface {
	CreateSession(ctx context.Context, userID string) (*models.Session, error)
	Chat(ctx context.Context, sessionID, prompt string) (orchestrator.ChatResponse, error)
	GetMetrics(sessionID string) (models.SessionMetrics, error)
	GetSession(sessionID string) (*models.Session, error)
	ListUserSessions(userID string) ([]orchestrator.SessionSummary, error)
}

type Handler struct {
	service Service
}

type createSessionResponse struct {
	SessionID string `json:"session_id"`
}

type createSessionRequest struct {
	UserID string `json:"user_id"`
}

type chatRequest struct {
	SessionID string `json:"session_id"`
	Prompt    string `json:"prompt"`
}

func NewHandler(service Service) *Handler {
	return &Handler{service: service}
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	h.registerRoutes(mux, "")
	h.registerRoutes(mux, "/api")
	return withCORS(mux)
}

func (h *Handler) registerRoutes(mux *http.ServeMux, prefix string) {
	mux.HandleFunc(prefix+"/health", h.handleHealth)
	mux.HandleFunc(prefix+"/session", h.handleSession)
	mux.HandleFunc(prefix+"/sessions/", h.handleSessionByID)
	mux.HandleFunc(prefix+"/chat", h.handleChat)
	mux.HandleFunc(prefix+"/metrics/", h.handleMetrics)
	mux.HandleFunc(prefix+"/users/", h.handleUsers)
}

func (h *Handler) handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodGet {
		methodNotAllowed(w)
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (h *Handler) handleSession(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodPost {
		methodNotAllowed(w)
		return
	}

	var payload createSessionRequest
	if r.ContentLength > 0 {
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			writeError(w, http.StatusBadRequest, errors.New("invalid json body"))
			return
		}
	}

	session, err := h.service.CreateSession(r.Context(), payload.UserID)
	if err != nil {
		writeError(w, http.StatusBadGateway, err)
		return
	}

	writeJSON(w, http.StatusCreated, createSessionResponse{SessionID: session.ID})
}

func (h *Handler) handleSessionByID(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodGet {
		methodNotAllowed(w)
		return
	}

	path := r.URL.Path
	sessionID := strings.TrimPrefix(path, "/sessions/")
	if strings.HasPrefix(path, "/api/sessions/") {
		sessionID = strings.TrimPrefix(path, "/api/sessions/")
	}
	if sessionID == "" || strings.Contains(sessionID, "/") {
		writeError(w, http.StatusBadRequest, errors.New("session_id is required"))
		return
	}

	current, err := h.service.GetSession(sessionID)
	if err != nil {
		if orchestrator.IsSessionNotFound(err) {
			writeError(w, http.StatusNotFound, err)
			return
		}
		writeError(w, http.StatusInternalServerError, err)
		return
	}

	writeJSON(w, http.StatusOK, current)
}

func (h *Handler) handleChat(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodPost {
		methodNotAllowed(w)
		return
	}

	var payload chatRequest
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		writeError(w, http.StatusBadRequest, errors.New("invalid json body"))
		return
	}

	response, err := h.service.Chat(r.Context(), payload.SessionID, payload.Prompt)
	if err != nil {
		switch {
		case orchestrator.IsSessionNotFound(err):
			writeError(w, http.StatusNotFound, err)
		case strings.Contains(err.Error(), "prompt is required"):
			writeError(w, http.StatusBadRequest, err)
		default:
			writeError(w, http.StatusBadGateway, err)
		}
		return
	}

	writeJSON(w, http.StatusOK, response)
}

func (h *Handler) handleMetrics(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodGet {
		methodNotAllowed(w)
		return
	}

	path := r.URL.Path
	sessionID := strings.TrimPrefix(path, "/metrics/")
	if strings.HasPrefix(path, "/api/metrics/") {
		sessionID = strings.TrimPrefix(path, "/api/metrics/")
	}
	if sessionID == "" || strings.Contains(sessionID, "/") {
		writeError(w, http.StatusBadRequest, errors.New("session_id is required"))
		return
	}

	metrics, err := h.service.GetMetrics(sessionID)
	if err != nil {
		if orchestrator.IsSessionNotFound(err) {
			writeError(w, http.StatusNotFound, err)
			return
		}
		writeError(w, http.StatusInternalServerError, err)
		return
	}

	writeJSON(w, http.StatusOK, metrics)
}

func (h *Handler) handleUsers(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodGet {
		methodNotAllowed(w)
		return
	}

	path := strings.TrimPrefix(r.URL.Path, "/users/")
	if strings.HasPrefix(r.URL.Path, "/api/users/") {
		path = strings.TrimPrefix(r.URL.Path, "/api/users/")
	}
	parts := strings.Split(path, "/")
	if len(parts) != 2 || parts[0] == "" || parts[1] != "sessions" {
		writeError(w, http.StatusNotFound, errors.New("route not found"))
		return
	}

	sessions, err := h.service.ListUserSessions(parts[0])
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}

	writeJSON(w, http.StatusOK, sessions)
}

func methodNotAllowed(w http.ResponseWriter) {
	writeError(w, http.StatusMethodNotAllowed, errors.New("method not allowed"))
}

func writeError(w http.ResponseWriter, status int, err error) {
	writeJSON(w, status, map[string]string{"error": err.Error()})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func withCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}

		next.ServeHTTP(w, r)
	})
}
