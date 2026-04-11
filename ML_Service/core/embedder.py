"""
core/embedder.py
----------------
Singleton sentence-transformers encoder.

Model : all-MiniLM-L6-v2
Output: 384-dim float32 vectors (already normalised by the model)

The model is loaded once at import time and reused across all requests,
keeping latency low and memory constant.
"""

import numpy as np
from sentence_transformers import SentenceTransformer

# Load once — intentionally module-level so FastAPI workers share it.
_MODEL_NAME = "all-MiniLM-L6-v2"
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print(f"[EMBEDDER    ] Loading model '{_MODEL_NAME}' ...")
        _model = SentenceTransformer(_MODEL_NAME)
        print(f"[EMBEDDER    ] Model ready ✅")
    return _model


def embed(text: str) -> np.ndarray:
    """
    Encode text and return a 384-dim float32 numpy vector.
    normalize_embeddings=True returns L2-normalised vectors directly.
    """
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
    return vec.astype(np.float32)
