"""
routes/route.py
---------------
POST /route/

Full router pipeline endpoint:
  1. Run the context classifier on the prompt.
  2. If needs_context=True AND context was supplied, use it; otherwise prompt-only.
  3. Call the tier router  → assign tier 1 | 2 | 3.
  4. Call the prompt optimizer → compress prompt + embed context.
  5. Return { prompt_to_send, tier, reason, original_tokens, optimized_tokens, tokens_saved }.

The caller is responsible for forwarding prompt_to_send to the appropriate LLM.
"""

from fastapi import APIRouter, HTTPException

from core.classifier import classify
from core.tier_router import route as tier_route
from core.prompt_optimizer import optimize as optimize_prompt
from models.schemas import RouteRequest, RouteResponse

router = APIRouter(tags=["Router"])


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

    - **prompt_to_send** — token-optimized, context-embedded prompt ready for the LLM.
    - **tier** — target model tier (1 = small/fast, 2 = mid, 3 = large/frontier).
    - **reason** — primary heuristic signal that drove the tier decision.
    - **original_tokens** — word-count before optimization.
    - **optimized_tokens** — word-count after optimization.
    - **tokens_saved** — reduction delta.

    The caller forwards `prompt_to_send` to the model mapped to `tier`.
    """
    try:
        # ── 1. Context classifier ─────────────────────────────────────────────
        needs_context, _confidence, _clf_reason = classify(request.prompt)

        # active_context controls what gets EMBEDDED in the final prompt.
        # The classifier decides this: only embed context if the prompt
        # explicitly references prior conversation.
        active_context: str | None = (
            request.context if (needs_context and request.context) else None
        )

        # ── 2. Tier router ────────────────────────────────────────────────────
        # Always pass the raw context to the tier router regardless of the
        # classifier — context length is a session-complexity signal (S4),
        # independent of whether the prompt explicitly references it.
        route_result = tier_route(request.prompt, request.context)

        # ── 3. Prompt optimizer ───────────────────────────────────────────────
        # Use active_context here so context is only embedded in the final
        # prompt when the classifier agrees it's needed.
        opt_result = optimize_prompt(request.prompt, active_context, route_result.tier)

        # ── 4. Return ─────────────────────────────────────────────────────────
        return RouteResponse(
            prompt_to_send=opt_result.optimized_prompt,
            tier=route_result.tier,
            reason=route_result.reason,
            original_tokens=opt_result.original_tokens,
            optimized_tokens=opt_result.optimized_tokens,
            tokens_saved=opt_result.tokens_saved,
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
