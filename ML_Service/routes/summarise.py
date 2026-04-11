from fastapi import APIRouter, HTTPException

from core.summariser import summarize
from models.schemas import SummariseRequest, SummariseResponse

router = APIRouter(prefix="/summarise", tags=["Summariser"])


@router.post("/", response_model=SummariseResponse, summary="Summarise a conversation")
async def summarise_conversation(request: SummariseRequest) -> SummariseResponse:
    """
    Accepts a list of conversation messages and returns a compact 5-sentence
    summary along with the number of tokens saved.
    """
    try:
        messages_as_dicts = [m.model_dump() for m in request.messages]
        summary, tokens_saved = summarize(messages_as_dicts)
        return SummariseResponse(summary=summary, tokens_saved=tokens_saved)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
