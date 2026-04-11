"""
routes/embed.py
---------------
Utility endpoint: embed a text string and return the raw vector.
Handy for debugging similarity thresholds without going through the full cache.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from core.embedder import embed

router = APIRouter(prefix="/embed", tags=["Embedder"])


class EmbedRequest(BaseModel):
    text: str


class EmbedResponse(BaseModel):
    text: str
    dim: int
    vector: list[float]


@router.post(
    "/",
    response_model=EmbedResponse,
    summary="Embed a text string and return the raw vector",
)
async def embed_text(request: EmbedRequest) -> EmbedResponse:
    """
    Encode text with all-MiniLM-L6-v2 and return the 384-dim vector.
    Useful for manual similarity inspection.
    """
    vec = embed(request.text)
    return EmbedResponse(text=request.text, dim=len(vec), vector=vec.tolist())
