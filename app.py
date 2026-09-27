import os 
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0' 
os.environ['TOKENIZERS_PARALLELISM'] = 'false' 
import warnings 
warnings.filterwarnings('ignore') 
import sys 
import json 
import time 
from pathlib import Path 
from io import BytesIO 
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, redirect, url_for, flash 
sys.path.insert(0, str(Path(__file__).resolve().parent)) 
from src.config import DOCUMENTS_DIR, EMBEDDING_MODEL_NAME, OLLAMA_BASE_URL, DEFAULT_OLLAMA_MODEL 
from src.ingest import extract_pages, chunk_pages, file_hash 
from src.vectorstore import add_chunks, search, stats, delete_source, get_source_chunks, reset_collection, ingested_hashes 
from src.ollama_client import list_ollama_models, check_ollama_health, build_rag_prompt, generate_ollama_answer, generate_ollama_stream 
from src.structured_query import is_aggregate_query, execute_universal_structured_query 
app = Flask(__name__) 
app.secret_key = 'local-database-qa-system-secret-key-998877' 
