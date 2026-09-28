"""
Sentence-transformer wrapper for computing embeddings and similarity.

Uses safetensors format to avoid pickle deserialization issues.
Model is loaded once and reused (lazy singleton).
"""

import logging
import threading

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from config import settings

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None
_lock = threading.Lock()

_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
if _DEVICE == "cuda":
    logger.info("Using GPU: %s", torch.cuda.get_device_name(0))
else:
    logger.info("Using CPU for embeddings (no GPU found)")


def _get_model() -> SentenceTransformer:
    """Load model on first call, reuse after that."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                logger.info("Loading '%s' on %s...", settings.EMBEDDING_MODEL, _DEVICE)
                _model = SentenceTransformer(
                    settings.EMBEDDING_MODEL,
                    device=_DEVICE,
                    model_kwargs={"use_safetensors": True},
                )
                logger.info("Model loaded.")
    return _model


def embed(text: str) -> np.ndarray:
    """Get a normalized embedding vector for the given text."""
    model = _get_model()
    return model.encode(text, normalize_embeddings=True, show_progress_bar=False)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two normalized vectors (just a dot product)."""
    return float(np.clip(np.dot(a, b), 0.0, 1.0))


def compute_similarity(text_a: str, text_b: str) -> float:
    """Embed two strings and return their cosine similarity."""
    return cosine_similarity(embed(text_a), embed(text_b))
