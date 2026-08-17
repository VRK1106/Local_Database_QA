import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import warnings
warnings.filterwarnings("ignore")

import sys
import json
import time
from pathlib import Path
from io import BytesIO

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    Response,
    stream_with_context,
    redirect,
    url_for,
    flash
)

# Ensure project directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import DOCUMENTS_DIR, EMBEDDING_MODEL_NAME, OLLAMA_BASE_URL
from src.ingest import extract_pages, chunk_pages, file_hash
from src.embeddings import embed_documents, embed_query
from src.vectorstore import (
    add_chunks,
    search,
    stats,
    delete_source,
    get_source_chunks,
    reset_collection,
    ingested_hashes
)
from src.ollama_client import (
    list_ollama_models,
    check_ollama_health,
    build_rag_prompt,
    generate_ollama_answer,
    generate_ollama_stream
)

app = Flask(__name__)
app.secret_key = "local-database-qa-system-secret-key-998877"


@app.context_processor
def inject_global_vars():
    """Inject background system state into all templates."""
    db_stats = stats()
    ollama_ok = check_ollama_health()
    available_models = list_ollama_models()
    return {
        "db_stats": db_stats,
        "ollama_ok": ollama_ok,
        "available_models": available_models,
        "embedding_model": EMBEDDING_MODEL_NAME
    }


@app.route('/', methods=['GET'])
def index():
    """Main Local QA Studio View."""
    db_stats = stats()
    models = list_ollama_models()
    query = request.args.get('q', '').strip()
    selected_model = request.args.get('model', models[0] if models else '')
    selected_sources = request.args.getlist('sources')
    mode = request.args.get('mode', 'rag')  # 'rag', 'direct', 'search_only'
    top_k = request.args.get('top_k', 4, type=int)

    results = None
    answer = None
    retrieval_time = 0.0
    generation_time = 0.0

    if query:
        t0 = time.time()
        # 1. Vector Search
        query_vec = embed_query(query)
        hits = search(
            query_embedding=query_vec,
            top_k=top_k,
            source_filters=selected_sources if selected_sources else None
        )
        t1 = time.time()
        retrieval_time = round(t1 - t0, 3)
        results = hits

        if mode == 'rag':
            prompt = build_rag_prompt(query, hits)
            t2 = time.time()
            answer = generate_ollama_answer(prompt=prompt, model_name=selected_model)
            generation_time = round(time.time() - t2, 3)
        elif mode == 'direct':
            t2 = time.time()
            answer = generate_ollama_answer(prompt=query, model_name=selected_model)
            generation_time = round(time.time() - t2, 3)

    return render_template(
        'index.html',
        query=query,
        selected_model=selected_model,
        selected_sources=selected_sources,
        mode=mode,
        top_k=top_k,
        results=results,
        answer=answer,
        retrieval_time=retrieval_time,
        generation_time=generation_time,
        active_page='qa'
    )


@app.route('/documents', methods=['GET'])
def documents_page():
    """Document Ingestion & Vector DB Management View."""
    db_stats = stats()
    selected_doc = request.args.get('inspect')
    inspect_chunks = []
    if selected_doc:
        inspect_chunks = get_source_chunks(selected_doc)

    return render_template(
        'documents.html',
        db_stats=db_stats,
        selected_doc=selected_doc,
        inspect_chunks=inspect_chunks,
        active_page='documents'
    )


@app.route('/system_info', methods=['GET'])
def system_info_page():
    """System & Model Diagnostics View."""
    ollama_ok = check_ollama_health()
    models = list_ollama_models()
    db_stats = stats()

    return render_template(
        'system_info.html',
        ollama_ok=ollama_ok,
        models=models,
        db_stats=db_stats,
        ollama_url=OLLAMA_BASE_URL,
        embedding_model=EMBEDDING_MODEL_NAME,
        active_page='system'
    )


@app.route('/api/upload', methods=['POST'])
def api_upload():
    """Handle document uploads, parsing, chunking, and ChromaDB vector indexing."""
    uploaded_files = request.files.getlist('files')
    if not uploaded_files or not uploaded_files[0].filename:
        flash("No files selected for upload.", "warning")
        return redirect(url_for('documents_page'))

    known = ingested_hashes()
    indexed_count = 0
    skipped_count = 0

    for f in uploaded_files:
        if not f.filename:
            continue
        try:
            content = f.read()
            if not content:
                continue
            digest = file_hash(content)
            if digest in known:
                skipped_count += 1
                continue

            pages = extract_pages(BytesIO(content), f.filename)
            if not pages:
                continue

            chunks = chunk_pages(pages, f.filename)
            embeddings = embed_documents([c["text"] for c in chunks])
            add_chunks(chunks, embeddings, digest)

            # Save file to disk
            save_path = Path(DOCUMENTS_DIR) / f.filename
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(content)

            known.add(digest)
            indexed_count += 1
        except Exception as e:
            flash(f"Error processing {f.filename}: {e}", "danger")

    if indexed_count > 0:
        flash(f"Successfully indexed {indexed_count} new document(s) into ChromaDB!", "success")
    elif skipped_count > 0:
        flash(f"Skipped {skipped_count} duplicate file(s) already present in database.", "info")

    return redirect(url_for('documents_page'))


@app.route('/api/delete_doc', methods=['POST'])
def api_delete_doc():
    """Delete document source and vector embeddings."""
    source_name = request.form.get('source_name')
    if source_name:
        delete_source(source_name)
        flash(f"Document '{source_name}' and its vector embeddings were removed.", "info")
    return redirect(url_for('documents_page'))


@app.route('/api/reset_db', methods=['POST'])
def api_reset_db():
    """Completely wipe the ChromaDB collection and document storage."""
    reset_collection()
    flash("Local database wiped successfully.", "warning")
    return redirect(url_for('documents_page'))


@app.route('/api/stream_query', methods=['POST'])
def api_stream_query():
    """Stream response tokens from Ollama using SSE."""
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    model = data.get('model') or list_ollama_models()[0]
    sources = data.get('sources', [])
    mode = data.get('mode', 'rag')
    top_k = data.get('top_k', 4)

    if not query:
        return jsonify({"error": "Empty query"}), 400

    def event_stream():
        # 1. Retrieve vector context if in RAG mode
        context_chunks = []
        if mode == 'rag':
            query_vec = embed_query(query)
            context_chunks = search(query_vec, top_k=top_k, source_filters=sources if sources else None)

            # Send vector context metadata event first
            citations = [{
                "source": c["source"],
                "page": c["page"],
                "score": c["score"],
                "text": c["text"]
            } for c in context_chunks]

            yield f"data: {json.dumps({'type': 'context', 'citations': citations})}\n\n"
            prompt = build_rag_prompt(query, context_chunks)
        else:
            prompt = query
            yield f"data: {json.dumps({'type': 'context', 'citations': []})}\n\n"

        # 2. Stream tokens from Ollama
        for stream_chunk in generate_ollama_stream(prompt=prompt, model_name=model):
            yield stream_chunk

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print("\n" + "=" * 65)
    print("  LOCAL DATABASE QUESTION-ANSWERING SYSTEM IS LIVE!")
    print(f"  ACCESS AT: http://127.0.0.1:{port}")
    print("=" * 65 + "\n")
    app.run(host="0.0.0.0", port=port, debug=True)
