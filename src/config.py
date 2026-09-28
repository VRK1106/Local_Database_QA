import os 
from pathlib import Path 
 
BASE_DIR = Path(__file__).resolve().parent.parent 
DOCUMENTS_DIR = BASE_DIR / 'documents' 
VECTOR_DB_DIR = BASE_DIR / 'vector_db' 
 
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True) 
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True) 
 
CHROMA_DB_PATH = str(VECTOR_DB_DIR) 
CHROMA_COLLECTION = 'local_qa_collection' 
 
OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434') 
EMBEDDING_MODEL_NAME = 'BAAI/bge-small-en-v1.5' 
DEFAULT_OLLAMA_MODEL = 'qwen2.5-coder:latest' 
APP_SECRET_KEY = os.environ.get('APP_SECRET_KEY', 'local-database-qa-system-fallback-key-2026') 
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'admin-secret-12345')
AUTH_DB_PATH = BASE_DIR / 'auth.db'
