"""ChromaDB Vector Store: Persistent document indexing, retrieval, and analytics."""

from __future__ import annotations
import sys
import threading
from pathlib import Path

# Thread-safe SQLite patch
try:
    import pysqlite3
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except (ImportError, KeyError):
    pass

import sqlite3
_original_connect = sqlite3.connect
def _patched_connect(*args, **kwargs):
    kwargs['check_same_thread'] = False
    return _original_connect(*args, **kwargs)
sqlite3.connect = _patched_connect

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from src.config import CHROMA_COLLECTION, CHROMA_DB_PATH, DOCUMENTS_DIR

_chroma_lock = threading.RLock()
_client_instance = None
_stats_cache = None
_stats_cache_time = 0.0


def get_client() -> ClientAPI:
    """Return persistent ChromaDB client instance."""
    global _client_instance
    with _chroma_lock:
        if _client_instance is None:
            _client_instance = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    return _client_instance


def get_collection() -> Collection | None:
    """Return cosine-space document collection."""
    try:
        client = get_client()
        return client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"}
        )
    except Exception as e:
        print(f"[ERROR] Failed to obtain vector collection: {e}")
        return None


def invalidate_stats_cache():
    """Clear statistics cache when document index changes."""
    global _stats_cache_time
    _stats_cache_time = 0.0


def ingested_hashes() -> set[str]:
    """Return set of document file hashes already indexed."""
    hashes: set[str] = set()
    try:
        doc_dir = Path(DOCUMENTS_DIR)
        from src.ingest import file_hash
        if doc_dir.exists():
            for f in doc_dir.iterdir():
                if f.is_file() and not f.name.startswith('.'):
                    try:
                        hashes.add(file_hash(f.read_bytes()))
                    except Exception:
                        pass
    except Exception as ex:
        print(f"Error reading ingested hashes: {ex}")
    return hashes


def add_chunks(chunks: list[dict], embeddings: list[list[float]], file_hash: str) -> int:
    """Upsert document chunks and embeddings into collection."""
    if not chunks:
        return 0

    ids = [chunk["id"] for chunk in chunks]
    documents = [chunk["text"] for chunk in chunks]
    metadatas = []
    for chunk in chunks:
        meta = dict(chunk["metadata"])
        meta["file_hash"] = file_hash
        metadatas.append(meta)

    with _chroma_lock:
        collection = get_collection()
        if not collection:
            return 0
        try:
            collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings,
            )
            invalidate_stats_cache()
            return len(ids)
        except Exception as e:
            print(f"[ERROR] Failed to upsert chunks: {e}")
            return 0


def search(
    query_embedding: list[float],
    top_k: int = 4,
    source_filters: list[str] | None = None,
    threshold: float = 0.0,
) -> list[dict]:
    """Query similarity search in ChromaDB and return ranked result objects."""
    with _chroma_lock:
        collection = get_collection()
        if not collection:
            return []
        
        total_count = collection.count()
        if total_count == 0:
            return []

        where_clause = None
        if source_filters:
            if len(source_filters) == 1:
                where_clause = {"source": source_filters[0]}
            elif len(source_filters) > 1:
                where_clause = {"source": {"$in": source_filters}}

        query_k = min(max(top_k * 2, 10), total_count)

        try:
            result = collection.query(
                query_embeddings=[query_embedding],
                n_results=query_k,
                where=where_clause,
                include=["documents", "metadatas", "distances"],
            )

            documents = (result.get("documents") or [[]])[0]
            metadatas = (result.get("metadatas") or [[]])[0]
            distances = (result.get("distances") or [[]])[0]

            hits = []
            for text, meta, distance in zip(documents, metadatas, distances):
                meta = meta or {}
                source_name = meta.get("source", "Unknown Document")
                
                # Strict post-filter check
                if source_filters and source_name not in source_filters:
                    continue

                score = max(0.0, 1.0 - float(distance))
                if score >= threshold:
                    hits.append({
                        "text": text,
                        "source": source_name,
                        "page": meta.get("page", 1),
                        "chunk_index": meta.get("chunk_index", 0),
                        "score": round(score, 4),
                    })

            hits.sort(key=lambda x: x["score"], reverse=True)
            return hits[:top_k]
        except Exception as e:
            print(f"[ERROR] Vector search query failed: {e}")
            return []


