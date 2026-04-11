"""
core/llm_dispatcher.py
----------------------
Simulated LLM dispatcher.

Maps numeric tiers (1 / 2 / 3) from the router to named model tiers
(LOW / MID / HIGH) and tries each model in order — cheapest first.

No real API calls are made: every "call" is simulated and the terminal
receives a detailed log of what would have been invoked.
"""

import time
from dataclasses import dataclass, field

# ── Tier definitions ──────────────────────────────────────────────────────────
TIER_NAMES: dict[int, str] = {
    1: "LOW",
    2: "MID",
    3: "HIGH",
}

TIERS: dict[str, list[str]] = {
    "LOW":  ["llama-8b"],
    "MID":  ["gemini-flash", "llama-70b"],
    "HIGH": ["gemini-pro"],
}

MODEL_DESCRIPTIONS: dict[str, str] = {
    "llama-8b":    "LLaMA 3 8B  — simple queries, ultra-fast",
    "gemini-flash": "Gemini 1.5 Flash — moderate reasoning, low latency",
    "llama-70b":   "LLaMA 3 70B — moderate reasoning, high capacity",
    "gemini-pro":  "Gemini 1.5 Pro  — complex reasoning, frontier",
}


@dataclass
class DispatchResult:
    tier_number: int
    tier_name: str
    model_used: str
    prompt_sent: str
    simulated_response: str
    models_tried: list[str] = field(default_factory=list)


def _simulate_model_call(model: str, prompt: str) -> str:
    """Return a canned response that looks like real LLM output."""
    return (
        f"[SIMULATED RESPONSE from {model}]\n"
        f"Prompt received ({len(prompt.split())} tokens). "
        f"This is a placeholder response — wire up the real {model} API here."
    )


def dispatch(prompt: str, tier: int) -> DispatchResult:
    """
    Try each model in the resolved tier (cheapest → most powerful).

    Parameters
    ----------
    prompt : str
        The optimized prompt from /route (prompt_to_send).
    tier : int
        Numeric tier from the router: 1 = LOW, 2 = MID, 3 = HIGH.

    Returns
    -------
    DispatchResult
        Full record of what was tried and what (simulated) response came back.
    """
    tier_name = TIER_NAMES.get(tier, "LOW")
    models = TIERS.get(tier_name, ["llama-8b"])
    models_tried: list[str] = []

    # ── Header banner ─────────────────────────────────────────────────────────
    separator = "=" * 60
    print(f"\n{separator}")
    print(f"  [DISPATCHER]  LLM DISPATCHER -- incoming request")
    print(separator)
    print(f"  [TIER]        Tier assigned : {tier} -> {tier_name}")
    print(f"  [MODELS]      Models in tier: {', '.join(models)}")
    print(f"  [TOKENS]      Prompt length : {len(prompt.split())} tokens (word-count approx)")
    print(separator)

    response: str = ""
    model_used: str = models[0]

    for model in models:
        models_tried.append(model)
        desc = MODEL_DESCRIPTIONS.get(model, model)

        print(f"\n  >> Trying model  : {model}")
        print(f"     Description   : {desc}")
        print(f"     Status        : CALLING... (simulated, no real API)")

        # Simulate latency
        time.sleep(0.05)

        # In production: replace this block with a real API call.
        response = _simulate_model_call(model, prompt)
        model_used = model

        print(f"     Result        : SUCCESS")
        break  # First model succeeded — no cascade needed

    print(f"\n{separator}")
    print(f"  [OK]  Dispatched to : {model_used}  (Tier {tier} / {tier_name})")
    print(separator + "\n")

    return DispatchResult(
        tier_number=tier,
        tier_name=tier_name,
        model_used=model_used,
        prompt_sent=prompt,
        simulated_response=response,
        models_tried=models_tried,
    )
