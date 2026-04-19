"""
routes/llm.py
-------------
POST /llm/invoke

Accepts the output from /route (prompt_to_send + tier) and dispatches it
to the appropriate simulated LLM tier.

Model tiers
-----------
LOW  (tier=1) : llama-8b
MID  (tier=2) : llama-70b
HIGH (tier=3) : gemini-2.5-flash-lite

No real API calls are made — every dispatch is logged to the terminal.
"""

from fastapi import APIRouter, HTTPException
import logging

from core.gateway import (
    run_cascade,
    count_groq_tokens,
    count_gemini_tokens,
    TIER1_MODEL,
    TIER2_MODEL,
    TIER3_MODEL,
)
from core.router_adapter import route as tier_route
from models.schemas import (
    LLMInvokeRequest,
    LLMInvokeResponse,
    LLMSimulateRequest,
    LLMSimulateResponse,
)

router = APIRouter(prefix="/llm", tags=["LLM Dispatcher"])


def _count_output_tokens(tier: int, text: str) -> int:
    if not text:
        return 1

    if tier in (1, 2):
        return count_groq_tokens(text)

    return count_gemini_tokens(TIER3_MODEL, text)


def _log_token_usage(tier: int, input_tokens: int, output_tokens: int) -> None:
    """Print a clean token usage summary box to the terminal."""
    total = input_tokens + output_tokens
    model_name = TIER1_MODEL if tier == 1 else TIER2_MODEL if tier == 2 else TIER3_MODEL
    logging.info("")
    logging.info("╔══ TOKEN USAGE ═══════════════════════════════════════════╗")
    logging.info(f"║  Answered by  : Tier {tier} — {model_name:<33}║")
    logging.info("╠══════════════════════════════════════════════════════════╣")
    logging.info(f"║  Input  tokens: {input_tokens:<40}║")
    logging.info(f"║  Output tokens: {output_tokens:<40}║")
    logging.info(f"║  Total  tokens: {total:<40}║")
    logging.info("╚══════════════════════════════════════════════════════════╝")
    logging.info("")


@router.post(
    "/invoke",
    response_model=LLMInvokeResponse,
    summary="Invoke the appropriate LLM for a routed prompt",
    description=(
        "Pass the **prompt_to_send** and **tier** that were returned by `/route` "
        "and this endpoint will dispatch the prompt to the correct model tier.\n\n"
        "**Tier mapping:**\n"
        "- `1` → **LOW** — `llama-8b` (simple queries)\n"
        "- `2` → **MID** — `llama-70b` (moderate reasoning)\n"
        "- `3` → **HIGH** — `gemini-2.5-flash-lite` (complex reasoning)\n\n"
        "Models are tried in order (cheapest → most powerful). "
        "The terminal prints a detailed dispatch log for every call."
    ),
)
async def invoke_llm(request: LLMInvokeRequest) -> LLMInvokeResponse:
    """
    Dispatch a routed prompt to the target model tier.

    The endpoint is intentionally stateless: every request is independent.
    Pair it with `/route` to get the full Axiom TokenOptimizer pipeline.
    """
    try:
        # Use the production-grade gateway instead of the simulated dispatcher
        result = run_cascade(request.prompt_to_send, start_tier=request.tier)
        
        full_text = ""
        if result.is_streaming and result.stream_generator:
            for chunk in result.stream_generator:
                full_text += chunk
        
        result.response = full_text
        tier = result.tier_reached
        input_tokens = result.input_tokens_used.get(f"tier{tier}", 0)
        output_tokens = _count_output_tokens(tier, full_text)
        
        _log_token_usage(tier, input_tokens, output_tokens)
        
        return LLMInvokeResponse(
            tier_number=tier,
            tier_name="LOW" if tier == 1 else "MID" if tier == 2 else "HIGH",
            model_used=TIER3_MODEL if tier == 3 else TIER1_MODEL if tier == 1 else TIER2_MODEL,
            models_tried=[f"tier{i}" for i in range(request.tier, tier + 1)],
            simulated_response=full_text,
            token_breakdown={
                "model_cascade": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
                "attempts": [],
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/simulate",
    response_model=LLMSimulateResponse,
    summary="Route prompt and invoke simulated LLM (no external model API calls)",
    description=(
        "Pass a raw prompt, the router resolves the tier, and the dispatcher simulates "
        "the model call while printing tier and model selection in the terminal.\n\n"
        "**MODEL TIERS**\n"
        "- `LOW`  (`tier=1`): `llama-8b`\n"
        "- `MID`  (`tier=2`): `llama-70b`\n"
        "- `HIGH` (`tier=3`): `gemini-2.5-flash-lite`\n\n"
        "Models are tried in order (cheap to powerful). "
        "This endpoint is simulation-only and does not call real model provider APIs."
    ),
)
async def simulate_from_prompt(request: LLMSimulateRequest) -> LLMSimulateResponse:
    """
    Swagger-friendly endpoint for quick testing.

    It performs two steps in one call:
    1) Resolve tier from prompt (+ optional context).
    2) Simulate dispatch and print model/tier trace to the terminal.
    """
    try:
        route_result = tier_route(request.prompt, request.context)
        route_source = "llama" if route_result.reason.startswith("[router=llama]") else "fallback"
        print(f"[ROUTER_DEBUG] source={route_source} tier={route_result.tier} reason={route_result.reason}")

        print("\n" + "-" * 60)
        print("[LLM_GATEWAY] Incoming prompt received")
        print(f"[LLM_GATEWAY] Tier resolved: {route_result.tier} ({'LOW' if route_result.tier == 1 else 'MID' if route_result.tier == 2 else 'HIGH'})")
        print(f"[LLM_GATEWAY] Reason      : {route_result.reason}")
        print("-" * 60)

        result = run_cascade(request.prompt, start_tier=route_result.tier)

        full_text = ""
        if result.is_streaming and result.stream_generator:
            for chunk in result.stream_generator:
                full_text += chunk

        tier = result.tier_reached
        input_tokens = result.input_tokens_used.get(f"tier{tier}", 0)
        output_tokens = _count_output_tokens(tier, full_text)

        _log_token_usage(tier, input_tokens, output_tokens)

        return LLMSimulateResponse(
            tier_number=tier,
            tier_name="LOW" if tier == 1 else "MID" if tier == 2 else "HIGH",
            tier_reason=route_result.reason,
            model_used=TIER3_MODEL if tier == 3 else TIER1_MODEL if tier == 1 else TIER2_MODEL,
            models_tried=[f"tier{i}" for i in range(route_result.tier, tier + 1)],
            prompt_sent=request.prompt,
            simulated_response=full_text,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
