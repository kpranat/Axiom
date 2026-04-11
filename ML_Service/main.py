import os

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from routes.router import api_router

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
