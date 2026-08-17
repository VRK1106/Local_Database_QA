"""Ollama Local LLM API Client: Model discovery, RAG prompt generation, streaming response handling."""

from __future__ import annotations
import json
import requests
from typing import Generator
from src.config import OLLAMA_BASE_URL


import time

_models_cache = None
_models_cache_time = 0.0

_health_cache = None
_health_cache_time = 0.0


def list_ollama_models() -> list[str]:
    """Query local Ollama server and return list of available model names (cached for 30s)."""
    global _models_cache, _models_cache_time
    now = time.time()
    if _models_cache is not None and (now - _models_cache_time) < 30.0:
        return _models_cache

    try:
        url = f"{OLLAMA_BASE_URL}/api/tags"
        resp = requests.get(url, timeout=0.5)
        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            if models:
                _models_cache = sorted(models)
                _models_cache_time = now
                return _models_cache
    except Exception:
        pass

    fallback = ["llama3:latest", "mistral:latest", "gemma:7b", "phi3:latest"]
    _models_cache = fallback
    _models_cache_time = now
    return fallback


def check_ollama_health() -> bool:
    """Return True if Ollama service is reachable on localhost (cached for 15s)."""
    global _health_cache, _health_cache_time
    now = time.time()
    if _health_cache is not None and (now - _health_cache_time) < 15.0:
        return _health_cache

    try:
        url = f"{OLLAMA_BASE_URL}/api/tags"
        resp = requests.get(url, timeout=0.5)
        _health_cache = (resp.status_code == 200)
    except Exception:
        _health_cache = False

    _health_cache_time = now
    return _health_cache


def build_rag_prompt(question: str, context_chunks: list[dict]) -> str:
    """Construct a grounded prompt combining retrieved vector context and question."""
    if not context_chunks:
        return (
            f"SYSTEM NOTICE: No relevant passages were found in the selected document(s) for the user's question.\n\n"
            f"QUESTION: {question}\n\n"
            f"INSTRUCTION: Inform the user clearly and politely that the selected document(s) do not contain any information regarding this question. Do NOT guess or invent facts.\n\n"
            f"ANSWER:"
        )

    context_str = ""
    for idx, hit in enumerate(context_chunks, start=1):
        source = hit.get("source", "Document")
        page = hit.get("page", 1)
        text = hit.get("text", "")
        context_str += f"[Source {idx}: {source}, Page {page}]\n{text}\n\n"

    prompt = (
        f"You are a strict, precise document QA assistant. Extract exact facts from the provided database text.\n\n"
        f"GRADING SCALE REFERENCE (for academic transcripts):\n"
        f"- 'O' = Outstanding (10 Points, HIGHEST grade, NOT zero or lowest)\n"
        f"- 'A+' = Excellent (9 Points)\n"
        f"- 'A' = Very Good (8 Points)\n"
        f"- 'B+' = Good (7 Points)\n"
        f"- 'B' = Average (6 Points)\n"
        f"- 'C' / 'P' = Pass (5 Points)\n"
        f"- 'F' / 'U' / 'RA' = Reappear / Fail (0 Points, LOWEST grade)\n\n"
        f"DATABASE TEXT:\n{context_str.strip()}\n\n"
        f"QUESTION: {question}\n\n"
        f"INSTRUCTION: Extract the exact answer, grade, code, or result directly from the database text above according to the grading scale reference. Be concise and precise.\n\n"
        f"ANSWER:"
    )
    return prompt


def generate_ollama_answer(
    prompt: str,
    model_name: str,
    system_instruction: str | None = None,
    temperature: float = 0.0
) -> str:
    """Send synchronous request to Ollama and return complete answer text."""
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "top_p": 0.9
        }
    }
    if system_instruction:
        payload["system"] = system_instruction

    try:
        resp = requests.post(url, json=payload, timeout=300.0)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("response", "").strip()
        else:
            return f"Ollama API Error (Status {resp.status_code}): {resp.text}"
    except Exception as e:
        return f"Could not connect to Ollama model '{model_name}': {e}. Note: First-time model loading can take up to 60s. Ensure Ollama is running locally."


def generate_ollama_stream(
    prompt: str,
    model_name: str,
    system_instruction: str | None = None,
    temperature: float = 0.0
) -> Generator[str, None, None]:
    """Stream token chunks from Ollama API as Server-Sent Events (SSE)."""
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.0,
            "top_p": 0.9
        }
    }
    if system_instruction:
        payload["system"] = system_instruction

    try:
        resp = requests.post(url, json=payload, stream=True, timeout=300.0)
        if resp.status_code != 200:
            yield f"data: {json.dumps({'error': f'Ollama API HTTP {resp.status_code}'})}\n\n"
            return

        for line in resp.iter_lines():
            if line:
                try:
                    chunk = json.loads(line.decode("utf-8"))
                    text = chunk.get("response", "")
                    done = chunk.get("done", False)
                    yield f"data: {json.dumps({'token': text, 'done': done})}\n\n"
                    if done:
                        break
                except Exception:
                    continue
    except Exception as e:
        yield f"data: {json.dumps({'error': f'Model {model_name} timed out or failed: {e}'})}\n\n"