def delete_source(source_name: str) -> bool:
    """Delete all chunks for a specific document source."""
    with _chroma_lock:
        collection = get_collection()
        if not collection:
            return False
        try:
            res = collection.get(where={"source": source_name})
            ids = res.get("ids") or []
            if ids:
                collection.delete(ids=ids)
            
            # Remove file from documents directory if it exists
            doc_file = Path(DOCUMENTS_DIR) / source_name
            if doc_file.exists():
                doc_file.unlink()
                
            invalidate_stats_cache()
            return True
        except Exception as e:
            print(f"[ERROR] Failed to delete source {source_name}: {e}")
            return False


def get_source_chunks(source_name: str) -> list[dict]:
    """Retrieve all chunks of a specific document for inspection."""
    with _chroma_lock:
        collection = get_collection()
        if not collection:
            return []
        try:
            result = collection.get(
                where={"source": source_name},
                include=["documents", "metadatas"],
            )
            documents = result.get("documents") or []
            metadatas = result.get("metadatas") or []
            ids = result.get("ids") or []

            chunks = []
            for doc_id, text, meta in zip(ids, documents, metadatas):
                meta = meta or {}
                chunks.append({
                    "id": doc_id,
                    "text": text,
                    "page": meta.get("page", 1),
                    "chunk_index": meta.get("chunk_index", 0)
                })
            chunks.sort(key=lambda x: (x["page"], x["chunk_index"]))
            return chunks
        except Exception:
            return []


def stats() -> dict:
    """Return cached or freshly retrieved vector collection statistics."""
    global _stats_cache, _stats_cache_time
    import time
    now = time.time()
    if _stats_cache is not None and (now - _stats_cache_time) < 15.0:
        return _stats_cache

    fallback = {
        "total_chunks": 0,
        "sources": 0,
        "source_names": [],
        "source_details": [],
    }

    with _chroma_lock:
        collection = get_collection()
        if not collection:
            return fallback

        try:
            total = collection.count()
            if not total:
                _stats_cache = fallback
                _stats_cache_time = now
                return fallback

            sources_dict: dict[str, int] = {}
            source_pages: dict[str, set[int]] = {}

            result = collection.get(include=["metadatas"])
            for meta in result.get("metadatas") or []:
                meta = meta or {}
                src = meta.get("source")
                if src:
                    sources_dict[src] = sources_dict.get(src, 0) + 1
                    page = meta.get("page")
                    if page is not None:
                        if src not in source_pages:
                            source_pages[src] = set()
                        source_pages[src].add(page)

            source_details = []
            for src in sorted(sources_dict.keys()):
                pages_set = source_pages.get(src, set())
                source_details.append({
                    "name": src,
                    "chunks": sources_dict[src],
                    "pages": len(pages_set) if len(pages_set) > 0 else 1,
                })

            res = {
                "total_chunks": total,
                "sources": len(sources_dict),
                "source_names": sorted(sources_dict.keys()),
                "source_details": source_details,
            }
            _stats_cache = res
            _stats_cache_time = now
            return res
        except Exception as e:
            print(f"[WARN] Error fetching vectorstore stats: {e}")
            return _stats_cache if _stats_cache is not None else fallback


def reset_collection() -> None:
    """Completely wipe the vector database collection and documents."""
    with _chroma_lock:
        client = get_client()
        try:
            client.delete_collection(CHROMA_COLLECTION)
        except Exception:
            pass
        client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"}
        )
        
        # Remove documents from directory
        doc_dir = Path(DOCUMENTS_DIR)
        if doc_dir.exists():
            for f in doc_dir.iterdir():
                if f.is_file() and not f.name.startswith('.'):
                    try:
                        f.unlink()
                    except Exception:
                        pass
        invalidate_stats_cache()
