"""
core/router_adapter.py
----------------------
Adapter that routes prompts through routerFunctionML first,
with a safe fallback to the legacy heuristic router.
"""

from __future__ import annotations

import importlib
import re
from typing import Callable, Optional

from core.tier_router import RouteResult, route as legacy_route

_router_fn: Optional[Callable[[str], str]] = None
_router_load_error: Optional[Exception] = None


def _load_router_function() -> None:
    """Lazy-load routerFunctionML.get_route once per process."""
    global _router_fn, _router_load_error

    if _router_fn is not None or _router_load_error is not None:
        return

    try:
        module = importlib.import_module("routerFunctionML.test_router")
        candidate = getattr(module, "get_route", None)
        if not callable(candidate):
            raise AttributeError("routerFunctionML.test_router.get_route is not callable")
        _router_fn = candidate
    except Exception as exc:  # pragma: no cover - fallback path
        _router_load_error = exc


def _parse_tier(label: str) -> Optional[int]:
    """Parse tier labels like 'tier_2' or '2' into int tier."""
    if not label:
        return None

    match = re.search(r"([1-3])", str(label))
    if not match:
        return None

    return int(match.group(1))


def route(prompt: str, context: Optional[str] = None) -> RouteResult:
    """
    Route via routerFunctionML first, fallback to legacy heuristic router.

    Args:
        prompt: user prompt text.
        context: optional summarized context.

    Returns:
        RouteResult with tier and reason.
    """
    _load_router_function()

    query = (prompt or "").strip()
    if context and context.strip():
        query = f"{context.strip()}\n\n{query}"

    if _router_fn is not None:
        try:
            raw_label = _router_fn(query)
            tier = _parse_tier(raw_label)
            if tier is not None:
                return RouteResult(
                    tier=tier,
                    score=0,
                    reason=f"[router=llama] routerFunctionML selected {raw_label}",
                )

            fallback = legacy_route(prompt, context)
            return RouteResult(
                tier=fallback.tier,
                score=fallback.score,
                reason=f"[router=fallback-parse] routerFunctionML parse fallback: {raw_label}; {fallback.reason}",
            )
        except Exception as exc:  # pragma: no cover - runtime fallback
            fallback = legacy_route(prompt, context)
            return RouteResult(
                tier=fallback.tier,
                score=fallback.score,
                reason=f"[router=fallback-runtime] routerFunctionML runtime fallback: {exc}; {fallback.reason}",
            )

    fallback = legacy_route(prompt, context)
    if _router_load_error is None:
        return fallback

    return RouteResult(
        tier=fallback.tier,
        score=fallback.score,
        reason=f"[router=fallback-load] routerFunctionML load fallback: {_router_load_error}; {fallback.reason}",
    )
