"""
core/classifier.py
~~~~~~~~~~~~~~~~~~
Pure-Python, zero-dependency context-dependency classifier.

Decides whether a user's latest prompt REQUIRES prior conversation context
to be understood correctly.  No LLM, no model weights — rule-based only.

Algorithm
---------
1. Compile a set of weighted regex Signals at module load (once).
2. For each incoming prompt, evaluate strong signals and weak signals separately.
3. Apply standalone-intent guard to suppress weak-signal accumulation only.
4. Combine strong/weak outcomes into (needs_context: bool, confidence: float, reason: str).

Decision rule:
    - Any strong signal match           -> needs_context = True
    - Otherwise, weak_score >= 5        -> needs_context = True
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
    strong: bool = False


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
        weight=2,
        label="Bare pronoun reference (it/they/them/their/its/those/these)",
        strong=False,
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
        strong=True,
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
        strong=True,
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
        weight=5,
        label="Explicit back-reference (you mentioned / as discussed / as before…)",
        strong=True,
    ),

    # ── 5. Follow-up conjunction / adverb at sentence start ─────────────────
    # "Also, …", "Additionally, …", "Furthermore, …" at START of message.
    Signal(
        pattern=_compile(
            r"^(also|additionally|furthermore|besides|moreover|"
            r"as well|what else|in addition|on top of that|"
            r"other than that)[,\s]"
        ),
        weight=3,
        label="Follow-up conjunction/adverb at sentence start (also / additionally…)",
        strong=True,
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
        strong=True,
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
        strong=False,
    ),

    # ── 8. Ambiguous placeholder question at sentence start ────────────────
    # Captures unresolved references likely needing earlier turns.
    Signal(
        pattern=_compile(
            r"^\s*(what|who|which)\s+(is|are|was|were)\s+(it|this|that|those|these)\b"
        ),
        weight=4,
        label="Ambiguous placeholder question (what is it/this/that…)",
        strong=True,
    ),

    # ── 9. Explain/deepen request tied to deictic reference ─────────────────
    # e.g. "explain this in detail", "can you explain that"
    Signal(
        pattern=_compile(
            r"\b("
            r"(can you\s+)?(explain|describe|elaborate on|expand on)\s+(this|that|it)"
            r"(?:\s+in\s+(detail|depth))?"
            r")\b"
        ),
        weight=4,
        label="Explanation request on unresolved reference (explain this/that/it)",
        strong=True,
    ),

    # ── 10. Prepositional anaphora phrase ──────────────────────────────────
    # e.g. "behind it", "about it", "regarding it", "concerning this"
    Signal(
        pattern=_compile(
            r"\b(behind|about|regarding|concerning|around|on|over|for)\s+"
            r"(it|this|that|those|these|them)\b"
        ),
        weight=4,
        label="Prepositional anaphora phrase (behind/about/regarding/concerning it)",
        strong=True,
    ),

    # ── 11. Trailing deictic reference at sentence end ─────────────────────
    # End-of-sentence deictics are often unresolved in user follow-ups.
    Signal(
        pattern=_compile(r"\b(it|this|that|those|these|them)\s*[?!.]*\s*$"),
        weight=2,
        label="Trailing deictic reference at sentence end",
        strong=False,
    ),

    # ── 12. Interrogative fragment (short follow-up question) ───────────────
    # e.g. "Why not?", "How so?", "What about it?", "Really?"
    # Detected structurally: ≤ 6 tokens, starts with a follow-up starter.
    # Handled in _score() because it's length-dependent — not a pure regex.

]

# Compile the short-question starter separately for use in _score()
_SHORT_Q_STARTERS = _compile(
    r"^(what about|how about|why not|how so|really|seriously|and then|so then)\b"
)

_STANDALONE_INTENT_START = _compile(
    r"^(what is|what are|who is|how to|how do i|how can i|"
    r"recipe for|steps to|define|meaning of|benefits of|types of)\b"
)

_DEICTIC_REFERENCE = _compile(r"\b(it|this|that|those|these|they|them|their|its)\b")
_BACKREF_HINT = _compile(r"\b(earlier|before|previous|mentioned|said|discussed)\b")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

_CONTEXT_THRESHOLD = 5  # weak-signal score threshold; strong signals can override


def _looks_standalone_intent(prompt: str) -> bool:
    """
    Return True for generic informational prompts that are usually self-contained.

    Guardrail examples:
      - "how to make tea"
      - "what is machine learning"
      - "define polymorphism"
    """
    stripped = prompt.strip().lower()
    if not _STANDALONE_INTENT_START.match(stripped):
        return False

    # If there are unresolved references/back-reference cues, do not suppress.
    if _DEICTIC_REFERENCE.search(stripped):
        return False
    if _BACKREF_HINT.search(stripped):
        return False

    return True


def _score(prompt: str) -> tuple[int, int, str, bool, bool]:
    """
    Scan the prompt against all signals and return:
    (total_score, weak_score, best_reason, strong_hit, standalone_guard_applied).

    Returns:
        (score: int, weak_score: int, reason: str, strong_hit: bool, standalone_guard_applied: bool)
    """
    stripped = prompt.strip()
    total = 0
    weak_total = 0
    best_reason: Optional[str] = None
    best_weight = 0
    strong_hit = False
    standalone_guard_applied = _looks_standalone_intent(stripped)

    for sig in _SIGNALS:
        if sig.pattern.search(stripped):
            if sig.strong:
                total += sig.weight
                strong_hit = True
                if sig.weight > best_weight:
                    best_weight = sig.weight
                    best_reason = sig.label
            elif not standalone_guard_applied:
                total += sig.weight
                weak_total += sig.weight
                if sig.weight > best_weight:
                    best_weight = sig.weight
                    best_reason = sig.label

    # Signal 12: interrogative fragment (structural check)
    tokens = stripped.split()
    if (
        not standalone_guard_applied
        and
        len(tokens) <= 6
        and _SHORT_Q_STARTERS.match(stripped)
    ):
        w = 2
        total += w
        weak_total += w
        if w > best_weight:
            best_weight = w
            best_reason = "Short interrogative fragment without a clear subject"

    if standalone_guard_applied and not strong_hit and total == 0:
        return 0, 0, "Standalone informational intent detected", False, True

    reason = best_reason or "No strong context-dependency signals found"
    return total, weak_total, reason, strong_hit, standalone_guard_applied


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

    score, weak_score, reason, strong_hit, standalone_guard_applied = _score(prompt)

    needs_context = strong_hit or weak_score >= _CONTEXT_THRESHOLD

    if needs_context:
        # Strong references indicate clearer dependence on prior turns.
        if strong_hit:
            confidence = min(0.72 + score * 0.04, 0.99)
        else:
            confidence = min(0.62 + score * 0.03, 0.85)
    else:
        confidence = max(0.98 - score * 0.08, 0.60)

    # ------------- DEBUG PRINT -------------
    print("\n" + "~" * 60)
    print(f"[CLASS_SIM] Checking Context Requirement")
    print(f"[CLASS_SIM] Score: {score} -> needs_context: {needs_context} (Confidence: {confidence})")
    print(f"[CLASS_SIM] Weak score: {weak_score} (threshold={_CONTEXT_THRESHOLD})")
    print(f"[CLASS_SIM] Strong signal hit: {strong_hit}")
    print(f"[CLASS_SIM] Standalone guard applied: {standalone_guard_applied}")
    print(f"[CLASS_SIM] Reason: {reason}")
    print("~" * 60 + "\n")
    # ---------------------------------------

    return needs_context, round(confidence, 2), reason
