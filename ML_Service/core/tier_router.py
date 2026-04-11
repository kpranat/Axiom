"""
core/tier_router.py
-------------------
Heuristic-based tier router for model cascading.

Given a user prompt (and an optional pre-summarised context string), assigns
the prompt to one of three model tiers:

  Tier 1 — simple, factual, single-turn  (small / fast model)
  Tier 2 — moderate reasoning, context   (mid-size model)
  Tier 3 — complex, long, multi-doc      (large / frontier model)

Algorithm
---------
Five weighted signals are evaluated:

  S1  Token count of prompt            (0–3 pts, scaled by length)
  S2  Reasoning keywords               (+2 pts)
  S3  Technical / domain vocabulary    (+1 pt)
  S4  Context attached and long        (+2 pts)
  S5  Complex instruction framing      (+1 pt)

Score → Tier
  0–3  →  Tier 1
  4–7  →  Tier 2
  8 +  →  Tier 3

No external calls are made; this module is fully synchronous.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RouteResult:
    """Immutable result returned by the tier router."""
    tier: int              # 1 | 2 | 3
    score: int             # raw accumulated signal score
    reason: str            # human-readable explanation of the dominant signal


# ──────────────────────────────────────────────────────────────────────────────
# Signal patterns (compiled once at import)
# ──────────────────────────────────────────────────────────────────────────────

def _c(pattern: str) -> re.Pattern:
    """Compile a case-insensitive Unicode pattern."""
    return re.compile(pattern, re.IGNORECASE | re.UNICODE)


# S2 — reasoning / analytical keywords
_REASONING = _c(
    r"\b("
    r"explain\s+why|explain\s+how|why\s+does|how\s+does|"
    r"compare|contrast|versus|vs\.?|"
    r"analy[sz]e|analy[sz]is|evaluate|evaluation|"
    r"critique|critically|assess|assessment|"
    r"justify|justify\s+your|reasoning|reason\s+through|"
    r"pros\s+and\s+cons|trade[\s-]?offs?|"
    r"what\s+are\s+the\s+(implications|consequences|effects|impacts)|"
    r"step[\s-]by[\s-]step|walk\s+me\s+through|break\s+it\s+down"
    r")\b"
)

# S3 — technical / domain vocabulary
_TECHNICAL = _c(
    r"\b("
    r"algorithm|algorithms|"
    r"architect(?:ure|ural)|"
    r"implement(?:ation|ing|ed)?|"
    r"optim[iu][sz](?:e|ation|ing|ed)|"
    r"framework|infrastructure|pipeline|"
    r"latency|throughput|scalab(?:le|ility)|"
    r"complexit(?:y|ies)|big[\s-]o|"
    r"database|schema|query|endpoint|"
    r"machine\s+learning|neural\s+network|model|embedding|"
    r"refactor|deploy(?:ment|ing)?|containeris|docker|kubernetes"
    r")\b"
)

# S5 — complex instruction framing
# Starts with an imperative verb AND contains connective complexity markers
_IMPERATIVE_START = _c(
    r"^(write|create|build|design|generate|develop|"
    r"draft|produce|construct|implement|make|set\s+up|"
    r"explain|describe|outline|summarise|summarize|list|"
    r"compare|analyse|analyze|evaluate|critique)"
)

_COMPLEXITY_CONNECTIVE = _c(
    r"\b(considering|given\s+that|such\s+that|while\s+also|"
    r"but\s+(also|ensure|make\s+sure)|however|"
    r"in\s+addition\s+to|as\s+well\s+as|"
    r"taking\s+into\s+account|with\s+the\s+constraint|"
    r"that\s+(also|still|additionally)|"
    r"and\s+(also|additionally|furthermore))\b"
)


# ──────────────────────────────────────────────────────────────────────────────
# Scoring helpers
# ──────────────────────────────────────────────────────────────────────────────

_CONTEXT_LONG_THRESHOLD = 50   # words in context to trigger S4
_TIER_BOUNDARIES = (4, 7)      # [Tier1 < 4], [4 <= Tier2 < 7], [Tier3 >= 7]


def _score_token_count(prompt: str) -> tuple[int, str]:
    """
    S1: Score based on the token count (whitespace-split) of the prompt.

    ≤ 15 tokens  → 0 pts  (trivially short)
    16–40 tokens → 1 pt
    41–80 tokens → 2 pts
    > 80 tokens  → 3 pts
    """
    n = len(prompt.split())
    if n <= 15:
        return 0, f"Short prompt ({n} tokens)"
    elif n <= 40:
        return 1, f"Medium-length prompt ({n} tokens)"
    elif n <= 80:
        return 2, f"Long prompt ({n} tokens)"
    else:
        return 3, f"Very long prompt ({n} tokens)"


def _score_reasoning(prompt: str) -> tuple[int, str]:
    """S2: +2 if any reasoning/analytical keyword is detected."""
    if _REASONING.search(prompt):
        match = _REASONING.search(prompt)
        return 2, f"Reasoning keyword detected: '{match.group().strip()}'"
    return 0, ""


def _score_technical(prompt: str) -> tuple[int, str]:
    """S3: +1 if technical/domain vocabulary is detected."""
    if _TECHNICAL.search(prompt):
        match = _TECHNICAL.search(prompt)
        return 1, f"Technical vocabulary detected: '{match.group().strip()}'"
    return 0, ""


def _score_context(context: Optional[str]) -> tuple[int, str]:
    """S4: +2 if a non-trivial context string is attached (> 50 words)."""
    if context and len(context.split()) > _CONTEXT_LONG_THRESHOLD:
        return 2, f"Long context attached ({len(context.split())} words)"
    if context:
        return 1, "Short context attached"
    return 0, ""


def _score_instruction_framing(prompt: str) -> tuple[int, str]:
    """S5: +1 if prompt starts with an imperative verb AND has complex connectives."""
    stripped = prompt.strip()
    if _IMPERATIVE_START.match(stripped) and _COMPLEXITY_CONNECTIVE.search(stripped):
        return 1, "Complex imperative instruction with connectives"
    return 0, ""


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def route(prompt: str, context: Optional[str] = None) -> RouteResult:
    """
    Assign the prompt to a model tier.

    Args:
        prompt:  The user's (raw or pre-processed) message.
        context: Optional pre-summarised conversation context string
                 (output of the /summarise endpoint).

    Returns:
        RouteResult with tier (1|2|3), raw score, and primary reason.
    """
    if not prompt or not prompt.strip():
        return RouteResult(tier=1, score=0, reason="Empty prompt — defaulting to Tier 1")

    # Accumulate scores from all five signals
    signals: list[tuple[int, str]] = [
        _score_token_count(prompt),
        _score_reasoning(prompt),
        _score_technical(prompt),
        _score_context(context),
        _score_instruction_framing(prompt),
    ]

    total_score = sum(pts for pts, _ in signals)

    # Pick the most informative non-empty reason (highest point signal)
    best_reason = max(
        ((pts, reason) for pts, reason in signals if reason),
        default=(0, "No strong signals detected"),
    )[1]

    # Map score to tier
    low, high = _TIER_BOUNDARIES
    if total_score < low:
        tier = 1
    elif total_score < high:
        tier = 2
    else:
        tier = 3

    return RouteResult(tier=tier, score=total_score, reason=best_reason)
