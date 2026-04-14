package config

import (
	"os"
	"strconv"
	"time"
)

type Config struct {
	HTTPAddr         string
	MLServiceBaseURL string
	SummaryInterval  int
	RequestTimeout   time.Duration
	SupabaseURL      string
	SupabaseKey      string
}

func Load() Config {
	return Config{
		HTTPAddr:         getEnv("AXIOM_HTTP_ADDR", ":8080"),
		MLServiceBaseURL: getEnv("AXIOM_ML_SERVICE_URL", "http://127.0.0.1:8000"),
		SummaryInterval:  getEnvInt("AXIOM_SUMMARY_INTERVAL", 5),
		RequestTimeout:   time.Duration(getEnvInt("AXIOM_REQUEST_TIMEOUT_SECONDS", 30)) * time.Second,
		SupabaseURL:      getEnv("SUPABASE_URL", ""),
		SupabaseKey:      getEnv("SUPABASE_SERVICE_ROLE_KEY", ""),
	}
}

func getEnv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}

	parsed, err := strconv.Atoi(value)
	if err != nil || parsed <= 0 {
		return fallback
	}

	return parsed
}
