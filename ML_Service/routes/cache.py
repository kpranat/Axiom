"""
routes/cache.py
---------------
/cache/query            — main semantic-cache endpoint
/cache/store            — store a response in the cache
/cache/stats            — inspect cache sizes
/cache/reset            — clear all caches (useful during demos)
/cache/debug-similarity — compare cosine similarity of two prompts
"""

from fastapi import APIRouter
from pydantic import BaseModel
from models.schemas import (
    QueryRequest,
    QueryResponse,
    CacheStoreRequest,
    CacheStoreResponse,
    CacheStatsResponse,
)
from core.cascader import lookup_query, store_response, debug_similarity
from core.FAISS_store import cache_manager

router = APIRouter(prefix="/cache", tags=["Semantic Cache"])


# ──────────────────────────────────────────────────────────────────────────────
# /cache/query  — primary endpoint
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Semantic cache query with two-layer retrieval",
)
async def query(request: QueryRequest) -> QueryResponse:
    """
    Process a prompt through the two-layer semantic cache.

    Cache lookup only:
    1. Classify prompt (PERSONAL / GENERIC)
    2. Embed prompt with minilm sentence-transformer
    3. Check GLOBAL then PERSONAL FAISS stores
    4. Return hit metadata or miss metadata
    """
    result = lookup_query(request.prompt, request.user_id)
    return QueryResponse(**result)


@router.post(
    "/store",
    response_model=CacheStoreResponse,
    summary="Store final response in semantic cache",
)
async def store(request: CacheStoreRequest) -> CacheStoreResponse:
    """
    Store a final model response after route/invoke on cache miss.
    """
    result = store_response(
        prompt=request.prompt,
        user_id=request.user_id,
        response=request.response,
        classified=request.classified,
    )
    return CacheStoreResponse(**result)


# ──────────────────────────────────────────────────────────────────────────────
# /cache/stats
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/stats",
    response_model=CacheStatsResponse,
    summary="Current cache sizes",
)
async def cache_stats() -> CacheStatsResponse:
    """Return the number of entries stored in global and per-user caches."""
    stats = cache_manager.stats()
    return CacheStatsResponse(
        global_entries=stats["global_entries"],
        user_stores=stats["user_stores"],
        model_global_entries=stats["model_global_entries"],
        model_user_stores=stats["model_user_stores"],
    )


# ──────────────────────────────────────────────────────────────────────────────
# /cache/reset
# ──────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/reset",
    summary="Reset all caches (demo utility)",
)
async def reset_cache() -> dict:
    """
    Wipe the global FAISS store and all per-user stores.
    Useful between demo runs to start fresh.
    """
    cache_manager.reset()
    print("[RESET       ] Semantic cache cleared")
    return {"status": "ok", "message": "All caches reset."}


# ──────────────────────────────────────────────────────────────────────────────
# /cache/debug-similarity
# ──────────────────────────────────────────────────────────────────────────────

class DebugSimilarityRequest(BaseModel):
    prompt_a: str
    prompt_b: str


class DebugSimilarityResponse(BaseModel):
    prompt_a: str
    prompt_b: str
    similarity: dict[str, float]
    threshold: float
    would_hit: dict[str, bool]


@router.post(
    "/debug-similarity",
    response_model=DebugSimilarityResponse,
    summary="[DEBUG] Compare cosine similarity of two prompts",
)
async def debug_similarity_endpoint(request: DebugSimilarityRequest) -> DebugSimilarityResponse:
    """
    Compute the raw cosine similarity between two prompts using
    the MiniLM-L6-v2 (384d) embedding model.

    Results are printed to the terminal **and** returned in the JSON response.
    Use this to understand why a cache hit did or did not fire and to calibrate
    the similarity threshold.

    **Example use-case**: compare `"give recipe to make tea"` vs
    `"how to make tea"` to see which model scores them closer together.
    """
    result = debug_similarity(request.prompt_a, request.prompt_b)
    return DebugSimilarityResponse(**result)
