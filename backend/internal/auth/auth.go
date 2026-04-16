package auth

import (
	"errors"
	"fmt"
	"net/mail"
	"strings"
	"time"

	"axiom/backend/utils"
	"golang.org/x/crypto/bcrypt"
)

var (
	ErrInvalidToken       = errors.New("invalid token")
	ErrExpiredToken       = errors.New("token expired")
	ErrInvalidCredentials = errors.New("Invalid credentials")
	ErrUserExists         = errors.New("user already exists")
	ErrUserNotFound       = errors.New("user not found")
	ErrUnauthorized       = errors.New("unauthorized")
)

type Claims = utils.JWTClaims

func NormalizeEmail(email string) string {
	return strings.ToLower(strings.TrimSpace(email))
}

func NormalizePlan(plan string) string {
	switch strings.ToLower(strings.TrimSpace(plan)) {
	case "pro":
		return "pro"
	default:
		return "free"
	}
}

func ValidateEmail(email string) error {
	email = NormalizeEmail(email)
	if email == "" {
		return errors.New("email is required")
	}
	if _, err := mail.ParseAddress(email); err != nil {
		return errors.New("invalid email format")
	}
	return nil
}

func ValidatePassword(password string) error {
	if len(strings.TrimSpace(password)) < 8 {
		return errors.New("password must be at least 8 characters")
	}
	return nil
}

func HashPassword(password string) (hash string, salt string, err error) {
	hashed, err := bcrypt.GenerateFromPassword([]byte(password), 12)
	if err != nil {
		return "", "", err
	}

	// Bcrypt encodes salt in the hash payload, so a separate salt column is optional.
	return string(hashed), "", nil
}

func VerifyPassword(password, saltHex, expectedHash string) bool {
	_ = saltHex
	if strings.TrimSpace(expectedHash) == "" {
		return false
	}
	return bcrypt.CompareHashAndPassword([]byte(expectedHash), []byte(password)) == nil
}

func SignJWT(secret string, claims Claims) (string, error) {
	return utils.GenerateToken(secret, claims)
}

func ParseJWT(secret, token string, now time.Time) (Claims, error) {
	claims, err := utils.ParseToken(secret, token, now)
	if err != nil {
		switch {
		case errors.Is(err, utils.ErrTokenExpired):
			return claims, ErrExpiredToken
		default:
			return claims, ErrInvalidToken
		}
	}

	return claims, nil
}

func NewClaims(userID, email, plan string, ttl time.Duration, now time.Time) Claims {
	return utils.NewJWTClaims(userID, email, plan, "axiom", ttl, now)
}

func ExtractBearer(header string) (string, error) {
	header = strings.TrimSpace(header)
	if header == "" {
		return "", ErrUnauthorized
	}

	parts := strings.SplitN(header, " ", 2)
	if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") || strings.TrimSpace(parts[1]) == "" {
		return "", fmt.Errorf("%w: bearer token required", ErrUnauthorized)
	}

	return strings.TrimSpace(parts[1]), nil
}
