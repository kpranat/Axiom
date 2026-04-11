"""
core/cascader.py
----------------
Two-layer semantic cache cascade logic.

Flow (for every query):
  1.  Classify  -> PERSONAL | GENERIC
  2.  Embed     (single embedding, reused throughout)
  3.  Check GLOBAL cache
  4.  If MISS -> check PERSONAL cache
  5.  If MISS -> call LLM mock
  6.  Store: GLOBAL if generic, PERSONAL if personal

All observable decisions are printed via log().
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

    # ── 1. LOG REQUEST ────────────────────────────────────────────────────────
    log("REQUEST     ", f"\"{prompt}\"  [user={user_id}]")

    # ── 2. CLASSIFY ───────────────────────────────────────────────────────────
    personal = is_personal(prompt)
    classification = "PERSONAL" if personal else "GENERIC"
    log("CLASSIFY    ", classification)

    # ── 3. EMBED (once) ───────────────────────────────────────────────────────
    log("EMBED       ", "Generating embedding ...")
    embedding: np.ndarray = embed(prompt)

    # ── 4. GLOBAL CACHE CHECK ─────────────────────────────────────────────────
    log("CACHE_CHECK ", "GLOBAL")
    global_hit = cache_manager.search_global(embedding)

    if global_hit:
        log("CACHE_HIT   ", f"GLOBAL ✅  (score={global_hit['score']})")
        return {
            "response": global_hit["response"],
            "cache_layer": "global",
            "classified": classification,
            "score": global_hit["score"],
        }

    log("CACHE_MISS  ", "GLOBAL ❌")

    # ── 5. PERSONAL CACHE CHECK ───────────────────────────────────────────────
    log("CACHE_CHECK ", "PERSONAL")
    personal_hit = cache_manager.search_personal(user_id, embedding)

    if personal_hit:
        log("CACHE_HIT   ", f"PERSONAL ✅  (score={personal_hit['score']})")
        return {
            "response": personal_hit["response"],
            "cache_layer": "personal",
            "classified": classification,
            "score": personal_hit["score"],
        }

    log("CACHE_MISS  ", "PERSONAL ❌")

    # ── 6. LLM CALL ───────────────────────────────────────────────────────────
    response = call_llm(prompt)

    # ── 7. STORE ──────────────────────────────────────────────────────────────
    if personal:
        cache_manager.store_personal(user_id, embedding, prompt, response)
        log("STORE       ", f"PERSONAL  [user={user_id}]")
    else:
        cache_manager.store_global(embedding, prompt, response)
        log("STORE       ", "GLOBAL")

    print()  # blank separator between requests in the terminal

    return {
        "response": response,
        "cache_layer": "miss",
        "classified": classification,
        "score": None,
    }
