# pip install fastapi groq google-generativeai transformers python-dotenv
import os
import sys
import re
import time
import json
import logging
from typing import Optional, Generator
from dataclasses import dataclass
from dotenv import load_dotenv, find_dotenv
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Load environment variables — find_dotenv() walks up the tree automatically
load_dotenv(find_dotenv(usecwd=True))

import google.generativeai as genai
from groq import Groq

# -----------------------------------------------------------------------------
# 1. Constants
# -----------------------------------------------------------------------------
TIER_SYSTEM_PROMPT = """You are a highly efficient assistant.

STRICT RULE: If the user's question requires any of the following:
- Advanced mathematics or formal proofs
- Deep multi-step code generation (more than 20 lines)
- Specialized domain knowledge you are not confident about
- Legal, medical, or financial analysis
- Complex reasoning chains longer than 5 steps

Then your ENTIRE response must be the single word: CASCADE
Nothing before it. Nothing after it. Just: CASCADE

If you can answer confidently and correctly, answer normally.
Do NOT use CASCADE for simple questions."""

SIGNAL = "CASCADE"
BUFFER_LIMIT = 15   # chars to buffer before checking for CASCADE signal

# Regex that strips a trailing confidence JSON line produced by confidence_few_shot.py
# e.g.  {"confidence": 0.97}
_CONFIDENCE_RE = re.compile(r'\s*\{[\s]*"confidence"\s*:\s*[\d.]+[\s]*\}\s*$')

COSTS = {
    "tier1_input":  0.05,
    "tier1_output": 0.10,
    "tier2_input":  0.59,
    "tier2_output": 0.79,
    "tier3_input":  1.25,
    "tier3_output": 10.00,
}

# Model names
TIER1_MODEL = "llama-3.1-8b-instant"
TIER2_MODEL = "llama-3.3-70b-versatile"
TIER3_MODEL = "gemini-2.5-flash"

# -----------------------------------------------------------------------------
# 2. CascadeResult dataclass
# -----------------------------------------------------------------------------
@dataclass
class CascadeResult:
    cascaded: bool
    tier_reached: int
    response: str
    is_streaming: bool
    stream_generator: Optional[Generator]
    input_tokens_used: dict
    cascade_detected_at_chars: Optional[int]
    total_latency_ms: float

# -----------------------------------------------------------------------------
# 3. Tokenizer utilities
# -----------------------------------------------------------------------------
_groq_tokenizer = None

def get_groq_tokenizer():
    """Lazy-loaded GPT-2 tokenizer used as a fast approximation for Llama token counts."""
    global _groq_tokenizer
    if _groq_tokenizer is None:
        try:
            from transformers import AutoTokenizer
            logging.getLogger("transformers.tokenization_utils_base").setLevel(logging.ERROR)
            _groq_tokenizer = AutoTokenizer.from_pretrained(
                "openai-community/gpt2",
                use_fast=True
            )
        except Exception as e:
            logging.warning(f"Failed to load HuggingFace tokenizer: {e}. Falling back to char/4 approximation.")
            _groq_tokenizer = "fallback"
    return _groq_tokenizer

