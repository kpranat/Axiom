"""
core/classifier.py
~~~~~~~~~~~~~~~~~~
Pure-Python, zero-dependency context-dependency classifier.

Decides whether a user's latest prompt REQUIRES prior conversation context
to be understood correctly.  No LLM, no model weights — rule-based only.

Algorithm
---------
1. Compile a set of weighted regex Signals at module load (once).
2. For each incoming prompt, scan every Signal and accumulate a raw score.
3. Map the raw score to (needs_context: bool, confidence: float, reason: str).

Threshold: score >= 4  →  needs_context = True
Weights are intentionally kept small; see _SIGNALS for rationale.
"""

import re
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Signal dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Signal:
    """A single heuristic rule with an associated weight and human-readable label."""
    pattern: re.Pattern
    weight: int
    label: str


# ---------------------------------------------------------------------------
# Signal definitions
# ---------------------------------------------------------------------------

def _compile(pattern: str) -> re.Pattern:
    """Compile a case-insensitive, Unicode-aware pattern."""
    return re.compile(pattern, re.IGNORECASE | re.UNICODE)


_SIGNALS: list[Signal] = [

    # ── 1. Bare pronoun references ──────────────────────────────────────────
    # "it", "they", "them", "their", "those", "these", "its"
    # Exclude "this is …" / "that is …" sentence starters (introductory use).
    # Exclude common idioms: "it is", "it's" at sentence start are usually NOT anaphoric
    Signal(
        pattern=_compile(
            r"(?<!\bthis )\b(it|they|them|their|its|those|these)\b"
            r"(?!\s+is\b)(?!\s*'s\b)"
        ),
        weight=3,
        label="Bare pronoun reference (it/they/them/their/its/those/these)",
    ),

    # ── 2. Singular demonstrative — "that" as standalone reference ──────────
    # "that one", "that role", "that company" but NOT "that is" / "is that"
    Signal(
        pattern=_compile(
            r"\bthat\s+(?!is\b|was\b|will\b|would\b|could\b|should\b|are\b)"
            r"(?:one|role|job|company|position|offer|listing|option|thing|place|"
            r"part|point|section|idea|application|post|opening|opportunity|salary|"
            r"package|profile|resume|cv|college|university|course|branch|stream)\b"
        ),
        weight=3,
        label="Singular demonstrative + vague noun (that job/role/company…)",
    ),

    # ── 3. Definite anaphoric noun phrase ───────────────────────────────────
    # "the one", "the role", "the previous", "the last", "the same"
    Signal(
        pattern=_compile(
            r"\bthe\s+(one|previous|last|same|other|first|second|third|"
            r"aforementioned|above|mentioned|role|job|company|listing|offer|"
            r"option|position|opening|opportunity|application|profile)\b"
        ),
        weight=3,
        label="Definite anaphoric noun phrase (the one / the role / the previous…)",
    ),

    # ── 4. Explicit back-reference phrase ───────────────────────────────────
    # Strongest signal — speaker directly cites a prior exchange.
    Signal(
        pattern=_compile(
            r"\b(you mentioned|you said|you told|as (you |we )?(mentioned|said|discussed)|"
            r"like (I|you|we) said|as before|like before|as discussed|"
            r"what you (said|mentioned|told|described)|"
            r"the one you (talked|spoke|mentioned|said|described)|"
            r"from (earlier|before|last time|our (last|previous) conversation))\b"
        ),
        weight=4,
        label="Explicit back-reference (you mentioned / as discussed / as before…)",
    ),

    # ── 5. Follow-up conjunction / adverb at sentence start ─────────────────
    # "Also, …", "Additionally, …", "Furthermore, …" at START of message.
    Signal(
        pattern=_compile(
            r"^(also|additionally|furthermore|besides|moreover|"
            r"as well|what else|in addition|on top of that|"
            r"other than that)[,\s]"
        ),
        weight=4,
        label="Follow-up conjunction/adverb at sentence start (also / additionally…)",
    ),

    # ── 6. Continuation / elaboration request ───────────────────────────────
    # "Tell me more", "expand on that", "go on", "elaborate"
    Signal(
        pattern=_compile(
            r"\b(tell me more|expand on (that|it|this)|more (details|info|information)|"
            r"go on|keep going|elaborate|give me more|can you (expand|elaborate)|"
            r"explain (further|more|that)|what else|continue)\b"
        ),
        weight=4,
        label="Continuation/elaboration request (tell me more / expand on that…)",
    ),

    # ── 7. Comparative reference ────────────────────────────────────────────
    # "similar to that", "same as before", "better than the first"
    Signal(
        pattern=_compile(
            r"\b(similar to (that|it|this|the (one|other|previous|last))|"
            r"same as (before|that|the (other|previous|last|first))|"
            r"unlike the (other|first|second|last|previous)|"
            r"better than (that|the (first|other|previous|last))|"
            r"compared to (that|it|the (other|previous|last)))\b"
        ),
        weight=2,
        label="Comparative reference (similar to that / same as before…)",
    ),

    # ── 8. Interrogative fragment (short question lacking a subject) ─────────
    # e.g. "Why not?", "How so?", "What about it?", "Really?"
    # Detected structurally: ≤ 6 tokens, starts with a WH-word or "Why/How/Really"
    # Handled in _score() because it's length-dependent — not a pure regex.

]

