package auth

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"
)

var (
	ErrInvalidToken       = errors.New("invalid token")
	ErrExpiredToken       = errors.New("token expired")
	ErrInvalidCredentials = errors.New("invalid email or password")
	ErrUserExists         = errors.New("user already exists")
	ErrUserNotFound       = errors.New("user not found")
	ErrUnauthorized       = errors.New("unauthorized")
)

type Claims struct {
	Subject string `json:"sub"`
	Email   string `json:"email"`
	Plan    string `json:"plan"`
	Issued  int64  `json:"iat"`
	Expiry  int64  `json:"exp"`
}

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

func ValidatePassword(password string) error {
	if len(strings.TrimSpace(password)) < 8 {
		return errors.New("password must be at least 8 characters")
	}
	return nil
}

func HashPassword(password string) (hash string, salt string, err error) {
	saltBytes := make([]byte, 32)
	if _, err := rand.Read(saltBytes); err != nil {
		return "", "", err
	}

	return hashPasswordWithSalt(password, saltBytes), hex.EncodeToString(saltBytes), nil
}

func VerifyPassword(password, saltHex, expectedHash string) bool {
	saltBytes, err := hex.DecodeString(saltHex)
	if err != nil {
		return false
	}

	actualHash := hashPasswordWithSalt(password, saltBytes)
	return subtle.ConstantTimeCompare([]byte(actualHash), []byte(expectedHash)) == 1
}

func hashPasswordWithSalt(password string, salt []byte) string {
	block := append([]byte(password), salt...)
	sum := sha256.Sum256(block)
	for i := 0; i < 120000; i++ {
		round := append(sum[:], salt...)
		sum = sha256.Sum256(round)
	}
	return hex.EncodeToString(sum[:])
}

func SignJWT(secret string, claims Claims) (string, error) {
	if strings.TrimSpace(secret) == "" {
		return "", errors.New("jwt secret is required")
	}

	header := map[string]string{
		"alg": "HS256",
		"typ": "JWT",
	}

	headerBytes, err := json.Marshal(header)
	if err != nil {
		return "", err
	}

	payloadBytes, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}

	headerPart := base64.RawURLEncoding.EncodeToString(headerBytes)
	payloadPart := base64.RawURLEncoding.EncodeToString(payloadBytes)
	signingInput := headerPart + "." + payloadPart

	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(signingInput))
	signature := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))

	return signingInput + "." + signature, nil
}

func ParseJWT(secret, token string, now time.Time) (Claims, error) {
	var claims Claims

	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return claims, ErrInvalidToken
	}

	signingInput := parts[0] + "." + parts[1]
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(signingInput))
	expected := mac.Sum(nil)

	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		return claims, ErrInvalidToken
	}

	if !hmac.Equal(signature, expected) {
		return claims, ErrInvalidToken
	}

	payloadBytes, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return claims, ErrInvalidToken
	}
	if err := json.Unmarshal(payloadBytes, &claims); err != nil {
		return claims, ErrInvalidToken
	}

	if claims.Subject == "" || claims.Email == "" {
		return claims, ErrInvalidToken
	}
	if claims.Expiry <= now.Unix() {
		return claims, ErrExpiredToken
	}

	return claims, nil
}

func NewClaims(userID, email, plan string, ttl time.Duration, now time.Time) Claims {
	return Claims{
		Subject: userID,
		Email:   NormalizeEmail(email),
		Plan:    NormalizePlan(plan),
		Issued:  now.Unix(),
		Expiry:  now.Add(ttl).Unix(),
	}
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
