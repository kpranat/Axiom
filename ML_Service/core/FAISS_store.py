"""
core/FAISS_store.py
-------------------
FAISS-backed in-memory vector store.

Design follows the TokenMiser reference:
  - IndexFlatIP  -> exact inner-product (= cosine sim on L2-normalised vecs)
  - All vectors are pre-normalised before insertion / search
  - Threshold-based retrieval (default 0.87)
"""

import numpy as np
import faiss


# ──────────────────────────────────────────────────────────────────────────────
# Core store
# ──────────────────────────────────────────────────────────────────────────────

class FaissStore:
    """Single-namespace FAISS vector store (global OR one user)."""

    def __init__(self, dim: int = 384):
        self.index = faiss.IndexFlatIP(dim)   # inner-product index
        self.entries: list[dict] = []          # parallel list of {query, response}

    def _normalise(self, vec: np.ndarray) -> np.ndarray:
        """Return L2-normalised copy of vec (shape: [dim])."""
        norm = np.linalg.norm(vec)
        if norm == 0:
            return vec
        return (vec / norm).astype(np.float32)

    def search(self, embedding: np.ndarray, threshold: float = 0.87) -> dict | None:
        """
        Return the best-matching entry if its cosine similarity >= threshold,
        otherwise return None.
        """
        if self.index.ntotal == 0:
            return None

        normed = self._normalise(embedding).reshape(1, -1)
        D, I = self.index.search(normed, k=1)

        score: float = float(D[0][0])
        idx: int = int(I[0][0])

        if score >= threshold:
            return {**self.entries[idx], "score": round(score, 4)}
        return None

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
    Two-layer semantic cache:
      Layer 1 - global  (shared across all users)
      Layer 2 - personal (isolated per user_id)
    """

    def __init__(self, dim: int = 384, threshold: float = 0.87):
        self.dim = dim
        self.threshold = threshold
        self.global_store = FaissStore(dim)
        self.user_stores: dict[str, FaissStore] = {}

    def _user_store(self, user_id: str) -> FaissStore:
        if user_id not in self.user_stores:
            self.user_stores[user_id] = FaissStore(self.dim)
        return self.user_stores[user_id]

    def search_global(self, embedding: np.ndarray) -> dict | None:
        return self.global_store.search(embedding, self.threshold)

    def search_personal(self, user_id: str, embedding: np.ndarray) -> dict | None:
        return self._user_store(user_id).search(embedding, self.threshold)

    def store_global(self, embedding: np.ndarray, query: str, response: str) -> None:
        self.global_store.store(embedding, query, response)

    def store_personal(self, user_id: str, embedding: np.ndarray, query: str, response: str) -> None:
        self._user_store(user_id).store(embedding, query, response)

    def stats(self) -> dict:
        return {
            "global_entries": self.global_store.size,
            "user_stores": {uid: s.size for uid, s in self.user_stores.items()},
        }


# Singleton used by all route handlers
cache_manager = CacheManager()
