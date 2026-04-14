package main

import (
	"log"
	"net/http"
	"time"

	"axiom/backend/internal/config"
	"axiom/backend/internal/httpapi"
	"axiom/backend/internal/ml"
	"axiom/backend/internal/orchestrator"
	"axiom/backend/internal/session"
)

func main() {
	cfg := config.Load()

	httpClient := &http.Client{
		Timeout: cfg.RequestTimeout,
	}

	mlClient := ml.NewClient(cfg.MLServiceBaseURL, httpClient)
	var store orchestrator.SessionStore
	if cfg.SupabaseURL != "" && cfg.SupabaseKey != "" {
		supabaseStore, err := session.NewSupabaseStore(cfg.SupabaseURL, cfg.SupabaseKey, httpClient)
		if err != nil {
			log.Fatalf("supabase store init failed: %v", err)
		}
		store = supabaseStore
		log.Printf("session store: supabase")
	} else {
		store = session.NewStore()
		log.Printf("session store: in-memory fallback")
	}
	service := orchestrator.NewService(store, mlClient, cfg)
	handler := httpapi.NewHandler(service)

	server := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           handler.Routes(),
		ReadHeaderTimeout: 5 * time.Second,
	}

	log.Printf("axiom backend listening on %s", cfg.HTTPAddr)
	log.Printf("python ml service base url: %s", cfg.MLServiceBaseURL)

	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("server failed: %v", err)
	}
}
