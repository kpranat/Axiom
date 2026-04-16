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

<<<<<<< HEAD
from core.llm_dispatcher import dispatch
from core.router_adapter import route as tier_route
=======
from core.gateway import run_cascade, build_billing_summary
from core.tier_router import route as tier_route
>>>>>>> modelcascader
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
        # Use the production-grade gateway instead of the simulated dispatcher
        result = run_cascade(request.prompt_to_send, start_tier=request.tier)
        
        full_text = ""
        if result.is_streaming and result.stream_generator:
            for chunk in result.stream_generator:
                full_text += chunk
        
        result.response = full_text
        billing = build_billing_summary(result)
        
        return LLMInvokeResponse(
            tier_number=result.tier_reached,
            tier_name="LOW" if result.tier_reached == 1 else "MID" if result.tier_reached == 2 else "HIGH",
            model_used="gemini-2.5-flash" if result.tier_reached == 3 else "llama-3.1" if result.tier_reached == 1 else "llama-3.3",
            models_tried=[f"tier{i}" for i in range(request.tier, result.tier_reached + 1)],
            simulated_response=full_text,
            token_breakdown={
                "model_cascade": {
                    "input_tokens": sum(result.input_tokens_used.values()),
                    "output_tokens": 0, # Calculated in billing
                    "total_tokens": sum(result.input_tokens_used.values()),
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
        print("[LLM_GATEWAY] Incoming prompt received")
        print(f"[LLM_GATEWAY] Tier resolved: {route_result.tier} ({'LOW' if route_result.tier == 1 else 'MID' if route_result.tier == 2 else 'HIGH'})")
        print(f"[LLM_GATEWAY] Reason      : {route_result.reason}")
        print("-" * 60)

        # Use the gateway instead of the simulated dispatcher
        result = run_cascade(request.prompt, start_tier=route_result.tier)
        
        full_text = ""
        if result.is_streaming and result.stream_generator:
            for chunk in result.stream_generator:
                full_text += chunk
        
        return LLMSimulateResponse(
            tier_number=result.tier_reached,
            tier_name="LOW" if result.tier_reached == 1 else "MID" if result.tier_reached == 2 else "HIGH",
            tier_reason=route_result.reason,
            model_used="gemini-2.5-flash" if result.tier_reached == 3 else "llama-native",
            models_tried=[f"tier{i}" for i in range(route_result.tier, result.tier_reached + 1)],
            prompt_sent=request.prompt,
            simulated_response=full_text,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
