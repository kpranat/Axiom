"""
core/llm_dispatcher.py
----------------------
Simulated LLM dispatcher.

Maps numeric tiers (1 / 2 / 3) from the router to named model tiers
(LOW / MID / HIGH) and tries each model in order — cheapest first.

No real API calls are made: every "call" is simulated and the terminal
receives a detailed log of what would have been invoked.
"""

import os
import re
import time
import requests
from dataclasses import dataclass, field
from groq import Groq

# ── Tier definitions ──────────────────────────────────────────────────────────
TIER_NAMES: dict[int, str] = {
    1: "LOW",
    2: "MID",
    3: "HIGH",
}

TIERS: dict[str, list[str]] = {
    "LOW":  ["llama-3.1-8b-instant"],
    "MID":  ["llama-3.3-70b-versatile"],
    "HIGH": ["llama-3.3-70b-versatile"],
}

MODEL_DESCRIPTIONS: dict[str, str] = {
    "llama-3.1-8b-instant": "LLaMA 3.1 8B (REAL) — simple queries, ultra-fast",
    "llama-3.3-70b-versatile": "LLaMA 3.3 70B (REAL) — moderate reasoning, high capacity",
    "gemini-2.5-flash":  "Gemini 2.5 Flash (REAL) — complex reasoning, frontier",
}

_GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "25"))
_GEMINI_MAX_ATTEMPTS = max(int(os.getenv("GEMINI_MAX_ATTEMPTS", "3")), 1)


def _is_error_response(text: str) -> bool:
    return (text or "").startswith("[ERROR:")


def _is_retryable_gemini_status(status_code: int) -> bool:
    return status_code in (429, 500, 502, 503, 504)


@dataclass
class DispatchResult:
    tier_number: int
    tier_name: str
    model_used: str
    prompt_sent: str
    simulated_response: str
    models_tried: list[str] = field(default_factory=list)
    cascaded: bool = False
    cascade_input_tokens: int = 0
    cascade_output_tokens: int = 0
    model_attempts: list[dict[str, int | str]] = field(default_factory=list)


def _rough_token_count(text: str) -> int:
    return len((text or "").split())


