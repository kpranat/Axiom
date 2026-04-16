package main

import (
	"log"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"strings"
	"time"

	"axiom/backend/internal/config"
	"axiom/backend/internal/httpapi"
	"axiom/backend/internal/ml"
	"axiom/backend/internal/orchestrator"
	"axiom/backend/internal/session"
)

func main() {
	cfg := config.Load()
	if err := cfg.Validate(); err != nil {
		log.Fatalf("config error: %v. Set these in Koyeb environment variables or backend/.env for local runs", err)
	}

	httpClient := &http.Client{
		Timeout: cfg.RequestTimeout,
	}

	mlClient := ml.NewClient(cfg.MLServiceBaseURL, httpClient)
	store, err := session.NewSupabaseStore(cfg.SupabaseURL, cfg.SupabaseKey, httpClient)
	if err != nil {
		log.Fatalf("supabase store init failed: %v", err)
	}
	log.Printf("session store: supabase")

	service := orchestrator.NewService(store, mlClient, cfg)
	handler := httpapi.NewHandler(service, cfg)
	serverHandler := handler.Routes()

	if frontendDist, ok := resolveFrontendDist(); ok {
		serverHandler = withFrontend(serverHandler, frontendDist)
		log.Printf("frontend static serving enabled: %s", frontendDist)
	} else {
		log.Printf("frontend static serving disabled: build not found (set AXIOM_FRONTEND_DIST to override)")
	}

	server := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           serverHandler,
		ReadHeaderTimeout: 5 * time.Second,
	}

	log.Printf("axiom backend listening on %s", cfg.HTTPAddr)
	log.Printf("python ml service base url: %s", cfg.MLServiceBaseURL)

	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("server failed: %v", err)
	}
}

func resolveFrontendDist() (string, bool) {
	if configured := strings.TrimSpace(os.Getenv("AXIOM_FRONTEND_DIST")); configured != "" {
		if hasIndexFile(configured) {
			return filepath.Clean(configured), true
		}
		return "", false
	}

	cwd, err := os.Getwd()
	if err != nil {
		return "", false
	}

	current := cwd
	for {
		candidate := filepath.Join(current, "frontend", "dist")
		if hasIndexFile(candidate) {
			return filepath.Clean(candidate), true
		}

		parent := filepath.Dir(current)
		if parent == current {
			break
		}
		current = parent
	}

	return "", false
}

func hasIndexFile(distDir string) bool {
	info, err := os.Stat(filepath.Join(distDir, "index.html"))
	if err != nil {
		return false
	}
	return !info.IsDir()
}

func withFrontend(apiHandler http.Handler, distDir string) http.Handler {
	staticFiles := http.FileServer(http.Dir(distDir))
	indexFile := filepath.Join(distDir, "index.html")

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if isAPIPath(r.URL.Path) || r.Method == http.MethodOptions {
			apiHandler.ServeHTTP(w, r)
			return
		}

		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			apiHandler.ServeHTTP(w, r)
			return
		}

		cleanPath := path.Clean("/" + r.URL.Path)
		if cleanPath == "/" {
			http.ServeFile(w, r, indexFile)
			return
		}

		assetPath := filepath.Join(distDir, filepath.FromSlash(strings.TrimPrefix(cleanPath, "/")))
		if info, err := os.Stat(assetPath); err == nil && !info.IsDir() {
			staticFiles.ServeHTTP(w, r)
			return
		}

		http.ServeFile(w, r, indexFile)
	})
}

func isAPIPath(requestPath string) bool {
	switch {
	case requestPath == "/api", strings.HasPrefix(requestPath, "/api/"):
		return true
	case strings.HasPrefix(requestPath, "/auth/"):
		return true
	case requestPath == "/health", requestPath == "/session", requestPath == "/chat":
		return true
	case strings.HasPrefix(requestPath, "/sessions/"), strings.HasPrefix(requestPath, "/metrics/"), strings.HasPrefix(requestPath, "/users/"):
		return true
	default:
		return false
	}
}
