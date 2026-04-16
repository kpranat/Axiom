package utils

import (
	"errors"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

var (
	ErrInvalidToken = errors.New("invalid token")
	ErrTokenExpired = errors.New("token expired")
)

type JWTClaims struct {
	UserID string `json:"user_id"`
	Email  string `json:"email"`
	Plan   string `json:"plan"`
	jwt.RegisteredClaims
}

func NewJWTClaims(userID, email, plan, issuer string, ttl time.Duration, now time.Time) JWTClaims {
	normalizedPlan := strings.ToLower(strings.TrimSpace(plan))
	if normalizedPlan == "" {
		normalizedPlan = "free"
	}

	return JWTClaims{
		UserID: strings.TrimSpace(userID),
		Email:  strings.ToLower(strings.TrimSpace(email)),
		Plan:   normalizedPlan,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   strings.TrimSpace(userID),
			ID:        uuid.NewString(),
			Issuer:    strings.TrimSpace(issuer),
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(ttl)),
		},
	}
}

func GenerateToken(secret string, claims JWTClaims) (string, error) {
	if strings.TrimSpace(secret) == "" {
		return "", errors.New("jwt secret is required")
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(secret))
}

func ParseToken(secret, tokenString string, now time.Time) (JWTClaims, error) {
	var claims JWTClaims
	if strings.TrimSpace(secret) == "" || strings.TrimSpace(tokenString) == "" {
		return claims, ErrInvalidToken
	}

	parsed, err := jwt.ParseWithClaims(
		tokenString,
		&claims,
		func(token *jwt.Token) (any, error) {
			if token.Method != jwt.SigningMethodHS256 {
				return nil, ErrInvalidToken
			}
			return []byte(secret), nil
		},
		jwt.WithValidMethods([]string{jwt.SigningMethodHS256.Alg()}),
		jwt.WithTimeFunc(func() time.Time { return now }),
	)
	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return claims, ErrTokenExpired
		}
		return claims, ErrInvalidToken
	}

	if !parsed.Valid || strings.TrimSpace(claims.UserID) == "" || strings.TrimSpace(claims.Email) == "" {
		return claims, ErrInvalidToken
	}

	return claims, nil
}
