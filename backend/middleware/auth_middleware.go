package middleware

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

	"axiom/backend/utils"
)

type contextKey string

const authClaimsKey contextKey = "authClaims"

type AuthIdentity struct {
	UserID string
	Email  string
	Plan   string
	JTI    string
	Token  string
}

func AuthMiddleware(jwtSecret string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			token, ok := extractBearer(r.Header.Get("Authorization"))
			if !ok {
				writeUnauthorized(w, "unauthorized")
				return
			}

			claims, err := utils.ParseToken(jwtSecret, token, time.Now().UTC())
			if err != nil {
				if errors.Is(err, utils.ErrTokenExpired) {
					writeUnauthorized(w, "token_expired")
					return
				}
				writeUnauthorized(w, "unauthorized")
				return
			}

			identity := AuthIdentity{
				UserID: claims.UserID,
				Email:  claims.Email,
				Plan:   claims.Plan,
				JTI:    claims.ID,
				Token:  token,
			}
			ctx := context.WithValue(r.Context(), authClaimsKey, identity)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func IdentityFromContext(ctx context.Context) (AuthIdentity, bool) {
	identity, ok := ctx.Value(authClaimsKey).(AuthIdentity)
	return identity, ok
}

func writeUnauthorized(w http.ResponseWriter, code string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusUnauthorized)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": code})
}

func extractBearer(header string) (string, bool) {
	header = strings.TrimSpace(header)
	if header == "" {
		return "", false
	}

	parts := strings.SplitN(header, " ", 2)
	if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") {
		return "", false
	}

	token := strings.TrimSpace(parts[1])
	if token == "" {
		return "", false
	}
	return token, true
}
