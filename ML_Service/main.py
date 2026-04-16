import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from core.classifier import classify
from core.embedder import embed
from core.router_adapter import route as route_tier
from routes.router import api_router

app = FastAPI(
    title="ML Service — TokenMiser",
    description="Context summariser and ML utilities for the Axiom platform.",
    version="1.0.0",
)

app.include_router(api_router)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _run_warmup_step(name: str, fn) -> None:
    started = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - started
    print(f"[WARMUP      ] {name} ready in {elapsed:.2f}s")


@app.on_event("startup")
async def warmup_models() -> None:
    """
    Warm up lazy-loaded ML components at process startup.

    This avoids first-request latency spikes and reduces timeout risk while
    model weights/tokenizers are being loaded for the first time.
    """
    if not _env_flag("AXIOM_WARMUP_MODELS", True):
        print("[WARMUP      ] disabled (AXIOM_WARMUP_MODELS=false)")
        return

    print("[WARMUP      ] starting ML component preload")

    steps = [
        ("embedder", lambda: embed("warmup", model_key="minilm")),
        ("classifier", lambda: classify("warmup prompt")),
    ]

    if _env_flag("AXIOM_WARMUP_ROUTER", True):
        steps.append(("router", lambda: route_tier("warmup prompt")))

    for name, step in steps:
        try:
            _run_warmup_step(name, step)
        except Exception as exc:
            # Keep service startup resilient if optional warmup fails.
            print(f"[WARMUP      ] {name} failed: {exc}")

    print("[WARMUP      ] completed")


@app.get("/health", tags=["Health"])
async def health_check():
    """Simple liveness probe."""
    return {"status": "ok"}
