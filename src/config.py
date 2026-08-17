"""Configuration settings for Local Database QA System."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = BASE_DIR / "documents"
VECTOR_DB_DIR = BASE_DIR / "vector_db"

DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)

CHROMA_DB_PATH = str(VECTOR_DB_DIR)
CHROMA_COLLECTION = "local_qa_collection"

# Ollama API Endpoint
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# Default Embedding Model
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
