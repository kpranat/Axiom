"""
routes/cache.py
---------------
/cache/query  — main semantic-cache endpoint
/cache/stats  — inspect cache sizes
/cache/reset  — clear all caches (useful during demos)
"""

from fastapi import APIRouter
from models.schemas import (
    QueryRequest,
    QueryResponse,
    CacheStoreRequest,
    CacheStoreResponse,
    CacheStatsResponse,
)
from core.cascader import lookup_query, store_response
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
    2. Embed prompt (all-MiniLM-L6-v2, 384-dim)
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
    cache_manager.global_store.__init__(cache_manager.dim)
    cache_manager.user_stores.clear()
    print("[RESET       ] All caches cleared ♻️")
    return {"status": "ok", "message": "All caches reset."}
