package config

import (
	"bufio"
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"strings"
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
	loadDotEnv()

	return Config{
		HTTPAddr:         getHTTPAddr(),
		MLServiceBaseURL: getEnv("AXIOM_ML_SERVICE_URL", "http://127.0.0.1:8000"),
		SummaryInterval:  getEnvInt("AXIOM_SUMMARY_INTERVAL", 5),
		RequestTimeout:   time.Duration(getEnvInt("AXIOM_REQUEST_TIMEOUT_SECONDS", 30)) * time.Second,
		SupabaseURL:      getEnv("SUPABASE_URL", ""),
		SupabaseKey:      getEnv("SUPABASE_SERVICE_ROLE_KEY", ""),
	}
}

func (c Config) Validate() error {
	if strings.TrimSpace(c.SupabaseURL) == "" {
		return errors.New("SUPABASE_URL is required")
	}
	if strings.TrimSpace(c.SupabaseKey) == "" {
		return errors.New("SUPABASE_SERVICE_ROLE_KEY is required")
	}
	return nil
}

func getHTTPAddr() string {
	if value := os.Getenv("AXIOM_HTTP_ADDR"); value != "" {
		return value
	}
	if port := os.Getenv("PORT"); port != "" {
		return ":" + port
	}
	return ":8080"
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

func loadDotEnv() {
	for _, path := range dotEnvPaths() {
		if loadDotEnvFile(path) == nil {
			return
		}
	}
}

func dotEnvPaths() []string {
	cwd, err := os.Getwd()
	if err != nil {
		return []string{".env"}
	}

	return []string{
		filepath.Join(cwd, ".env"),
		filepath.Join(cwd, "backend", ".env"),
	}
}

func loadDotEnvFile(path string) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		key, value, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}

		key = cleanDotEnvPart(key)
		value = cleanDotEnvPart(value)
		if key == "" {
			continue
		}
		if _, exists := os.LookupEnv(key); exists {
			continue
		}
		_ = os.Setenv(key, value)
	}

	return scanner.Err()
}

func cleanDotEnvPart(value string) string {
	value = strings.TrimSpace(value)
	value = strings.Trim(value, `"'`)
	return value
}
