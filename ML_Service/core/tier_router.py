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
Seven weighted signals are evaluated:

    S1  Token count of prompt            (0–1 pt, deliberately de-emphasized)
    S2  Reasoning / complexity keywords  (+3 pts)
  S3  Technical / domain vocabulary    (+1 pt)
  S4  Context attached and long        (+2 pts)
  S5  Complex instruction framing      (+1 pt)
    S6  Large-source analysis cues       (+2 pts)
    S7  Structured deliverable cues      (0–3 pts)

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
    r"explain\s+why|explain\s+how|detail|why\s+does|how\s+does|"
    r"compare|contrast|versus|vs\.?|"
    r"analy[sz]e|analy[sz]is|evaluate|evaluation|"
    r"critique|critically|assess|assessment|"
    r"justify|justify\s+your|reasoning|reason\s+through|"
    r"pros\s+and\s+cons|trade[\s-]?offs?|"
    r"debug|debugging|diagnos(?:e|is|ing)|troubleshoot(?:ing)?|"
    r"investigate|root\s+cause|resolve|fix|repair|"
    r"synthesi[sz]e|summari[sz]e|extract|"
    r"recommend(?:ation|ations)?|propose|proposal|"
    r"prioriti[sz]e|prioritization|roadmap|strategy|plan|planning|"
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
    r"database|schema|query|endpoint|api|json|http|"
    r"error|errors|exception|exceptions|bug|bugs|"
    r"test|tests|testing|edge\s+cases?|"
    r"compliance|policy|risk|security|privacy|"
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


# S6 — large-source / transcript analysis cues
_SOURCE_ARTIFACT = _c(
    r"\b("
    r"transcript|interview|meeting\s+transcript|call\s+transcript|"
    r"conversation\s+log|chat\s+log|document|report|paper|file|recording"
    r")\b"
)

_SIZE_OR_DURATION = _c(
    r"\b("
    r"long|large|full|entire|complete|multi[\s-]?hour|multi[\s-]?page|"
    r"\d+\s*[-]?\s*(hour|hours|hr|hrs|minute|minutes|min|mins|page|pages)"
    r")\b"
)

_ANALYSIS_ACTION = _c(
    r"\b("
    r"analy[sz]e|summari[sz]e|review|extract|identify|synthesi[sz]e|audit|detail"
    r")\b"
)


# S7 — structured deliverable / executive-summary cues
_EXECUTIVE_OUTPUT = _c(r"\b(executive\s+summary|summary|briefing|report)\b")
_EVIDENCE_OUTPUT = _c(
    r"\b(quoted?\s+examples?|with\s+examples?|for\s+every\s+claim|cite|citations?|evidence)\b"
)
_WORD_BUDGET = _c(r"\b(\d{2,4}\s*[-]?\s*word[s]?|word\s+limit)\b")
_MULTI_SECTION_ANALYSIS = _c(
    r"\b(key\s+themes?|contradictions?|action\s+items?|emotional\s+shifts?|per\s+participant)\b"
)


# ──────────────────────────────────────────────────────────────────────────────
# Scoring helpers
# ──────────────────────────────────────────────────────────────────────────────

_CONTEXT_LONG_THRESHOLD = 50   # words in context to trigger S4
_TIER_BOUNDARIES = (4, 8)      # [Tier1 < 4], [4 <= Tier2 < 8], [Tier3 >= 8]


def _score_token_count(prompt: str) -> tuple[int, str]:
    """
    S1: Lightweight length signal (whitespace-split token count).

    Length is intentionally de-emphasized so complexity/content cues dominate.

    ≤ 25 tokens   → 0 pts
    26+ tokens    → 1 pt
    """
    n = len(prompt.split())
    if n <= 20:
        return 0, f"Short prompt ({n} tokens)"
    return 1, f"Length signal present ({n} tokens, low weight)"


def _score_reasoning(prompt: str) -> tuple[int, str]:
    """S2: +3 if any reasoning/analytical keyword is detected."""
    if _REASONING.search(prompt):
        match = _REASONING.search(prompt)
        return 3, f"Reasoning keyword detected: '{match.group().strip()}'"
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


def _score_large_source(prompt: str) -> tuple[int, str]:
    """S6: +2 for transcript/large-file style analysis prompts."""
    stripped = prompt.strip()

    source = _SOURCE_ARTIFACT.search(stripped)
    if not source:
        return 0, ""

    size_or_duration = _SIZE_OR_DURATION.search(stripped)
    action = _ANALYSIS_ACTION.search(stripped)

    if size_or_duration or action:
        second = size_or_duration or action
        return 2, (
            "Large-source analysis cue detected: "
            f"'{source.group().strip()}' + '{second.group().strip()}'"
        )

    return 1, f"Source artifact detected: '{source.group().strip()}'"


def _score_structured_deliverable(prompt: str) -> tuple[int, str]:
    """S7: 0–3 based on how many structured-output cues are requested."""
    stripped = prompt.strip()

    cues: list[str] = []
    if _EXECUTIVE_OUTPUT.search(stripped):
        cues.append("summary/report output")
    if _EVIDENCE_OUTPUT.search(stripped):
        cues.append("evidence/examples requirement")
    if _WORD_BUDGET.search(stripped):
        cues.append("word budget")
    if _MULTI_SECTION_ANALYSIS.search(stripped):
        cues.append("multi-section analysis")

    if len(cues) >= 3:
        return 3, f"Structured deliverable cues detected: {', '.join(cues[:3])}"
    if len(cues) == 2:
        return 2, f"Structured deliverable cues detected: {', '.join(cues[:2])}"
    if len(cues) == 1:
        return 1, f"Structured deliverable cue detected: {cues[0]}"
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

    # Accumulate scores from all signals
    signals: list[tuple[int, str]] = [
        _score_token_count(prompt),
        _score_reasoning(prompt),
        _score_technical(prompt),
        _score_context(context),
        _score_instruction_framing(prompt),
        _score_large_source(prompt),
        _score_structured_deliverable(prompt),
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

    # ------------- DEBUG PRINT -------------
    print("\n" + "=" * 60)
    print("[ROUTER_SIM] Full Scoring Matrix for Prompt Tiering")
    print("-" * 60)
    signal_names = [
        "Token Count",
        "Reasoning / Complexity",
        "Technical / Domain Vocab",
        "Context / History",
        "Instruction Framing",
        "Large-source Analysis",
        "Structured Deliverable"
    ]
    for i, ((pts, reason), name) in enumerate(zip(signals, signal_names), 1):
        reason_str = reason if reason else "No match"
        print(f"  S{i} [{name}]: {pts} pts  -> {reason_str}")
    print("-" * 60)
    print(f"  Total Score: {total_score} -> Assigned Tier: {tier}")
    print("=" * 60 + "\n")
    # ---------------------------------------

    return RouteResult(tier=tier, score=total_score, reason=best_reason)
