"""
routes/route.py
---------------
POST /route/

Full router pipeline endpoint:
    1. Use the raw user prompt (no optimizer step).
    2. If context was supplied, combine it with the raw prompt.
    3. Call the tier router  → assign tier 1 | 2 | 3.
    4. Append confidence few-shot instructions for cascade decisions.
  5. Return { prompt_to_send, tier, reason, original_tokens, optimized_tokens, tokens_saved }.

The caller is responsible for forwarding prompt_to_send to the appropriate LLM.
"""

from fastapi import APIRouter, HTTPException

from core.router_adapter import route as tier_route
from core.confidence_few_shot import build_confidence_block
from models.schemas import RouteRequest, RouteResponse

router = APIRouter(tags=["Router"])


def _rough_token_count(text: str) -> int:
    return len((text or "").split())


@router.post(
    "/route",
    response_model=RouteResponse,
    summary="Route a prompt to the appropriate model tier",
)
@router.post(
    "/route/",
    response_model=RouteResponse,
    include_in_schema=False,   # hides the duplicate from /docs
)
async def route_prompt(request: RouteRequest) -> RouteResponse:
    """
    Accepts a user prompt (and optional pre-summarised context) and returns:

    - **prompt_to_send** — prompt ready for the LLM.
    - **tier** — target model tier (1 = small/fast, 2 = mid, 3 = large/frontier).
    - **reason** — primary heuristic signal that drove the tier decision.
    - **original_tokens** — word-count before route-time processing.
    - **optimized_tokens** — same as original (optimizer disabled).
    - **tokens_saved** — always 0 (optimizer disabled).

    The caller forwards `prompt_to_send` to the model mapped to `tier`.
    """
    try:
        active_context = request.context.strip() if request.context else None
        raw_prompt = request.prompt.strip()
        original_tokens = _rough_token_count(raw_prompt)
        if active_context:
            original_tokens += _rough_token_count(active_context)

        # ── 1. Route tier using raw prompt (+ context signal if present) ─────
        route_result = tier_route(raw_prompt, active_context)

        # ── 2. Build final prompt by combining raw prompt + context ──────────
        if active_context:
            final_prompt = f"[CONTEXT]\n{active_context}\n\n[PROMPT]\n{raw_prompt}"
        else:
            final_prompt = raw_prompt

        # ── 3. Append few-shot confidence block ──────────────────────────────
        confidence_block = build_confidence_block(route_result.tier)
        final_prompt = f"{final_prompt}\n\n{confidence_block}"

        # ── 4. Return ─────────────────────────────────────────────────────────
        return RouteResponse(
            prompt_to_send=final_prompt,
            tier=route_result.tier,
            reason=route_result.reason,
            original_tokens=original_tokens,
            optimized_tokens=original_tokens,
            tokens_saved=0,
            token_breakdown={
                "optimize_prompt": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                }
            },
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
