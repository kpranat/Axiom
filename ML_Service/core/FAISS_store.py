"""
core/FAISS_store.py
-------------------
FAISS-backed in-memory vector store.

Design follows the TokenMiser reference:
  - IndexFlatIP  -> exact inner-product (= cosine sim on L2-normalised vecs)
  - All vectors are pre-normalised before insertion / search
  - Threshold-based retrieval (default 0.80)
"""

from __future__ import annotations

import numpy as np
import faiss

from core.embedder import get_model_dimensions


# ──────────────────────────────────────────────────────────────────────────────
# Core store
# ──────────────────────────────────────────────────────────────────────────────

class FaissStore:
    """Single-namespace FAISS vector store (global OR one user)."""

    def __init__(self, dim: int):
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)
        self.entries: list[dict[str, str]] = []

    def _normalise(self, vec: np.ndarray) -> np.ndarray:
        """Return an L2-normalised float32 copy of vec."""
        norm = np.linalg.norm(vec)
        if norm == 0:
            return vec.astype(np.float32)
        return (vec / norm).astype(np.float32)

    def probe(self, embedding: np.ndarray, threshold: float = 0.80) -> dict:
        """
        Return the best-match metadata even if it misses the threshold.
        This lets the caller compare raw similarity scores across models.
        """
        if self.index.ntotal == 0:
            return {
                "hit": False,
                "score": None,
                "query": None,
                "response": None,
            }

        normed = self._normalise(embedding).reshape(1, -1)
        distances, indices = self.index.search(normed, k=1)

        score = round(float(distances[0][0]), 4)
        idx = int(indices[0][0])
        entry = self.entries[idx]

        return {
            "hit": score >= threshold,
            "score": score,
            "query": entry["query"],
            "response": entry["response"],
        }

    def search(self, embedding: np.ndarray, threshold: float = 0.80) -> dict | None:
        result = self.probe(embedding, threshold)
        if not result["hit"]:
            return None
        return {
            "query": result["query"],
            "response": result["response"],
            "score": result["score"],
        }

    def store(self, embedding: np.ndarray, query: str, response: str) -> None:
        """Add a new (query, response) pair to the store."""
        normed = self._normalise(embedding).reshape(1, -1)
        self.index.add(normed)
        self.entries.append({"query": query, "response": response})

    @property
    def size(self) -> int:
        return self.index.ntotal


# ──────────────────────────────────────────────────────────────────────────────
# Multi-layer store manager
# ──────────────────────────────────────────────────────────────────────────────

class CacheManager:
    """
    Two-layer semantic cache mirrored across multiple embedding models:
      Layer 1 - global   (shared across all users)
      Layer 2 - personal (isolated per user_id)
    """

    def __init__(
        self,
        model_dims: dict[str, int] | None = None,
        threshold: float = 0.80,
    ):
        self.model_dims = model_dims or get_model_dimensions()
        self.threshold = threshold
        self.primary_model = next(iter(self.model_dims))
        self.global_stores = {
            model_key: FaissStore(dim)
            for model_key, dim in self.model_dims.items()
        }
        self.user_stores: dict[str, dict[str, FaissStore]] = {}

    def _ensure_user_stores(self, user_id: str) -> dict[str, FaissStore]:
        if user_id not in self.user_stores:
            self.user_stores[user_id] = {
                model_key: FaissStore(dim)
                for model_key, dim in self.model_dims.items()
            }
        return self.user_stores[user_id]

    def _empty_probe(self) -> dict:
        return {"hit": False, "score": None, "query": None, "response": None}

    def _probe_all(
        self,
        stores: dict[str, FaissStore],
        embeddings: dict[str, np.ndarray],
    ) -> dict[str, dict]:
        results: dict[str, dict] = {}
        for model_key, store in stores.items():
            embedding = embeddings.get(model_key)
            if embedding is None:
                raise ValueError(f"Missing embedding for model '{model_key}'")
            results[model_key] = store.probe(embedding, self.threshold)
        return results

    def best_hit(self, results: dict[str, dict]) -> dict | None:
        best_model: str | None = None
        best_result: dict | None = None
        for model_key, result in results.items():
            if not result["hit"]:
                continue
            if best_result is None or result["score"] > best_result["score"]:
                best_model = model_key
                best_result = result

        if best_model is None or best_result is None:
            return None

        return {
            "model": best_model,
            "query": best_result["query"],
            "response": best_result["response"],
            "score": best_result["score"],
        }

    def search_global_all(self, embeddings: dict[str, np.ndarray]) -> dict[str, dict]:
        return self._probe_all(self.global_stores, embeddings)

    def search_personal_all(self, user_id: str, embeddings: dict[str, np.ndarray]) -> dict[str, dict]:
        stores = self.user_stores.get(user_id)
        if stores is None:
            return {model_key: self._empty_probe() for model_key in self.model_dims}
        return self._probe_all(stores, embeddings)

    def search_global(self, embeddings: dict[str, np.ndarray]) -> dict | None:
        return self.best_hit(self.search_global_all(embeddings))

    def search_personal(self, user_id: str, embeddings: dict[str, np.ndarray]) -> dict | None:
        return self.best_hit(self.search_personal_all(user_id, embeddings))

    def store_global_all(self, embeddings: dict[str, np.ndarray], query: str, response: str) -> None:
        for model_key, embedding in embeddings.items():
            self.global_stores[model_key].store(embedding, query, response)

    def store_personal_all(
        self,
        user_id: str,
        embeddings: dict[str, np.ndarray],
        query: str,
        response: str,
    ) -> None:
        stores = self._ensure_user_stores(user_id)
        for model_key, embedding in embeddings.items():
            stores[model_key].store(embedding, query, response)

    def stats(self) -> dict:
        logical_user_stores = {
            user_id: stores[self.primary_model].size
            for user_id, stores in self.user_stores.items()
        }
        return {
            "global_entries": self.global_stores[self.primary_model].size,
            "user_stores": logical_user_stores,
            "model_global_entries": {
                model_key: store.size
                for model_key, store in self.global_stores.items()
            },
            "model_user_stores": {
                model_key: {
                    user_id: stores[model_key].size
                    for user_id, stores in self.user_stores.items()
                }
                for model_key in self.model_dims
            },
        }

    def reset(self) -> None:
        self.global_stores = {
            model_key: FaissStore(dim)
            for model_key, dim in self.model_dims.items()
        }
        self.user_stores.clear()


# Singleton used by all route handlers
cache_manager = CacheManager()
