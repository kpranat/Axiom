from fastapi import APIRouter, HTTPException

from core.classifier import classify
from models.schemas import ClassifyRequest, ClassifyResponse

router = APIRouter(prefix="/classify", tags=["Classifier"])


@router.post(
    "/",
    response_model=ClassifyResponse,
    summary="Classify whether a prompt needs conversation context",
)
async def classify_prompt(request: ClassifyRequest) -> ClassifyResponse:
    """
    Accepts the latest user message and returns:
    - **needs_context** — whether prior conversation history is required.
    - **confidence** — classifier certainty (0.0 – 1.0).
    - **reason** — the strongest linguistic signal that drove the decision.

    This endpoint is fully local — no external API calls are made.
    """
    try:
        needs_context, confidence, reason = classify(request.prompt)
        return ClassifyResponse(
            needs_context=needs_context,
            confidence=confidence,
            reason=reason,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
