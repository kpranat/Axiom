"""
core/prompt_optimizer.py
------------------------
Token-reduction pre-processor for the model cascading router.

Takes the user's raw prompt (and optional pre-summarised context) and rewrites
it into a shorter, information-dense version using Groq's cheapest model.
The optimizer always uses llama-3.1-8b-instant regardless of the target tier —
this is cheap preprocessing, not the final answer call.

Returns
-------
OptimizeResult
    optimized_prompt : str   — the rewritten, token-efficient prompt.
                               If context is supplied it is prepended in a
                               structured block so the downstream model has
                               full situational awareness.
    original_tokens  : int   — rough word-count of the original input.
    optimized_tokens : int   — rough word-count of the optimized output.
    tokens_saved     : int   — original_tokens − optimized_tokens (≥ 0).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

_OPTIMIZER_MODEL = "llama-3.1-8b-instant"   # always cheap; this is preprocessing


# ──────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OptimizeResult:
    """Immutable result returned by the prompt optimizer."""
    optimized_prompt: str   # ready-to-send, token-efficient prompt
    original_tokens: int    # rough word-count before optimization
    optimized_tokens: int   # rough word-count after optimization
    tokens_saved: int       # delta (never negative)
    optimize_input_tokens: int
    optimize_output_tokens: int


# ──────────────────────────────────────────────────────────────────────────────
# System prompt (baked in — same for all tiers)
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a prompt compression engine. Your only job is to rewrite the user's \
prompt into a shorter, token-efficient version that preserves 100% of the \
original intent, constraints, and factual requirements.

Rules:
- Remove filler words, greetings, redundant phrases, and conversational openers \
  (e.g. "Hi, could you please", "I was wondering if", "Just wanted to ask").
- Keep all specific facts, numbers, names, constraints, and instructions.
- Do NOT add new information, explanations, or commentary.
- Do NOT answer the question — only rewrite the prompt.
- Output ONLY the rewritten prompt. No preamble, no labels, no quotes."""


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _rough_token_count(text: str) -> int:
    """Fast word-count approximation (1 word ≈ 1.3 tokens on average)."""
    return len(text.split())


def _build_user_message(prompt: str, context: Optional[str]) -> str:
    """
    Build the message we send to the optimizer model.
    If context is present it is included so the model knows what references
    in the prompt mean (e.g. 'that project' / 'as we discussed').
    """
    if context:
        return (
            f"[CONVERSATION CONTEXT]\n{context.strip()}\n\n"
            f"[USER PROMPT TO COMPRESS]\n{prompt.strip()}"
        )
    return f"[USER PROMPT TO COMPRESS]\n{prompt.strip()}"


def _build_final_prompt(optimized_raw: str, context: Optional[str]) -> str:
    """
    Assemble the final prompt_to_send that will be forwarded to the LLM tier.
    If context was provided it is prepended in a clean structured block so the
    downstream model has full situational awareness without needing a separate
    context injection step.
    """
    if context:
        return (
            f"[CONTEXT]\n{context.strip()}\n\n"
            f"[PROMPT]\n{optimized_raw.strip()}"
        )
    return optimized_raw.strip()


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def optimize(
    prompt: str,
    context: Optional[str] = None,
    tier: int = 1,
) -> OptimizeResult:
    """
    Compress the prompt (and optionally prepend context) for efficient LLM use.

    Args:
        prompt:  The raw user prompt (post-cache-miss, pre-LLM).
        context: Pre-summarised conversation history from /summarise.
                 If provided, it is embedded in the final prompt_to_send.
        tier:    The tier assigned by the tier router (1 | 2 | 3).
                 Currently informational — optimizer behaviour is tier-agnostic
                 but the value is kept for future tier-specific logic.

    Returns:
        OptimizeResult with the optimized_prompt ready to forward to the model.
    """
    if not prompt or not prompt.strip():
        return OptimizeResult(
            optimized_prompt="",
            original_tokens=0,
            optimized_tokens=0,
            tokens_saved=0,
            optimize_input_tokens=0,
            optimize_output_tokens=0,
        )

    optimize_input_tokens = _rough_token_count(prompt)
    original_tokens = optimize_input_tokens
    if context:
        original_tokens += _rough_token_count(context)

    user_message = _build_user_message(prompt, context)

    response = _client.chat.completions.create(
        model=_OPTIMIZER_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        max_tokens=512,
        temperature=0.1,   # near-deterministic — we want consistent compression
    )

    optimized_raw: str = response.choices[0].message.content.strip()
    optimize_output_tokens = _rough_token_count(optimized_raw)

    # Assemble the final prompt that goes to the downstream tier model
    final_prompt = _build_final_prompt(optimized_raw, context)

    optimized_tokens = _rough_token_count(final_prompt)
    tokens_saved = max(original_tokens - optimized_tokens, 0)

    return OptimizeResult(
        optimized_prompt=final_prompt,
        original_tokens=original_tokens,
        optimized_tokens=optimized_tokens,
        tokens_saved=tokens_saved,
        optimize_input_tokens=optimize_input_tokens,
        optimize_output_tokens=optimize_output_tokens,
    )
