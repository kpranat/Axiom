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
	store := session.NewStore()
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
