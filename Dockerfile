# Multi-stage / Production Dockerfile for AMYPO Local Database QA
FROM python:3.10-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
# Configure glibc memory arena limits and math library threads to prevent memory bloat
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TOKENIZERS_PARALLELISM=false \
    TF_CPP_MIN_LOG_LEVEL=3 \
    MALLOC_ARENA_MAX=2 \
    PYTHONMALLOC=malloc \
    OMP_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    NUMEXPR_NUM_THREADS=2

WORKDIR /app

# Install system dependencies for PyPDF, Pandas, Pillow, and PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
# The backend has no GPU reservation (only Ollama does), so install the CPU-only torch wheel
# first; it avoids pulling multi-GB CUDA libraries that would never be used in this container.
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

# Bake the embedding model, NLI trust-layer model and sentence tokenizer into the image so the
# backend runs fully offline and a recreated container does not re-download them at request time.
ARG EMBEDDING_MODEL_NAME=BAAI/bge-small-en-v1.5
ENV NLTK_DATA=/usr/local/share/nltk_data
RUN python -c "import nltk; nltk.download('punkt_tab', download_dir='/usr/local/share/nltk_data', quiet=True, raise_on_error=True)" \
 && python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('${EMBEDDING_MODEL_NAME}'); CrossEncoder('cross-encoder/nli-deberta-v3-small')"

# Models are baked in above: never contact the Hugging Face Hub at runtime
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# Copy application source
COPY . .

# Keep a pristine copy of the bundled sample documents: /app/documents is shadowed by the
# documents_data named volume, so startup seeds any missing files from here (once per file).
RUN cp -r /app/documents /app/seed_documents

# Expose web application port
EXPOSE 5000

# Container healthcheck using the non-blocking /health endpoint
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run with production Waitress WSGI runner
CMD ["python", "run_production.py"]
