import os 
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, redirect, url_for, flash 
import sys, json, time 
from pathlib import Path 
from io import BytesIO 
from src.config import DOCUMENTS_DIR, EMBEDDING_MODEL_NAME, OLLAMA_BASE_URL, DEFAULT_OLLAMA_MODEL 
from src.ingest import extract_pages, chunk_pages, file_hash 
from src.embeddings import embed_documents, embed_query 
from src.vectorstore import add_chunks, search, stats, delete_source, get_source_chunks, reset_collection, ingested_hashes 
from src.ollama_client import list_ollama_models, check_ollama_health, build_rag_prompt, generate_ollama_answer, generate_ollama_stream 
from src.structured_query import is_aggregate_query, execute_universal_structured_query 
app = Flask(__name__) 
app.secret_key = 'local-database-qa-system-secret-key-998877' 
@app.route('/') 
def index(): return render_template('index.html', active_page='qa') 
@app.route('/api/system_state') 
def api_system_state(): return jsonify({'db_stats': stats(), 'ollama_ok': check_ollama_health(), 'available_models': list_ollama_models(), 'embedding_model': EMBEDDING_MODEL_NAME}) 
@app.route('/api/documents') 
def api_documents(): db_stats = stats(); selected_doc = request.args.get('inspect'); inspect_chunks = get_source_chunks(selected_doc) if selected_doc else []; return jsonify({'db_stats': db_stats, 'selected_doc': selected_doc, 'inspect_chunks': inspect_chunks}) 
@app.route('/api/system_info') 
def api_system_info(): return jsonify({'ollama_ok': check_ollama_health(), 'models': list_ollama_models(), 'db_stats': stats(), 'ollama_url': OLLAMA_BASE_URL, 'embedding_model': EMBEDDING_MODEL_NAME}) 
@app.route('/api/upload', methods=['POST']) 
def api_upload(): pass 
@app.route('/api/delete_doc', methods=['POST']) 
def api_delete_doc(): pass 
@app.route('/api/reset_db', methods=['POST']) 
def api_reset_db(): pass 
@app.route('/api/stream_query', methods=['POST']) 
def api_stream_query(): pass 
if __name__ == '__main__': app.run(host='0.0.0.0', port=5000, debug=True) 
