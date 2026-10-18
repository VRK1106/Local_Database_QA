import os 
from pathlib import Path 

BASE_DIR = Path(__file__).resolve().parent.parent 
DOCUMENTS_DIR = BASE_DIR / 'documents' 
VECTOR_DB_DIR = BASE_DIR / 'vector_db' 

DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True) 
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True) 

# ChromaDB Server / Persistence Configuration
# If CHROMA_SERVER_HOST is set, the application connects to a dedicated ChromaDB server over HTTP/HTTPS
CHROMA_SERVER_HOST = os.environ.get('CHROMA_SERVER_HOST', '').strip() or None
CHROMA_SERVER_HTTP_PORT = int(os.environ.get('CHROMA_SERVER_HTTP_PORT', 8000))
CHROMA_SERVER_SSL = os.environ.get('CHROMA_SERVER_SSL', 'false').lower() == 'true'
CHROMA_SERVER_AUTH_CREDENTIALS = os.environ.get('CHROMA_SERVER_AUTH_CREDENTIALS', None)

CHROMA_DB_PATH = str(VECTOR_DB_DIR) 
CHROMA_COLLECTION = os.environ.get('CHROMA_COLLECTION', 'local_qa_collection')

# Relational Database Configuration (PostgreSQL with SQLite fallback)
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
USE_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith(('postgresql://', 'postgres://')))
AUTH_DB_PATH = BASE_DIR / 'auth.db'

# LLM & Embedding Settings
OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434') 
EMBEDDING_MODEL_NAME = os.environ.get('EMBEDDING_MODEL_NAME', 'BAAI/bge-small-en-v1.5')
DEFAULT_OLLAMA_MODEL = os.environ.get('DEFAULT_OLLAMA_MODEL', 'qwen2.5-coder:latest')
APP_SECRET_KEY = os.environ.get('APP_SECRET_KEY', 'local-database-qa-system-fallback-key-2026') 
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'admin-secret-12345')
