"""
routes/cache.py
---------------
/cache/query  — main semantic-cache endpoint
/cache/stats  — inspect cache sizes
/cache/reset  — clear all caches (useful during demos)
"""

from fastapi import APIRouter
from models.schemas import QueryRequest, QueryResponse, CacheStatsResponse
from core.cascader import process_query
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

    Flow:
    1. Classify prompt (PERSONAL / GENERIC)
    2. Embed prompt (all-MiniLM-L6-v2, 384-dim)
    3. Check GLOBAL FAISS store
    4. If miss -> check PERSONAL FAISS store
    5. If miss -> invoke mock LLM
    6. Store result in the appropriate layer

    All steps are logged to the terminal in real-time.
    """
    result = process_query(request.prompt, request.user_id)
    return QueryResponse(**result)


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