# Compile the short-question starter separately for use in _score()
_SHORT_Q_STARTERS = _compile(
    r"^(why|how|what about|how about|really|seriously|and then|so then)\b"
)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

_CONTEXT_THRESHOLD = 4  # raw score at/above which the prompt needs context


def _score(prompt: str) -> tuple[int, str]:
    """
    Scan the prompt against all signals and return (accumulated_score, first_reason).

    Returns:
        (score: int, reason: str)  — reason is the label of the highest-weight match.
    """
    stripped = prompt.strip()
    total = 0
    best_reason: Optional[str] = None
    best_weight = 0

    for sig in _SIGNALS:
        if sig.pattern.search(stripped):
            total += sig.weight
            if sig.weight > best_weight:
                best_weight = sig.weight
                best_reason = sig.label

    # Signal 8: interrogative fragment (structural check)
    tokens = stripped.split()
    if (
        len(tokens) <= 6
        and _SHORT_Q_STARTERS.match(stripped)
    ):
        w = 4
        total += w
        if w > best_weight:
            best_weight = w
            best_reason = "Short interrogative fragment without a clear subject"

    reason = best_reason or "No strong context-dependency signals found"
    return total, reason


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify(prompt: str) -> tuple[bool, float, str]:
    """
    Classify whether a user prompt requires prior conversation context.

    Args:
        prompt: The raw user message to evaluate.

    Returns:
        (needs_context, confidence, reason)
        - needs_context: True if the prompt likely requires conversation history.
        - confidence:    Float 0.0 – 1.0 indicating classifier certainty.
        - reason:        Short human-readable explanation of the decision.
    """
    if not prompt or not prompt.strip():
        return False, 1.0, "Empty prompt — no context needed"

    score, reason = _score(prompt)

    needs_context = score >= _CONTEXT_THRESHOLD

    if needs_context:
        # More signals → higher confidence, capped at 0.99
        confidence = min(0.60 + score * 0.05, 0.99)
    else:
        # More signals still detected (but below threshold) → lower confidence in False verdict
        confidence = max(0.99 - score * 0.08, 0.60)

    # ------------- DEBUG PRINT -------------
    print("\n" + "~" * 60)
    print(f"[CLASS_SIM] Checking Context Requirement")
    print(f"[CLASS_SIM] Score: {score} -> needs_context: {needs_context} (Confidence: {confidence})")
    print(f"[CLASS_SIM] Reason: {reason}")
    print("~" * 60 + "\n")
    # ---------------------------------------

    return needs_context, round(confidence, 2), reason