def count_groq_tokens(text: str) -> int:
    """Approximate Llama/Groq token count using a GPT-2 tokenizer (±5% accuracy)."""
    if not text:
        return 0
    tok = get_groq_tokenizer()
    if tok == "fallback":
        return max(1, len(text) // 4)
    try:
        return len(tok.encode(text, add_special_tokens=False))
    except Exception:
        return max(1, len(text) // 4)

def count_gemini_tokens(model_name: str, text: str) -> int:
    if not text:
        return 0
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel(model_name)
        return model.count_tokens(text).total_tokens
    except Exception:
        return max(1, len(text) // 4)

# -----------------------------------------------------------------------------
# 4. Cost calculation
# -----------------------------------------------------------------------------
def calculate_cost(tier: int, input_tokens: int, output_tokens: int) -> float:
    cost_in = (input_tokens / 1_000_000) * COSTS.get(f"tier{tier}_input", 0.0)
    cost_out = (output_tokens / 1_000_000) * COSTS.get(f"tier{tier}_output", 0.0)
    return cost_in + cost_out

def build_billing_summary(cascade_result: CascadeResult) -> dict:
    tier = cascade_result.tier_reached
    total_cost = 0.0
    tier_costs = {1: 0.0, 2: 0.0, 3: 0.0}

    for t_str, tokens in cascade_result.input_tokens_used.items():
        if tokens > 0:
            t = int(t_str.replace("tier", ""))
            c = calculate_cost(t, tokens, 0)
            tier_costs[t] += c
            total_cost += c

    output_tokens = 0
    if cascade_result.response:
        if tier in (1, 2):
            output_tokens = count_groq_tokens(cascade_result.response)
        else:
            output_tokens = count_gemini_tokens(TIER3_MODEL, cascade_result.response)
    else:
        output_tokens = 1

    out_cost = calculate_cost(tier, 0, output_tokens)
    tier_costs[tier] += out_cost
    total_cost += out_cost

    charge_to_user = tier_costs[tier]

    in_toks = cascade_result.input_tokens_used.get(f"tier{tier}", 0)
    model_name = TIER1_MODEL if tier == 1 else TIER2_MODEL if tier == 2 else TIER3_MODEL
    logging.info(f"[ANSWER] Tier {tier} ({model_name}) answered. Input tokens: {in_toks}, Output tokens: {output_tokens}")
    logging.info(f"[COST] Total request cost: ${total_cost:.8f} | Charged to user: ${charge_to_user:.8f}")

    return {
        "tier1_cost": tier_costs[1],
        "tier2_cost": tier_costs[2],
        "tier3_cost": tier_costs[3],
        "total_cost": total_cost,
        "charge_to_user": charge_to_user,
        "absorbed_cost": total_cost - charge_to_user,
    }

# -----------------------------------------------------------------------------
# 5. Streaming helpers
# -----------------------------------------------------------------------------
def _strip_confidence_json(text: str) -> str:
    """Remove trailing confidence JSON injected by confidence_few_shot.py, if present."""
    return _CONFIDENCE_RE.sub("", text).rstrip()

def _stream_groq(prompt: str, system_prompt: str, tier: int, model_name: str) -> CascadeResult:
    """
    Stream a Groq model, watching the first BUFFER_LIMIT chars for the CASCADE signal.
    If detected the stream is aborted immediately and cascaded=True is returned.
    Otherwise a pass-through generator is returned for the caller to consume.
    """
    start_time = time.perf_counter()
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logging.error(f"[ERROR] Tier {tier} failed: Missing GROQ_API_KEY")
        return CascadeResult(True, tier, "", False, None, {}, 0, (time.perf_counter() - start_time) * 1000)

    client = Groq(api_key=api_key)
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            stream=True,
        )
    except Exception as e:
        logging.error(f"[ERROR] Tier {tier} API call failed: {e}")
        return CascadeResult(True, tier, "", False, None, {}, 0, (time.perf_counter() - start_time) * 1000)

    buffer = ""
    cascaded = False

    try:
        for chunk in completion:
            delta = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else ""
            if delta:
                buffer += delta
                stripped = buffer.lstrip(" \t\n\r")
                # Once we have BUFFER_LIMIT chars we have enough context to decide
                if len(stripped) >= BUFFER_LIMIT:
                    cascaded = stripped.upper().startswith(SIGNAL)
                    break
    except Exception as e:
        logging.error(f"[ERROR] Tier {tier} stream read failed: {e}")
        cascaded = True

    # Post-loop: stream may have ended before hitting BUFFER_LIMIT (very short reply)
    if not cascaded and buffer:
        stripped = buffer.lstrip(" \t\n\r")
        if stripped.upper().startswith(SIGNAL):
            cascaded = True

    if cascaded:
        tokens_in_buffer = count_groq_tokens(buffer)
        next_tier = tier + 1
        logging.info("")
        logging.info("━" * 60)
        logging.info(f"  🔺 CASCADE TRIGGERED — Tier {tier} → Tier {next_tier}")
        logging.info(f"  ├─ Intercepted Output               : \"{buffer.strip()}\"")
        logging.info(f"  ├─ Tokens read before signal        : ~{tokens_in_buffer} tok  ({len(buffer)} chars)")
        logging.info(f"  └─ Model aborted, escalating now...")
        logging.info("━" * 60)
        logging.info("")
        try:
            completion.close()
        except Exception:
            pass
        return CascadeResult(
            cascaded=True,
            tier_reached=tier,
            response="",
            is_streaming=False,
            stream_generator=None,
            input_tokens_used={},
            cascade_detected_at_chars=len(buffer),
            total_latency_ms=(time.perf_counter() - start_time) * 1000,
        )

    # Not a cascade — return a pass-through generator
    def pass_through() -> Generator[str, None, None]:
        if buffer:
            yield buffer
        try:
            for chunk in completion:
                delta = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else ""
                if delta:
                    yield delta
        except Exception as e:
            logging.error(f"[ERROR] Tier {tier} pass-through failed: {e}")
        finally:
            try:
                completion.close()
            except Exception:
                pass

    return CascadeResult(
        cascaded=False,
        tier_reached=tier,
        response="",
        is_streaming=True,
        stream_generator=pass_through(),
        input_tokens_used={},
        cascade_detected_at_chars=None,
        total_latency_ms=(time.perf_counter() - start_time) * 1000,
    )


def stream_tier1(prompt: str, system_prompt: str) -> CascadeResult:
    """Tier 1 — Llama 3.1 8B (Groq, fast & cheap)"""
    return _stream_groq(prompt, system_prompt, 1, TIER1_MODEL)

def stream_tier2(prompt: str, system_prompt: str) -> CascadeResult:
    """Tier 2 — Llama 3.3 70B (Groq, balanced)"""
    return _stream_groq(prompt, system_prompt, 2, TIER2_MODEL)

def stream_tier3(prompt: str) -> CascadeResult:
    """Tier 3 — Gemini 2.5 Flash (Google, frontier)"""
    start_time = time.perf_counter()
    tier = 3
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logging.error(f"[ERROR] Tier {tier} failed: Missing GOOGLE_API_KEY / GEMINI_API_KEY")
        raise RuntimeError("Missing GOOGLE_API_KEY")

    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel(TIER3_MODEL)
        response = model.generate_content(
            prompt,
            stream=True,
            generation_config=genai.types.GenerationConfig(temperature=1.0),
        )

        def pass_through() -> Generator[str, None, None]:
            try:
                for chunk in response:
                    if chunk.text:
                        yield chunk.text
            except Exception as e:
                logging.error(f"[ERROR] Tier {tier} pass-through failed: {e}")

        return CascadeResult(
            cascaded=False,
            tier_reached=tier,
            response="",
            is_streaming=True,
            stream_generator=pass_through(),
            input_tokens_used={},
            cascade_detected_at_chars=None,
            total_latency_ms=(time.perf_counter() - start_time) * 1000,
        )
    except Exception as e:
        logging.error(f"[ERROR] Tier {tier} failed: {e}")
        raise

# -----------------------------------------------------------------------------
# 6. Main orchestrator
# -----------------------------------------------------------------------------
def run_cascade(user_prompt: str, start_tier: int = 1) -> CascadeResult:
    """
    Run the cascade from start_tier upward.
    Tier 1 → Tier 2 → Tier 3 (Tier 3 always replies).
    """
    input_tokens: dict = {"tier1": 0, "tier2": 0, "tier3": 0}

    # ── Tier 1 ────────────────────────────────────────────────────────────────
    if start_tier <= 1:
        t1_in_toks = count_groq_tokens(TIER_SYSTEM_PROMPT + "\n\n" + user_prompt)
        input_tokens["tier1"] = t1_in_toks
        logging.info(f"┌─ Attempting Tier 1 ({TIER1_MODEL})")
        res1 = stream_tier1(user_prompt, TIER_SYSTEM_PROMPT)
        if not res1.cascaded:
            res1.input_tokens_used = input_tokens.copy()
            return res1
        total_so_far = sum(input_tokens.values())
        logging.info(
            f"[ESCALATE] Tier 1 → Tier 2  |  "
            f"Input tokens charged for Tier 1: {t1_in_toks}  |  Running total: {total_so_far}"
        )
        logging.info(f"           Escalating with prompt: \"{user_prompt[:50]}...\"")

    # ── Tier 2 ────────────────────────────────────────────────────────────────
    if start_tier <= 2:
        t2_in_toks = count_groq_tokens(TIER_SYSTEM_PROMPT + "\n\n" + user_prompt)
        input_tokens["tier2"] = t2_in_toks
        logging.info(f"┌─ Attempting Tier 2 ({TIER2_MODEL})")
        res2 = stream_tier2(user_prompt, TIER_SYSTEM_PROMPT)
        if not res2.cascaded:
            res2.input_tokens_used = input_tokens.copy()
            return res2
        total_so_far = sum(input_tokens.values())
        logging.info(
            f"[ESCALATE] Tier 2 → Tier 3  |  "
            f"Input tokens charged for Tier 2: {t2_in_toks}  |  Running total: {total_so_far}"
        )
        logging.info(f"           Escalating with prompt: \"{user_prompt[:50]}...\"")

    # ── Tier 3 (must answer) ──────────────────────────────────────────────────
    t3_in_toks = count_gemini_tokens(TIER3_MODEL, user_prompt)
    input_tokens["tier3"] = t3_in_toks
    logging.info(f"┌─ Attempting Tier 3 ({TIER3_MODEL})")
    res3 = stream_tier3(user_prompt)
    res3.input_tokens_used = input_tokens.copy()
    return res3

# -----------------------------------------------------------------------------
# 7. FastAPI router — replaces the old standalone Flask app
#    Registered by routes/router.py → api_router
# -----------------------------------------------------------------------------
from core.tier_router import route as tier_route   # noqa: E402 (imported here to avoid circular at module load)

gateway_router = APIRouter(tags=["Gateway"])


@gateway_router.post("/query", summary="Non-streaming cascade query")
async def query(body: dict):
    """
    Accept { "prompt": "..." } and return the final answer with billing info.
    Starts from the tier resolved by tier_router (skips unnecessary tiers).
    """
    user_prompt = (body.get("prompt") or "").strip()
    if not user_prompt:
        return JSONResponse({"error": "prompt is required"}, status_code=400)

    start_tier = body.get("start_tier")
    if not isinstance(start_tier, int):
        start_tier = tier_route(user_prompt).tier

    try:
        result = run_cascade(user_prompt, start_tier=start_tier)
        full_text = ""
        if result.is_streaming and result.stream_generator:
            for chunk in result.stream_generator:
                full_text += chunk
        full_text = _strip_confidence_json(full_text)
        result.response = full_text
        billing = build_billing_summary(result)
        return {
            "answer": full_text,
            "tier_used": result.tier_reached,
            "billing": billing,
            "cascade_info": {
                "tier1_cascaded": result.tier_reached > 1,
                "tier2_cascaded": result.tier_reached > 2,
                "latency_ms": result.total_latency_ms,
            },
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=503)


@gateway_router.post("/query/stream", summary="SSE streaming cascade query")
async def stream_query(body: dict):
    """
    Accept { "prompt": "..." } and return an SSE stream.
    Events: cascade_event | token | done | error
    """
    user_prompt = (body.get("prompt") or "").strip()
    if not user_prompt:
        return JSONResponse({"error": "prompt is required"}, status_code=400)

    start_tier = body.get("start_tier")
    if not isinstance(start_tier, int):
        start_tier = tier_route(user_prompt).tier

    async def generate():
        try:
            result = run_cascade(user_prompt, start_tier=start_tier)

            if result.tier_reached > 1:
                yield f"data: {json.dumps({'type': 'cascade_event', 'from_tier': 1, 'to_tier': 2})}\n\n"
            if result.tier_reached > 2:
                yield f"data: {json.dumps({'type': 'cascade_event', 'from_tier': 2, 'to_tier': 3})}\n\n"

            full_text = ""
            if result.is_streaming and result.stream_generator:
                try:
                    for chunk in result.stream_generator:
                        full_text += chunk
                        yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
                except Exception as e:
                    logging.error(f"[ERROR] Stream interrupted: {e}")

            full_text = _strip_confidence_json(full_text)
            result.response = full_text
            billing = build_billing_summary(result)
            yield f"data: {json.dumps({'type': 'done', 'billing': billing, 'tier_used': result.tier_reached})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# -----------------------------------------------------------------------------
# 8. CLI entry point for quick smoke tests
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_prompts = [
            "What is 2 + 2?",                           # expect Tier 1
            "Write a full REST API in Python with auth", # expect cascade
            "Prove the Riemann Hypothesis",              # expect Tier 3
        ]
        for p in test_prompts:
            print(f"\nTesting: {p}")
            try:
                result = run_cascade(p)
                full_text = ""
                if result.is_streaming and result.stream_generator:
                    for chunk in result.stream_generator:
                        full_text += chunk
                full_text = _strip_confidence_json(full_text)
                result.response = full_text
                summary = build_billing_summary(result)
                print(f"Answered by Tier {result.tier_reached}")
                print(f"Answer: {full_text[:200]}")
                print(f"Total cost: ${summary['total_cost']:.8f}")
            except Exception as e:
                print(f"Test failed: {e}")
