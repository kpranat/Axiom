package httpapi

import (
	"encoding/json"
	"fmt"
	"math"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"axiom/backend/internal/auth"
	"axiom/backend/internal/models"
)

type rateLimiter struct {
	mu              sync.Mutex
	entries         map[string]*rateLimitEntry
	limit           int
	window          time.Duration
	refillPerSecond float64
}

type rateLimitEntry struct {
	tokens   float64
	lastSeen time.Time
}

func newRateLimiter(limit int, window time.Duration) *rateLimiter {
	return &rateLimiter{
		entries:         make(map[string]*rateLimitEntry),
		limit:           limit,
		window:          window,
		refillPerSecond: float64(limit) / window.Seconds(),
	}
}

func (h *Handler) withRateLimit(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodOptions {
			next.ServeHTTP(w, r)
			return
		}

		key := h.rateLimitKey(r)
		allowed, remaining, retryAfter := h.rateLimiter.Allow(key, time.Now().UTC())

		w.Header().Set("X-RateLimit-Limit", fmt.Sprintf("%d", h.rateLimiter.limit))
		w.Header().Set("X-RateLimit-Remaining", fmt.Sprintf("%d", remaining))

		if !allowed {
			if retryAfter > 0 {
				w.Header().Set("Retry-After", fmt.Sprintf("%d", int(math.Ceil(retryAfter.Seconds()))))
			}
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusTooManyRequests)
			_ = json.NewEncoder(w).Encode(map[string]string{"error": "rate limit exceeded"})
			return
		}

		next.ServeHTTP(w, r)
	})
}

func (l *rateLimiter) Allow(key string, now time.Time) (bool, int, time.Duration) {
	l.mu.Lock()
	defer l.mu.Unlock()

	entry, ok := l.entries[key]
	if !ok {
		entry = &rateLimitEntry{
			tokens:   float64(l.limit),
			lastSeen: now,
		}
		l.entries[key] = entry
	}

	elapsed := now.Sub(entry.lastSeen).Seconds()
	if elapsed > 0 {
		entry.tokens = minFloat(float64(l.limit), entry.tokens+(elapsed*l.refillPerSecond))
		entry.lastSeen = now
	}

	l.cleanup(now)

	if entry.tokens < 1 {
		missing := 1 - entry.tokens
		retryAfter := time.Duration((missing / l.refillPerSecond) * float64(time.Second))
		return false, 0, retryAfter
	}

	entry.tokens--
	return true, int(math.Floor(entry.tokens)), 0
}

func (l *rateLimiter) cleanup(now time.Time) {
	expiry := now.Add(-2 * l.window)
	for key, entry := range l.entries {
		if entry.lastSeen.Before(expiry) {
			delete(l.entries, key)
		}
	}
}

func (h *Handler) rateLimitKey(r *http.Request) string {
	identity := clientIP(r)
	if user, err := h.authenticatedUser(r); err == nil && user != nil {
		identity = "user:" + user.ID
	}

	return strings.Join([]string{identity, r.Method, normalizeRateLimitPath(r.URL.Path)}, "|")
}

func (h *Handler) authenticatedUser(r *http.Request) (*models.User, error) {
	header := strings.TrimSpace(r.Header.Get("Authorization"))
	if header == "" {
		return nil, nil
	}

	token, err := auth.ExtractBearer(header)
	if err != nil {
		return nil, err
	}

	return h.service.UserFromToken(token)
}

func clientIP(r *http.Request) string {
	for _, header := range []string{"CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP"} {
		value := strings.TrimSpace(r.Header.Get(header))
		if value == "" {
			continue
		}
		if header == "X-Forwarded-For" {
			parts := strings.Split(value, ",")
			if len(parts) > 0 {
				value = strings.TrimSpace(parts[0])
			}
		}
		if value != "" {
			return value
		}
	}

	host, _, err := net.SplitHostPort(strings.TrimSpace(r.RemoteAddr))
	if err == nil && host != "" {
		return host
	}
	if strings.TrimSpace(r.RemoteAddr) != "" {
		return strings.TrimSpace(r.RemoteAddr)
	}
	return "unknown"
}

func normalizeRateLimitPath(path string) string {
	if strings.HasPrefix(path, "/api/") {
		path = strings.TrimPrefix(path, "/api")
	}

	switch {
	case strings.HasPrefix(path, "/sessions/"):
		return "/sessions/:id"
	case strings.HasPrefix(path, "/metrics/"):
		return "/metrics/:id"
	case strings.HasPrefix(path, "/users/") && strings.HasSuffix(path, "/sessions"):
		return "/users/:id/sessions"
	default:
		return path
	}
}

func minFloat(left, right float64) float64 {
	if left < right {
		return left
	}
	return right
}
