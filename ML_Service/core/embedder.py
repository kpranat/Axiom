"""
core/embedder.py
----------------
Single sentence-transformers encoder for semantic caching.

Model:
  - minilm -> all-MiniLM-L6-v2 (384 dims)
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer


MODEL_SPECS: dict[str, dict[str, str | int]] = {
    "minilm": {"name": "all-MiniLM-L6-v2", "dim": 384},
}

def _load_models() -> dict[str, SentenceTransformer]:
    models: dict[str, SentenceTransformer] = {}
    for model_key, spec in MODEL_SPECS.items():
        model_name = str(spec["name"])
        print(f"[EMBEDDER    ] Loading {model_key}: '{model_name}' ...")
        models[model_key] = SentenceTransformer(model_name)
        print(f"[EMBEDDER    ] {model_key} ready")
    return models


_MODELS: dict[str, SentenceTransformer] = {}


def _get_models() -> dict[str, SentenceTransformer]:
    global _MODELS
    if not _MODELS:
        _MODELS = _load_models()
    return _MODELS


def get_model(model_key: str) -> SentenceTransformer:
    models = _get_models()
    if model_key not in models:
        supported = ", ".join(sorted(models))
        raise ValueError(f"Unknown embedding model '{model_key}'. Supported: {supported}")
    return models[model_key]


def get_model_dimensions() -> dict[str, int]:
    return {model_key: int(spec["dim"]) for model_key, spec in MODEL_SPECS.items()}


def embed(text: str, model_key: str = "minilm") -> np.ndarray:
    """
    Encode text with the requested model and return a float32 vector.
    normalize_embeddings=True returns L2-normalised vectors directly.
    """
    model = get_model(model_key)
    vec = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
    return vec.astype(np.float32)


def embed_all(text: str) -> dict[str, np.ndarray]:
    """Encode the same text with every configured model."""
    return {model_key: embed(text, model_key) for model_key in _get_models()}
