# Axiom

> **Token-efficient AI chat platform** — multi-tier model cascading, semantic caching, and intelligent context management to reduce LLM costs without sacrificing response quality.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Request Flow](#request-flow)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Getting Started](#getting-started)
  - [ML Service](#1-ml-service-python--fastapi)
  - [Backend](#2-backend-go)
  - [Frontend](#3-frontend-react--vite)
- [API Reference](#api-reference)
  - [Backend HTTP API](#backend-http-api-port-8080)
  - [ML Service API](#ml-service-api-port-8000)
- [ML Pipeline Deep-Dive](#ml-pipeline-deep-dive)
  - [Semantic Cache](#1-semantic-cache-two-layer-faiss)
  - [Context Classifier](#2-context-classifier)
  - [Conversation Summariser](#3-conversation-summariser)
  - [Tier Router](#4-tier-router)
  - [Prompt Optimizer](#5-prompt-optimizer)
  - [Model Cascade](#6-model-cascade)
- [Token Metrics](#token-metrics)
- [Running Tests](#running-tests)
- [Configuration Reference](#configuration-reference)

---

## Overview

Axiom is a full-stack AI chat application built around a token-reduction pipeline called **TokenMiser**. Every user message passes through a series of ML stages designed to minimise the tokens — and therefore cost — sent to large language models:

1. **Semantic cache** — identical or near-identical questions are served from a FAISS vector store, skipping the LLM entirely.
2. **Context classifier** — determines whether the conversation history is actually needed, avoiding unnecessary context injection.
3. **Conversation summariser** — periodically compresses the chat history into a compact 5-sentence summary.
4. **Tier router** — scores prompt complexity and assigns it to the cheapest model tier that can answer correctly.
5. **Prompt optimizer** — rewrites the prompt into a shorter, information-dense form before it reaches the LLM.
6. **Model cascade** — starts with a cheap model (Tier 1) and escalates only if the model signals it cannot answer.

---

## Architecture

```
┌─────────────┐      REST / JSON       ┌──────────────────────┐
│   Browser   │ ──────────────────────▶│  Go Backend (:8080)  │
│  React/Vite │ ◀──────────────────── │  Orchestrator + Auth  │
└─────────────┘                        └──────────┬───────────┘
                                                   │ HTTP (internal)
                                                   ▼
                                        ┌──────────────────────┐
                                        │  ML Service (:8000)  │
                                        │  Python / FastAPI    │
                                        │                      │
                                        │  ┌─────────────────┐ │
                                        │  │  Semantic Cache │ │
                                        │  │  (FAISS)        │ │
                                        │  └────────┬────────┘ │
                                        │           │ miss     │
                                        │  ┌────────▼────────┐ │
                                        │  │   Classifier    │ │
                                        │  │   Summariser    │ │
                                        │  │   Tier Router   │ │
                                        │  │ Prompt Optimizer│ │
                                        │  └────────┬────────┘ │
                                        │           │          │
                                        │  ┌────────▼────────┐ │
                                        │  │ Model Cascade   │ │
                                        │  │  T1: Llama 8B   │ │
                                        │  │  T2: Llama 70B  │ │
                                        │  │  T3: Gemini 2.5 │ │
                                        │  └─────────────────┘ │
                                        └──────────────────────┘
                                                   │
                                        ┌──────────▼───────────┐
                                        │     Supabase         │
                                        │  (Users, Sessions,   │
                                        │   Messages)          │
                                        └──────────────────────┘
```

---

## Request Flow

```
User sends message
      │
      ▼
Backend receives POST /chat
      │
      ├─▶ Query semantic cache (FAISS)
      │         │
      │    Cache HIT ──────────────────────────────▶ Return cached response
      │         │
      │    Cache MISS
      │         │
      ├─▶ Context classifier
      │         │  needs_context = true?
      │         │
      │    YES──▶ Load/generate conversation summary
      │         │
      ├─▶ Tier router  (scores prompt complexity → Tier 1 / 2 / 3)
      │
      ├─▶ Prompt optimizer  (compresses prompt via Llama 3.1 8B)
      │
      ├─▶ Model cascade
      │         │
      │    Tier 1 (Llama 3.1 8B)  → answers or signals CASCADE
      │    Tier 2 (Llama 3.3 70B) → answers or signals CASCADE
      │    Tier 3 (Gemini 2.5 Flash) → always answers
      │
      ├─▶ Store response in semantic cache
      │
      ├─▶ Periodic conversation summarisation (every N messages)
      │
      └─▶ Return response + token breakdown + workflow metadata
```

---

## Project Structure

```
Axiom/
├── backend/                    # Go HTTP API server
│   ├── cmd/                    # Entry point (main)
│   ├── internal/
│   │   ├── auth/               # JWT signing/validation, password hashing
│   │   ├── config/             # Environment-based configuration
│   │   ├── httpapi/            # HTTP handlers (chat, session, auth, metrics)
│   │   ├── ml/                 # HTTP client for ML Service
│   │   ├── models/             # Domain models (User, Session, Message)
│   │   ├── orchestrator/       # Core chat orchestration logic
│   │   └── session/            # Supabase-backed session/user store
│   ├── middleware/             # JWT auth middleware
│   ├── utils/
│   ├── go.mod
│   └── go.sum
│
├── frontend/                   # React + Vite SPA
│   ├── src/
│   │   ├── api/                # API client (session, chat, metrics)
│   │   ├── components/         # Chat, Message, MetricsSidebar, ThemeToggle
│   │   ├── context/            # Auth context (React Context API)
│   │   ├── hooks/              # Custom React hooks
│   │   ├── lib/                # Fetch wrapper with auth header injection
│   │   ├── pages/              # AuthPage
│   │   └── App.jsx             # Router setup
│   ├── package.json
│   └── vite.config.js
│
├── ML_Service/                 # Python FastAPI — TokenMiser pipeline
│   ├── main.py                 # App entry point + startup model warm-up
│   ├── requirement.txt         # Python dependencies
│   ├── core/
│   │   ├── cascader.py         # Two-layer semantic cache orchestration
│   │   ├── classifier.py       # Context-dependency classifier (rule-based + transformer)
│   │   ├── embedder.py         # Sentence embedding (all-MiniLM-L6-v2)
│   │   ├── FAISS_store.py      # FAISS vector store management
│   │   ├── gateway.py          # Model cascade runner + FastAPI router
│   │   ├── llm_dispatcher.py   # LLM invocation dispatcher
│   │   ├── prompt_optimizer.py # Prompt compression via Groq
│   │   ├── router_adapter.py   # Adapter between tier_router and routes
│   │   ├── summariser.py       # Conversation summarisation via Groq
│   │   └── tier_router.py      # Heuristic prompt complexity scorer
│   ├── routes/
│   │   ├── router.py           # Top-level FastAPI router aggregator
│   │   ├── cache.py            # /cache routes
│   │   ├── classify.py         # /classify route
│   │   ├── embed.py            # /embed route
│   │   ├── llm.py              # /llm/invoke route
│   │   ├── route.py            # /route route
│   │   └── summarise.py        # /summarise route
│   ├── models/                 # Pydantic request/response models
│   └── ContextClassifierMl/    # Fine-tuned transformer classifier weights
│
├── list_models.py              # Utility: list available Groq models
└── streaming_test.py           # Utility: smoke-test streaming endpoint
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18, Vite 8, React Router v6, Framer Motion, jwt-decode |
| **Backend** | Go 1.25, `golang-jwt/jwt`, `google/uuid`, `golang.org/x/crypto` |
| **ML Service** | Python 3.11+, FastAPI, Uvicorn, Pydantic v2 |
| **Embeddings** | `sentence-transformers` (all-MiniLM-L6-v2, 384d) |
| **Vector Store** | FAISS (CPU) |
| **LLM — Tier 1** | Llama 3.1 8B Instant (Groq) |
| **LLM — Tier 2** | Llama 3.3 70B Versatile (Groq) |
| **LLM — Tier 3** | Gemini 2.5 Flash Lite (Google) |
| **Classifier** | Fine-tuned HuggingFace transformer + rule-based fallback |
| **Database** | Supabase (PostgreSQL) |

---

## Prerequisites

- **Go** ≥ 1.22
- **Node.js** ≥ 18 (with npm)
- **Python** ≥ 3.11
- **Supabase** project (for user/session storage)
- **Groq API key** — [console.groq.com](https://console.groq.com)
- **Google AI / Gemini API key** — [aistudio.google.com](https://aistudio.google.com)

---

## Environment Variables

### Backend (`backend/.env` or root `.env`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `SUPABASE_URL` | ✅ | — | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | — | Supabase service-role key |
| `AXIOM_JWT_SECRET` | ✅ | — | Secret used to sign JWTs |
| `AXIOM_ML_SERVICE_URL` | — | `http://127.0.0.1:8000` | ML Service base URL |
| `AXIOM_HTTP_ADDR` | — | `:8080` | Backend listen address |
| `AXIOM_JWT_TTL_HOURS` | — | `168` (7 days) | JWT expiry in hours |
| `AXIOM_SUMMARY_INTERVAL` | — | `5` | User messages between auto-summaries |
| `AXIOM_REQUEST_TIMEOUT_SECONDS` | — | `30` | HTTP timeout for ML Service calls |

### ML Service (`ML_Service/.env`)

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | ✅ | Groq API key (Tier 1 & 2 models + optimizer + summariser) |
| `GOOGLE_API_KEY` or `GEMINI_API_KEY` | ✅ | Google / Gemini API key (Tier 3 model) |
| `AXIOM_CLASSIFIER_MODEL_PATH` | — | Override path for the fine-tuned classifier weights |
| `AXIOM_WARMUP_MODELS` | — | Set to `false` to skip model warm-up at startup (default: `true`) |
| `AXIOM_WARMUP_ROUTER` | — | Set to `false` to skip router warm-up at startup (default: `true`) |

### Frontend (`.env` at `frontend/`)

| Variable | Default | Description |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8080` | Backend base URL |

---

## Getting Started

### 1. ML Service (Python / FastAPI)

```bash
cd ML_Service

# Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirement.txt

# Create your .env file
cp .env.example .env        # or create manually — see Environment Variables above

# Start the service (development, with auto-reload)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The service exposes an interactive API explorer at **http://localhost:8000/docs**.

> **Note:** On first startup, the service pre-loads embedding and classifier models. This may take 30–60 seconds depending on hardware. Set `AXIOM_WARMUP_MODELS=false` to skip warm-up for faster iteration.

---

### 2. Backend (Go)

```bash
cd backend

# Download dependencies
go mod download

# Create your .env file in the backend directory (or the repo root)
# See Environment Variables above

# Run the server
go run ./cmd

# Or build a binary first
go build -o axiom ./cmd && ./axiom
```

The backend listens on **http://localhost:8080** by default.

---

### 3. Frontend (React / Vite)

```bash
cd frontend

# Install dependencies
npm install

# Create a .env file (optional — only needed if backend runs on a non-default port)
echo "VITE_API_URL=http://localhost:8080" > .env

# Start the development server
npm run dev

# Build for production
npm run build
```

The dev server runs at **http://localhost:5173** by default.

---

## API Reference

All backend endpoints are available both with and without the `/api` prefix (e.g. `POST /chat` and `POST /api/chat` are identical).

### Backend HTTP API (port 8080)

#### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/signup` | ❌ | Register a new user. Body: `{ email, password, plan? }` |
| `POST` | `/auth/login` | ❌ | Log in. Body: `{ email, password }`. Returns JWT. |
| `GET` | `/auth/me` | ✅ Bearer | Return current user info and chat list. |
| `POST` | `/auth/logout` | ✅ Bearer | Invalidate the session client-side. |

**Signup / Login response:**
```json
{
  "token": "<JWT>",
  "expires_at": "2026-04-23T20:53:48Z",
  "user": { "id": "...", "email": "...", "plan": "free" },
  "chats": []
}
```

#### Sessions

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/session` | ✅ Bearer | Create a new chat session. Returns `{ session_id }`. |
| `GET` | `/sessions/:id` | ✅ Bearer | Retrieve a session with full message history. |
| `GET` | `/users/:user_id/sessions` | ✅ Bearer | List all sessions (summaries) for a user. |

#### Chat

| Method | Path | Auth | Body | Description |
|---|---|---|---|---|
| `POST` | `/chat` | ✅ Bearer | `{ session_id, prompt }` | Send a message and receive a response. |

**Chat response:**
```json
{
  "response": "...",
  "model_used": "llama-3.1-8b-instant",
  "tokens_used": 142,
  "tokens_saved": 58,
  "total_tokens_used": 142,
  "cache_hit": false,
  "token_breakdown": {
    "context_summary":  { "input_tokens": 0, "output_tokens": 0, "total_tokens": 0 },
    "optimize_prompt":  { "input_tokens": 45, "output_tokens": 28, "total_tokens": 73 },
    "model_cascade":    { "input_tokens": 50, "output_tokens": 19, "total_tokens": 69 },
    "total":            { "input_tokens": 95, "output_tokens": 47, "total_tokens": 142 }
  },
  "workflow": {
    "cache_hit": false,
    "context_requested": true,
    "context_used": true,
    "tier": 1,
    "tier_reason": "Short prompt (8 tokens)",
    "models_tried": ["llama-3.1-8b-instant"],
    "cascaded": false
  }
}
```

#### Metrics

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/metrics/:session_id` | ✅ Bearer | Token usage counters for a session. |

**Metrics response:**
```json
{
  "tokens_used": 1420,
  "tokens_saved": 580,
  "cache_hits": 3,
  "cache_misses": 12,
  "cost_saved": 0.00116
}
```

#### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe. Returns `{ "status": "ok" }`. |

---

### ML Service API (port 8000)

Full interactive docs: **http://localhost:8000/docs**

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe. |
| `POST` | `/cache/query` | Semantic cache lookup (embed + FAISS search). |
| `POST` | `/cache/store` | Store a prompt-response pair in the cache. |
| `POST` | `/classify` | Classify whether a prompt needs conversation context. |
| `POST` | `/summarise` | Summarise a list of messages into 5 sentences. |
| `POST` | `/route` | Score prompt complexity → assign tier + optimize prompt. |
| `POST` | `/llm/invoke` | Run the model cascade for a given tier + prompt. |
| `POST` | `/query` | Non-streaming end-to-end cascade (for direct testing). |
| `POST` | `/query/stream` | SSE streaming cascade (for direct testing). |

---

## ML Pipeline Deep-Dive

### 1. Semantic Cache (Two-Layer FAISS)

Every prompt is embedded using **all-MiniLM-L6-v2** (384-dimensional vectors, L2-normalised) and compared against two FAISS stores using cosine similarity:

- **Global cache** — shared across all users; stores generic responses.
- **Personal cache** — per-user store; used when the prompt contains personal references (`my`, `I`, `our`, previous conversation keywords, etc.).

A prompt is served from cache when the cosine similarity exceeds the configured threshold (default: **0.82**). Cache hits skip all downstream ML calls and LLM invocations entirely.

### 2. Context Classifier

A two-stage classifier decides whether the current prompt requires prior conversation history:

1. **Transformer model** (fine-tuned on labelled conversational data, stored in `ContextClassifierMl/`) — primary classifier when model weights are present.
2. **Rule-based fallback** — 12 weighted regex signals covering anaphoric references, explicit back-references, follow-up conjunctions, interrogative fragments, and standalone-intent guards. Fires when the transformer model is unavailable.

Output: `{ needs_context: bool, confidence: float, reason: str }`

### 3. Conversation Summariser

When `needs_context = true`, the backend retrieves the stored rolling summary. If no summary exists, it calls the ML Service `/summarise` endpoint which uses **Llama 3.1 8B Instant** (Groq) to compress the conversation into exactly 5 sentences.

Periodic summarisation also runs automatically after every `AXIOM_SUMMARY_INTERVAL` (default: 5) user messages, keeping the context window lean.

### 4. Tier Router

A purely heuristic, synchronous scorer maps a prompt to one of three model tiers using seven weighted signals:

| Signal | Max pts | Examples |
|---|---|---|
| S1: Token count | 1 | Prompt length >25 words |
| S2: Reasoning keywords | 3 | `explain why`, `compare`, `analyze`, `debug` |
| S3: Technical vocabulary | 1 | `algorithm`, `API`, `latency`, `docker` |
| S4: Context attached | 2 | Summary >50 words attached |
| S5: Complex instruction framing | 1 | Imperative verb + connective phrase |
| S6: Large-source analysis | 2 | `transcript`, `document`, `full recording` |
| S7: Structured deliverable | 3 | `executive summary`, `cited evidence`, `word limit` |

**Score → Tier mapping:**
- `0–3` → Tier 1 (Llama 3.1 8B Instant — fast, cheap)
- `4–7` → Tier 2 (Llama 3.3 70B Versatile — balanced)
- `8+` → Tier 3 (Gemini 2.5 Flash Lite — frontier)

### 5. Prompt Optimizer

Before the prompt reaches the LLM, it is compressed by **Llama 3.1 8B Instant** acting as a "prompt compression engine". The optimizer removes filler words, conversational openers, and redundant phrases while preserving all constraints, facts, and intent. If a conversation summary is available, it is prepended in a structured `[CONTEXT]` block.

Typical savings: **15–40% token reduction** on verbose prompts.

### 6. Model Cascade

The cascade starts at the tier assigned by the router and attempts each model in order:

```
Tier 1 (Llama 3.1 8B) ──CASCADE?──▶ Tier 2 (Llama 3.3 70B) ──CASCADE?──▶ Tier 3 (Gemini 2.5 Flash)
```

Each Groq model is instructed: *"If this question requires complex reasoning or domain knowledge beyond your confidence, respond with only the word `CASCADE`."* The cascade runner monitors the first ~15 characters of the streaming response. If it detects `CASCADE`, the stream is aborted and the prompt escalates to the next tier — avoiding wasted tokens on partial responses.

Tier 3 (Gemini) never cascades; it always answers.

---

## Token Metrics

Every chat response includes a full token accounting broken down by pipeline stage:

| Stage | What's counted |
|---|---|
| `context_summary` | Tokens used to generate/refresh the conversation summary |
| `optimize_prompt` | Tokens consumed by the prompt optimizer (input prompt → compressed prompt) |
| `model_cascade` | Tokens used by the final answering model (and any cascade attempts) |
| `total` | Sum of all the above |

The `tokens_saved` field in the response reflects both prompt-optimizer savings and summarisation savings. The `/metrics/:session_id` endpoint accumulates these counters across the lifetime of a session.

---

## Running Tests

### Backend

```bash
cd backend
go test ./...
```

### ML Service

```bash
cd ML_Service
# Using pytest if test files are present
python -m pytest

# Quick smoke test for the cascade gateway
python core/gateway.py test
```

### Frontend

```bash
cd frontend
npm run build   # Type-checks and bundles; fails on errors
```

---

## Configuration Reference

| Variable | Service | Default | Notes |
|---|---|---|---|
| `AXIOM_HTTP_ADDR` | Backend | `:8080` | Also respects `PORT` env var |
| `AXIOM_ML_SERVICE_URL` | Backend | `http://127.0.0.1:8000` | Internal ML Service URL |
| `AXIOM_JWT_SECRET` | Backend | *(required)* | Min recommended length: 32 chars |
| `AXIOM_JWT_TTL_HOURS` | Backend | `168` | Token TTL in hours (168 = 7 days) |
| `AXIOM_SUMMARY_INTERVAL` | Backend | `5` | Auto-summarise every N user messages |
| `AXIOM_REQUEST_TIMEOUT_SECONDS` | Backend | `30` | ML Service HTTP timeout |
| `SUPABASE_URL` | Backend | *(required)* | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend | *(required)* | Service role key (bypasses RLS) |
| `GROQ_API_KEY` | ML Service | *(required)* | Groq API key |
| `GOOGLE_API_KEY` | ML Service | *(required)* | Google AI / Gemini key |
| `AXIOM_CLASSIFIER_MODEL_PATH` | ML Service | `ContextClassifierMl/my_custom_router_native` | Path override for classifier weights |
| `AXIOM_WARMUP_MODELS` | ML Service | `true` | Pre-load models at startup |
| `AXIOM_WARMUP_ROUTER` | ML Service | `true` | Pre-load tier router at startup |
| `VITE_API_URL` | Frontend | `http://localhost:8080` | Backend URL for browser requests |