def _simulate_model_call(model: str, prompt: str) -> tuple[str, int, int]:
    """Return response text with input/output token counts."""
    default_input = _rough_token_count(prompt)
    if model in ("llama-3.1-8b-instant", "llama-3.3-70b-versatile"):
        try:
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
            )
            text = completion.choices[0].message.content
            usage = getattr(completion, "usage", None)
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            if input_tokens <= 0:
                input_tokens = default_input
            if output_tokens <= 0:
                output_tokens = _rough_token_count(text)
            return text, input_tokens, output_tokens
        except Exception as e:
            text = f"[ERROR: Groq API failed] {str(e)}"
            return text, default_input, _rough_token_count(text)

    elif model == "gemini-2.5-flash":
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            text = "[ERROR: Gemini API failed] Missing GEMINI_API_KEY"
            return text, default_input, _rough_token_count(text)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}

        for attempt in range(1, _GEMINI_MAX_ATTEMPTS + 1):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=_GEMINI_TIMEOUT_SECONDS,
                )

                if _is_retryable_gemini_status(response.status_code) and attempt < _GEMINI_MAX_ATTEMPTS:
                    backoff_seconds = 0.5 * attempt
                    print(
                        f"     Warning       : Gemini HTTP {response.status_code} on attempt "
                        f"{attempt}/{_GEMINI_MAX_ATTEMPTS}; retrying in {backoff_seconds:.1f}s..."
                    )
                    time.sleep(backoff_seconds)
                    continue

                response.raise_for_status()
                data = response.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                usage = data.get("usageMetadata", {})
                input_tokens = int(usage.get("promptTokenCount", 0) or 0)
                output_tokens = int(usage.get("candidatesTokenCount", 0) or 0)
                if input_tokens <= 0:
                    input_tokens = default_input
                if output_tokens <= 0:
                    output_tokens = _rough_token_count(text)
                return text, input_tokens, output_tokens

            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if _is_retryable_gemini_status(status) and attempt < _GEMINI_MAX_ATTEMPTS:
                    backoff_seconds = 0.5 * attempt
                    print(
                        f"     Warning       : Gemini HTTP {status} on attempt "
                        f"{attempt}/{_GEMINI_MAX_ATTEMPTS}; retrying in {backoff_seconds:.1f}s..."
                    )
                    time.sleep(backoff_seconds)
                    continue

                text = f"[ERROR: Gemini API failed] HTTP {status}"
                return text, default_input, _rough_token_count(text)

            except requests.RequestException:
                if attempt < _GEMINI_MAX_ATTEMPTS:
                    backoff_seconds = 0.5 * attempt
                    print(
                        f"     Warning       : Gemini request failed on attempt "
                        f"{attempt}/{_GEMINI_MAX_ATTEMPTS}; retrying in {backoff_seconds:.1f}s..."
                    )
                    time.sleep(backoff_seconds)
                    continue

                text = "[ERROR: Gemini API failed] Request error"
                return text, default_input, _rough_token_count(text)

            except Exception:
                text = "[ERROR: Gemini API failed] Unexpected error"
                return text, default_input, _rough_token_count(text)

    text = (
        f"[SIMULATED RESPONSE from {model}]\n"
        f"Prompt received ({len(prompt.split())} tokens). "
        f"This is a placeholder response — wire up the real {model} API here."
    )
    return text, default_input, _rough_token_count(text)


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
    models = []
    # Build an escalation path starting from the assigned tier up to HIGH
    for t in range(tier, 4):
        models.extend(TIERS.get(TIER_NAMES.get(t, "LOW"), []))
    
    models_tried: list[str] = []
    model_attempts: list[dict[str, int | str]] = []
    cascade_input_tokens = 0
    cascade_output_tokens = 0

    # ── Header banner ─────────────────────────────────────────────────────────
    separator = "=" * 60
    print(f"\n{separator}")
    print(f"  [DISPATCHER]  LLM DISPATCHER -- incoming request")
    print(separator)
    print(f"  [TIER]        Tier assigned : {tier} -> {tier_name}")
    print(f"  [MODELS]      Escalation path: {', '.join(models)}")
    print(f"  [TOKENS]      Prompt length : {len(prompt.split())} tokens (word-count approx)")
    print(separator)

    # ------------- DEBUG PRINT -------------
    print("\n[PROMPT_SIM] Final Prompt Sent to LLM:")
    print("-" * 60)
    print(prompt)
    print("-" * 60 + "\n")
    # ---------------------------------------

    response: str = ""
    model_used: str = models[0]

    for model in models:
        models_tried.append(model)
        desc = MODEL_DESCRIPTIONS.get(model, model)

        print(f"\n  >> Trying model  : {model}")
        print(f"     Description   : {desc}")
        
        status_msg = "CALLING (Real API)..." if model in ("llama-3.1-8b-instant", "llama-3.3-70b-versatile", "gemini-2.5-flash") else "CALLING... (simulated, no real API)"
        print(f"     Status        : {status_msg}")

        # Simulate latency
        time.sleep(0.05)

        # In production: replace this block with a real API call.
        response, input_tokens, output_tokens = _simulate_model_call(model, prompt)
        model_used = model
        cascade_input_tokens += input_tokens
        cascade_output_tokens += output_tokens
        model_attempts.append({
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        })

        if _is_error_response(response):
            if model != models[-1]:
                print("     Result        : PROVIDER ERROR — CASCADING UP...")
                continue
            print("     Result        : FAILED (final provider unavailable)")
            break

        # Parse confidence score from the JSON block at the end
        confidence = 1.0  # Default to pass if no score found
        match = re.search(r'"confidence"\s*:\s*([\d.]+)', response, re.IGNORECASE)
        if match:
            try:
                confidence = float(match.group(1))
            except ValueError:
                pass
        
        # If the model explicitly returns a low confidence (< 0.90) AND there are more models available to cascade to
        if confidence < 0.90 and model != models[-1]:
            print(f"     Result        : LOW CONFIDENCE ({confidence}) — CASCADING UP...")
            continue

        print(f"     Result        : SUCCESS (Confidence: {confidence})")
        break  # Target confidence reached or final model hit

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
        cascaded=len(models_tried) > 1,
        cascade_input_tokens=cascade_input_tokens,
        cascade_output_tokens=cascade_output_tokens,
        model_attempts=model_attempts,
    )
