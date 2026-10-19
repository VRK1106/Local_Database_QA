"""Local Embedding Engine using SentenceTransformers with strict memory constraints."""

from __future__ import annotations
import gc
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from src.config import EMBEDDING_MODEL_NAME
from src.memory_utils import trim_memory

# Restrict linear algebra thread allocation to 2 threads to conserve glibc memory arenas
try:
    torch.set_num_threads(2)
except Exception:
    pass

_model_instance = None


def get_embedding_model() -> SentenceTransformer:
    """Return a singleton instance of the local SentenceTransformer model."""
    global _model_instance
    if _model_instance is None:
        _model_instance = SentenceTransformer(EMBEDDING_MODEL_NAME)
        # Ensure eval mode to turn off dropout/training buffers
        _model_instance.eval()
    return _model_instance


def embed_documents(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Generate L2-normalized embeddings for a list of document chunks with bounded batch memory."""
    if not texts:
        return []
    model = get_embedding_model()
    with torch.inference_mode():
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True
        )
    result = embeddings.tolist()
    del embeddings
    trim_memory()
    return result


def embed_query(query: str) -> list[float]:
    """Generate L2-normalized embedding for a search query without autograd overhead."""
    if not query.strip():
        return []
    model = get_embedding_model()
    with torch.inference_mode():
        embedding = model.encode(
            query,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True
        )
    result = embedding.tolist()
    del embedding
    return result
