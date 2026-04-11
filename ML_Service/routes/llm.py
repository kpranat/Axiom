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
from models.schemas import LLMInvokeRequest, LLMInvokeResponse

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
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
