"""Local Embedding Engine using SentenceTransformers."""

from __future__ import annotations
import numpy as np
from sentence_transformers import SentenceTransformer
from src.config import EMBEDDING_MODEL_NAME

_model_instance = None


def get_embedding_model() -> SentenceTransformer:
    """Return a singleton instance of the local SentenceTransformer model."""
    global _model_instance
    if _model_instance is None:
        _model_instance = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model_instance


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Generate L2-normalized embeddings for a list of document chunks."""
    if not texts:
        return []
    model = get_embedding_model()
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return embeddings.tolist()


def embed_query(query: str) -> list[float]:
    """Generate L2-normalized embedding for a search query."""
    if not query.strip():
        return []
    model = get_embedding_model()
    embedding = model.encode(query, normalize_embeddings=True, show_progress_bar=False)
    return embedding.tolist()
