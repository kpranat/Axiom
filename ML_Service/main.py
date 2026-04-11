import os

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

load_dotenv()

from routes.router import api_router
from core.tier_router import route as tier_route

app = FastAPI(
    title="ML Service — TokenMiser",
    description="Context summariser and ML utilities for the Axiom platform.",
    version="1.0.0",
)

app.include_router(api_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Simple liveness probe."""
    return {"status": "ok"}


# ── TEMPORARY: Phase 1 debug endpoint — remove after Phase 3 is wired ────────

class _TestRouteRequest(BaseModel):
    prompt: str
    context: Optional[str] = None


@app.post("/test-route", tags=["Debug"])
async def test_tier_route(req: _TestRouteRequest):
    """Temporary endpoint to test the tier router directly. Remove after Phase 3."""
    result = tier_route(req.prompt, req.context)
    return {
        "tier": result.tier,
        "score": result.score,
        "reason": result.reason,
    }
