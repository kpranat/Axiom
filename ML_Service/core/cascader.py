"""
core/cascader.py
----------------
Two-layer semantic cache primitives.

Primary orchestrated flow (used by Go backend):
    1. lookup_query() -> classify + embed + global/personal cache search.
    2. On hit: return cached response.
    3. On miss: backend continues route/invoke flow.
    4. store_response() stores final model output in global or personal cache.

Legacy process_query() remains available for demos where cache miss still
falls back to a local mock LLM call.
"""

from __future__ import annotations

import numpy as np

from core.embedder import embed_all
from core.FAISS_store import cache_manager


# ──────────────────────────────────────────────────────────────────────────────
# Structured logger
# ──────────────────────────────────────────────────────────────────────────────

SEP = "─" * 60

def log(step: str, message: str) -> None:
    print(f"[{step:<12}] {message}")


# ──────────────────────────────────────────────────────────────────────────────
# Query classifier
# ──────────────────────────────────────────────────────────────────────────────

_PERSONAL_KEYWORDS = [
    "my", "i ", " i,", " i.", "me", "our",
    "account", "history", "previous",
    "you said", "earlier", "before",
    "my data", "my plan",
]


def is_personal(prompt: str) -> bool:
    """Return True when the prompt is personal / context-specific."""
    p = prompt.lower()
    if p.startswith("i ") or p == "i":
        return True
    return any(kw in p for kw in _PERSONAL_KEYWORDS)


# ──────────────────────────────────────────────────────────────────────────────
# Mock LLM
# ──────────────────────────────────────────────────────────────────────────────

def call_llm(prompt: str) -> str:
    """
    Mock LLM — replace with real OpenAI / Groq call in production.
    Prints a visible marker so demos can observe when the LLM is invoked.
    """
    log("LLM_CALL    ", f"🤖 Generating response for: \"{prompt}\"")
    response = f"[MOCK LLM] Response to: {prompt}"
    return response


def _classify_prompt(prompt: str) -> tuple[bool, str]:
    personal = is_personal(prompt)
    classification = "PERSONAL" if personal else "GENERIC"
    return personal, classification


def _format_score(score: float | None) -> str:
    if score is None:
        return "empty"
    return f"{score:.4f}"


def _log_model_scores(layer: str, results: dict[str, dict]) -> None:
    """
    Pretty-print a per-model similarity score table to the terminal.
    Example output:

      ┌─ GLOBAL COSINE SIMILARITY ──────────────────────────────────┐
      │  minilm  (all-MiniLM-L6-v2 · 384d) │ score=0.7812  MISS ❌ │
      └─────────────────────────────────────────────────────────────┘
    """
    MODEL_LABELS = {
        "minilm": "all-MiniLM-L6-v2 · 384d",
    }
    THRESHOLD = cache_manager.threshold

    print(f"  ┌─ {layer} COSINE SIMILARITY {SEP[:30]}")
    for model_key, result in results.items():
        label   = MODEL_LABELS.get(model_key, model_key)
        score   = result["score"]
        is_hit  = result["hit"]
        matched = f'  match="{result["query"]}"' if result["query"] else ""
        icon    = "HIT  ✅" if is_hit else "MISS ❌"
        score_s = _format_score(score)
        print(f"  │  {model_key:<8} ({label}) │ score={score_s}  {icon}{matched}")
    print(f"  │  threshold = {THRESHOLD}")
    print(f"  └{'─' * 55}")


def lookup_query(prompt: str, user_id: str) -> dict:
    """
    Cache-only lookup path used by service orchestration.

    Returns:
      {
        "cache_hit": bool,
        "response": str | None,
        "cache_layer": "global" | "personal" | "miss",
        "classified": "PERSONAL" | "GENERIC",
        "score": float | None,
      }
    """

    print(f"\n  {SEP}")
    log("REQUEST     ", f"\"{prompt}\"  [user={user_id}]")

    personal, classification = _classify_prompt(prompt)
    log("CLASSIFY    ", classification)

    log("EMBED       ", "Generating embeddings with minilm (all-MiniLM-L6-v2) ...")
    embeddings = embed_all(prompt)

    log("CACHE_CHECK ", "GLOBAL")
    global_results = cache_manager.search_global_all(embeddings)
    _log_model_scores("GLOBAL", global_results)
    global_hit = cache_manager.best_hit(global_results)
    if global_hit:
        log("CACHE_HIT   ", f"GLOBAL ✅  model={global_hit['model']}  score={global_hit['score']}")
        print(f"  │  [SIMILARITY] cosine={global_hit['score']:.4f}  threshold={cache_manager.threshold}  → HIT ✅")
        print(f"  {SEP}\n")
        return {
            "cache_hit": True,
            "response": global_hit["response"],
            "cache_layer": "global",
            "classified": classification,
            "score": global_hit["score"],
            "model_used": global_hit["model"],
            "model_scores": {model: result["score"] for model, result in global_results.items()},
        }

    log("CACHE_MISS  ", "GLOBAL ❌")

    log("CACHE_CHECK ", "PERSONAL")
    personal_results = cache_manager.search_personal_all(user_id, embeddings)
    _log_model_scores("PERSONAL", personal_results)
    personal_hit = cache_manager.best_hit(personal_results)
    if personal_hit:
        log("CACHE_HIT   ", f"PERSONAL ✅  model={personal_hit['model']}  score={personal_hit['score']}")
        print(f"  │  [SIMILARITY] cosine={personal_hit['score']:.4f}  threshold={cache_manager.threshold}  → HIT ✅")
        print(f"  {SEP}\n")
        return {
            "cache_hit": True,
            "response": personal_hit["response"],
            "cache_layer": "personal",
            "classified": classification,
            "score": personal_hit["score"],
            "model_used": personal_hit["model"],
            "model_scores": {model: result["score"] for model, result in personal_results.items()},
        }

    log("CACHE_MISS  ", "PERSONAL ❌ — full miss, forwarding to LLM")
    # Print best raw similarity score on a full miss so it's visible in terminal
    best_miss_score = global_results.get("minilm", {}).get("score")
    score_s = _format_score(best_miss_score)
    print(f"  │  [SIMILARITY] cosine={score_s}  threshold={cache_manager.threshold}  → MISS ❌")
    print(f"  {SEP}\n")
    flat_miss_scores = {model: result["score"] for model, result in global_results.items()}
    return {
        "cache_hit": False,
        "response": None,
        "cache_layer": "miss",
        "classified": classification,
        "score": None,
        "model_used": None,
        "model_scores": flat_miss_scores,
    }


