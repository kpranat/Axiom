"""
routes/llm.py
-------------
POST /llm/invoke

Accepts the output from /route (prompt_to_send + tier) and dispatches it
to the appropriate simulated LLM tier.

Model tiers
-----------
LOW  (tier=1) : llama-8b
MID  (tier=2) : gemini-flash → llama-70b   (cascade, cheapest first)
HIGH (tier=3) : gemini-pro

No real API calls are made — every dispatch is logged to the terminal.
"""

from fastapi import APIRouter, HTTPException

from core.llm_dispatcher import dispatch
from core.tier_router import route as tier_route
from models.schemas import (
    LLMInvokeRequest,
    LLMInvokeResponse,
    LLMSimulateRequest,
    LLMSimulateResponse,
)

router = APIRouter(prefix="/llm", tags=["LLM Dispatcher"])


@router.post(
    "/invoke",
    response_model=LLMInvokeResponse,
    summary="Invoke the appropriate LLM for a routed prompt",
    description=(
        "Pass the **prompt_to_send** and **tier** that were returned by `/route` "
        "and this endpoint will dispatch the prompt to the correct model tier.\n\n"
        "**Tier mapping:**\n"
        "- `1` → **LOW** — `llama-8b` (simple queries)\n"
        "- `2` → **MID** — `gemini-flash`, `llama-70b` (moderate reasoning)\n"
        "- `3` → **HIGH** — `gemini-pro` (complex reasoning)\n\n"
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
        result = dispatch(prompt=request.prompt_to_send, tier=request.tier)
        return LLMInvokeResponse(
            tier_number=result.tier_number,
            tier_name=result.tier_name,
            model_used=result.model_used,
            models_tried=result.models_tried,
            simulated_response=result.simulated_response,
            token_breakdown={
                "model_cascade": {
                    "input_tokens": result.cascade_input_tokens,
                    "output_tokens": result.cascade_output_tokens,
                    "total_tokens": result.cascade_input_tokens + result.cascade_output_tokens,
                },
                "attempts": result.model_attempts,
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
        "- `MID`  (`tier=2`): `gemini-flash`, `llama-70b`\n"
        "- `HIGH` (`tier=3`): `gemini-pro`\n\n"
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

        print("\n" + "-" * 60)
        print("[LLM_SIM] Incoming prompt received")
        print(f"[LLM_SIM] Tier resolved: {route_result.tier} ({'LOW' if route_result.tier == 1 else 'MID' if route_result.tier == 2 else 'HIGH'})")
        print(f"[LLM_SIM] Reason      : {route_result.reason}")
        print("-" * 60)

        result = dispatch(prompt=request.prompt, tier=route_result.tier)

        return LLMSimulateResponse(
            tier_number=result.tier_number,
            tier_name=result.tier_name,
            tier_reason=route_result.reason,
            model_used=result.model_used,
            models_tried=result.models_tried,
            prompt_sent=result.prompt_sent,
            simulated_response=result.simulated_response,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
