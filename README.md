# Axiom Backend (Go) Documentation

This document describes the Go backend in `backend/`: architecture, API endpoints, database interaction, configuration, and what each backend Go file is responsible for.

## Backend Overview

The Go backend starts from:

- `backend/cmd/api/main.go`

Runtime flow:

1. Load configuration (`internal/config`).
2. Create HTTP client with configured timeout.
3. Create ML service client (`internal/ml`).
4. Create session store:
   - Supabase-backed (`internal/session/supabase_store.go`) when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set.
   - In-memory fallback (`internal/session/store.go`) otherwise.
5. Build orchestrator service (`internal/orchestrator/service.go`).
6. Register HTTP routes (`internal/httpapi/handler.go`) and start server.

## API Endpoints

Routes are exposed both **with and without `/api` prefix**:

- `/health` and `/api/health`
- `/session` and `/api/session`
- `/chat` and `/api/chat`
- `/metrics/{session_id}` and `/api/metrics/{session_id}`

### `GET /health`

- Purpose: service health check.
- Response: `200 OK`
  - `{ "status": "ok" }`

### `POST /session`

- Purpose: create a new chat session.
- Request body (optional):
  - `{ "user_id": "user-123" }`
- Response: `201 Created`
  - `{ "session_id": "<generated_id>" }`

### `POST /chat`

- Purpose: send user prompt in a session and get assistant response.
- Request body:
  - `{ "session_id": "<session_id>", "prompt": "<text>" }`
- Response: `200 OK` with:
  - `response`, `model_used`
  - token metrics (`tokens_used`, `tokens_saved`, `total_tokens_used`, `token_breakdown`)
  - workflow metadata (`cache_hit`, `workflow`)
- Error patterns:
  - `400` for invalid JSON or empty prompt
  - `404` if session not found
  - `502` for upstream ML-service failures

### `GET /metrics/{session_id}`

- Purpose: fetch per-session usage metrics.
- Response: `200 OK`
  - `tokens_used`, `tokens_saved`, `cache_hits`, `cache_misses`, `cost_saved`
- Errors:
  - `400` invalid/missing session id
  - `404` if session not found

## ML Service Interaction

The backend calls Python ML endpoints through `internal/ml/client.go`:

- `GET /health`
- `POST /classify/`
- `POST /summarise/`
- `POST /cache/query`
- `POST /cache/store`
- `POST /route`
- `POST /llm/invoke`

The orchestrator (`internal/orchestrator/service.go`) manages this sequence:

1. Append user message.
2. Query semantic cache.
3. If cache miss, classify prompt for context need.
4. Build/refresh summary when needed.
5. Route prompt to tier.
6. Invoke model via cascade.
7. Store assistant response and metrics.
8. Persist session and messages.

## Database and Persistence

### In-Memory Store (default fallback)

- File: `internal/session/store.go`
- Uses Go map + mutexes.
- Data is process-local and lost on restart.

### Supabase Store (persistent)

- File: `internal/session/supabase_store.go`
- Uses Supabase REST API with API key auth headers.
- Upserts sessions and messages.

Expected tables:

1. `chat_sessions`
   - `id`, `user_id`, `summary`, `summarized_message_count`
   - `tokens_used`, `tokens_saved`, `cache_hits`, `cache_misses`, `cost_saved`
   - `created_at`, `updated_at`
2. `chat_messages`
   - `id`, `session_id`, `role`, `content`, `created_at`

## Configuration (Environment Variables)

Defined in `internal/config/config.go`:

- `AXIOM_HTTP_ADDR` (default `:8080`)
- `AXIOM_ML_SERVICE_URL` (default `http://127.0.0.1:8000`)
- `AXIOM_SUMMARY_INTERVAL` (default `5`)
- `AXIOM_REQUEST_TIMEOUT_SECONDS` (default `30`)
- `SUPABASE_URL` (optional; enables Supabase store when combined with key)
- `SUPABASE_SERVICE_ROLE_KEY` (optional; enables Supabase store when combined with URL)

## Backend File-by-File Reference (Go)

### Entry point

- `backend/cmd/api/main.go`  
  Bootstraps config, dependencies, storage mode, HTTP routes, and server lifecycle.

### HTTP layer

- `backend/internal/httpapi/handler.go`  
  HTTP routing, request parsing, response serialization, error mapping, CORS handling.

### Orchestration layer

- `backend/internal/orchestrator/service.go`  
  Core chat flow, cache/classify/summary/route/invoke pipeline, session metrics, and persistence orchestration.

- `backend/internal/orchestrator/locker.go`  
  Per-session lock management to keep concurrent writes safe.

- `backend/internal/orchestrator/service_test.go`  
  Unit tests for summary behavior, context behavior, session creation, and concurrent chat correctness.

### ML integration

- `backend/internal/ml/client.go`  
  Typed request/response models and HTTP client methods for ML service endpoints.

### Session + persistence

- `backend/internal/session/store.go`  
  In-memory `SessionStore` implementation.

- `backend/internal/session/supabase_store.go`  
  Supabase-backed `SessionStore` implementation for persistent chat sessions/messages.

- `backend/internal/session/id.go`  
  Session/message ID generation (crypto-random hex, with timestamp fallback).

- `backend/internal/session/store.go` + `supabase_store.go`  
  Both implement the same store contract consumed by orchestrator.

### Shared models/config

- `backend/internal/models/chat.go`  
  Core domain models (`Message`, `Session`, `SessionMetrics`).

- `backend/internal/config/config.go`  
  Centralized environment-based configuration loading.

## Local Backend Commands

From `backend/`:

- Run tests:
  - `go test ./...`
- Run API:
  - `go run ./cmd/api`