def store_response(
    prompt: str,
    user_id: str,
    response: str,
    classified: str | None = None,
) -> dict:
    """
    Store a final model response in the appropriate cache layer.
    """
    if classified in {"PERSONAL", "GENERIC"}:
        classification = classified
        personal = classified == "PERSONAL"
    else:
        personal, classification = _classify_prompt(prompt)

    log("CLASSIFY    ", f"{classification} (store)")
    log("EMBED       ", "Generating embeddings for store with minilm (all-MiniLM-L6-v2) ...")
    embeddings = embed_all(prompt)

    if personal:
        cache_manager.store_personal_all(user_id, embeddings, prompt, response)
        log("STORE       ", f"PERSONAL  [user={user_id}]")
        stored_layer = "personal"
    else:
        cache_manager.store_global_all(embeddings, prompt, response)
        log("STORE       ", "GLOBAL")
        stored_layer = "global"

    print()
    return {
        "status": "ok",
        "message": "Response stored in semantic cache.",
        "stored_layer": stored_layer,
        "models_stored": sorted(embeddings),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Debug: side-by-side similarity between two prompts
# ──────────────────────────────────────────────────────────────────────────────

def debug_similarity(prompt_a: str, prompt_b: str) -> dict:
    """
    Compute and display cosine similarity between two prompts for every
    configured embedding model.  Useful for threshold calibration.

    Returns:
      {
        "prompt_a": str,
        "prompt_b": str,
        "similarity": {
          "minilm": float,
        },
        "threshold": float,
        "would_hit": {
          "minilm": bool,
        },
      }
    """
    MODEL_LABELS = {
        "minilm": "all-MiniLM-L6-v2 · 384d",
    }
    THRESHOLD = cache_manager.threshold

    print(f"\n  {SEP}")
    log("DBG_SIM     ", f'Comparing prompts:')
    log("DBG_SIM     ", f'  A: "{prompt_a}"')
    log("DBG_SIM     ", f'  B: "{prompt_b}"')

    embeddings_a = embed_all(prompt_a)
    embeddings_b = embed_all(prompt_b)

    similarities: dict[str, float] = {}
    would_hit: dict[str, bool] = {}

    print(f"  ┌─ COSINE SIMILARITY COMPARISON {SEP[:25]}")
    for model_key in embeddings_a:
        vec_a = embeddings_a[model_key].astype(np.float64)
        vec_b = embeddings_b[model_key].astype(np.float64)
        # Vectors are already L2-normalised; dot product == cosine similarity
        score = float(np.dot(vec_a, vec_b))
        score = round(score, 4)
        hit = score >= THRESHOLD
        similarities[model_key] = score
        would_hit[model_key] = hit
        label = MODEL_LABELS.get(model_key, model_key)
        icon  = "HIT  ✅" if hit else "MISS ❌"
        print(f"  │  {model_key:<8} ({label}) │ score={score:.4f}  {icon}")
    print(f"  │  threshold = {THRESHOLD}")
    print(f"  └{'─' * 55}")
    print(f"  {SEP}\n")

    return {
        "prompt_a": prompt_a,
        "prompt_b": prompt_b,
        "similarity": similarities,
        "threshold": THRESHOLD,
        "would_hit": would_hit,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main cascade
# ──────────────────────────────────────────────────────────────────────────────

def process_query(prompt: str, user_id: str) -> dict:
    """
    Execute the full two-layer semantic cache flow and return a result dict:
      {
        "response"   : str,
        "cache_layer": "global" | "personal" | "miss",
        "classified" : "PERSONAL" | "GENERIC",
        "score"      : float | None,
      }
    """

    lookup = lookup_query(prompt, user_id)
    if lookup["cache_hit"]:
        return lookup

    response = call_llm(prompt)
    store_response(prompt, user_id, response, lookup.get("classified"))

    return {
        "cache_hit": False,
        "response": response,
        "cache_layer": "miss",
        "classified": lookup["classified"],
        "score": None,
        "model_used": None,
        "model_scores": lookup.get("model_scores"),
    }
