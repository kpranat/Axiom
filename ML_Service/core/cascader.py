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

from core.embedder import embed
from core.FAISS_store import cache_manager


# ──────────────────────────────────────────────────────────────────────────────
# Structured logger
# ──────────────────────────────────────────────────────────────────────────────

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

    log("REQUEST     ", f"\"{prompt}\"  [user={user_id}]")

    personal, classification = _classify_prompt(prompt)
    log("CLASSIFY    ", classification)

    log("EMBED       ", "Generating embedding ...")
    embedding: np.ndarray = embed(prompt)

    log("CACHE_CHECK ", "GLOBAL")
    global_hit = cache_manager.search_global(embedding)
    if global_hit:
        log("CACHE_HIT   ", f"GLOBAL ✅  (score={global_hit['score']})")
        return {
            "cache_hit": True,
            "response": global_hit["response"],
            "cache_layer": "global",
            "classified": classification,
            "score": global_hit["score"],
        }

    log("CACHE_MISS  ", "GLOBAL ❌")

    log("CACHE_CHECK ", "PERSONAL")
    personal_hit = cache_manager.search_personal(user_id, embedding)
    if personal_hit:
        log("CACHE_HIT   ", f"PERSONAL ✅  (score={personal_hit['score']})")
        return {
            "cache_hit": True,
            "response": personal_hit["response"],
            "cache_layer": "personal",
            "classified": classification,
            "score": personal_hit["score"],
        }

    log("CACHE_MISS  ", "PERSONAL ❌")
    return {
        "cache_hit": False,
        "response": None,
        "cache_layer": "miss",
        "classified": classification,
        "score": None,
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
    log("EMBED       ", "Generating embedding for store ...")
    embedding: np.ndarray = embed(prompt)

    if personal:
        cache_manager.store_personal(user_id, embedding, prompt, response)
        log("STORE       ", f"PERSONAL  [user={user_id}]")
        stored_layer = "personal"
    else:
        cache_manager.store_global(embedding, prompt, response)
        log("STORE       ", "GLOBAL")
        stored_layer = "global"

    print()
    return {
        "status": "ok",
        "message": "Response stored in semantic cache.",
        "stored_layer": stored_layer,
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
    }
