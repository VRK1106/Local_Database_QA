import os
try:
    import pyautogui
except ImportError:
    pyautogui = None

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
from functools import wraps

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
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user
)
from werkzeug.security import check_password_hash

# Ensure project directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import DOCUMENTS_DIR, EMBEDDING_MODEL_NAME, OLLAMA_BASE_URL, DEFAULT_OLLAMA_MODEL, APP_SECRET_KEY
from src.ingest import extract_pages, chunk_pages, file_hash
from src.embeddings import embed_documents, embed_query
from src.vectorstore import (
    add_chunks,
    search,
    stats,
    delete_source,
    update_source_visibility,
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
from src.structured_query import (
    is_aggregate_query,
    execute_universal_structured_query,
    execute_student_scoped_query
)
from src.auth import (
    init_auth_db,
    get_user_by_id,
    get_user_by_username,
    verify_user_password,
    create_user,
    update_password,
    log_audit_event,
    get_audit_logs,
    import_students_from_csv,
    get_db_connection
)

app = Flask(__name__)
app.secret_key = APP_SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Initialize SQLite tables & default admin user
init_auth_db()

# Setup Flask-Login session manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please sign in to access the Local Database QA System."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)


def role_required(*roles):
    """Decorator to enforce role-based access control with audit logging."""
    def decorator(f):
        @wraps(f)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({"status": "error", "message": "Authentication required."}), 401
                flash("Please sign in to access this page.", "warning")
                return redirect(url_for('login', next=request.url))

            if current_user.role not in roles:
                log_audit_event(
                    user_id=current_user.id,
                    username=current_user.username,
                    role=current_user.role,
                    action="unauthorized_access_attempt",
                    endpoint=request.path,
                    status="forbidden",
                    ip_address=request.remote_addr
                )
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({"status": "error", "message": "Access forbidden: insufficient role permissions."}), 403
                flash("Access denied: You do not have permissions for this section.", "danger")
                return redirect(url_for('index'))

            return f(*args, **kwargs)
        return decorated_view
    return decorator


@app.before_request
def enforce_security_policies():
    """Ensure users with default/temporary passwords change them before accessing features."""
    if current_user.is_authenticated and getattr(current_user, 'must_change_password', False):
        allowed_endpoints = ['change_password', 'logout', 'static']
        if request.endpoint and request.endpoint not in allowed_endpoints:
            flash("Security Policy: You must set a new personal password before accessing the system.", "warning")
            return redirect(url_for('change_password'))


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


# =========================================================================
# Authentication & User Management Routes
# =========================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Sign-in portal for Placement Officers and Students."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = verify_user_password(username, password)
        if user:
            login_user(user)
            log_audit_event(
                user_id=user.id,
                username=user.username,
                role=user.role,
                action="login",
                endpoint="/login",
                status="success",
                ip_address=request.remote_addr
            )
            flash(f"Signed in successfully as {user.username} ({user.role.capitalize()}).", "success")
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            log_audit_event(
                user_id=None,
                username=username,
                role=None,
                action="login_failed",
                endpoint="/login",
                status="unauthorized",
                ip_address=request.remote_addr
            )
            flash("Invalid username or password.", "danger")

    return render_template('login.html', active_page='login')


@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    """Sign out the current user session and record audit trail."""
    log_audit_event(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="logout",
        endpoint="/logout",
        status="success",
        ip_address=request.remote_addr
    )
    logout_user()
    flash("You have been signed out safely.", "info")
    return redirect(url_for('login'))


@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Allow students and officers to update their own password."""
    if request.method == 'POST':
        curr_pwd = request.form.get('current_password', '')
        new_pwd = request.form.get('new_password', '')
        confirm_pwd = request.form.get('confirm_password', '')

        if not verify_user_password(current_user.username, curr_pwd):
            flash("Incorrect current password.", "danger")
            return render_template('change_password.html', active_page='password')

        if new_pwd != confirm_pwd:
            flash("New passwords do not match.", "warning")
            return render_template('change_password.html', active_page='password')

        if len(new_pwd) < 6:
            flash("New password must be at least 6 characters.", "warning")
            return render_template('change_password.html', active_page='password')

        update_password(current_user.id, new_pwd)
        current_user.must_change_password = False
        log_audit_event(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="password_change",
            endpoint="/change_password",
            status="success",
            ip_address=request.remote_addr
        )
        flash("Password updated successfully!", "success")
        return redirect(url_for('index'))

    return render_template('change_password.html', active_page='password')


@app.route('/admin/users', methods=['GET'])
@role_required('placement')
def admin_users_page():
    """User account administration and student batch import view."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, student_id, must_change_password, active, created_at FROM users ORDER BY id DESC")
    users = [dict(r) for r in cur.fetchall()]
    conn.close()
    return render_template('admin_users.html', users=users, active_page='users')


@app.route('/admin/create_user', methods=['POST'])
@role_required('placement')
def admin_create_user():
    """Manually register an individual user account."""
    username = request.form.get('username', '').strip()
    role = request.form.get('role', 'student')
    student_id = request.form.get('student_id', '').strip() or None
    password = request.form.get('password', '')

    if not username or not password:
        flash("Username and password are required.", "danger")
        return redirect(url_for('admin_users_page'))

    try:
        create_user(username, password, role, student_id=student_id, must_change_password=False)
        log_audit_event(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="user_created",
            endpoint="/admin/create_user",
            query_text=f"User: {username} ({role})",
            status="success",
            ip_address=request.remote_addr
        )
        flash(f"Account '{username}' ({role.capitalize()}) created successfully!", "success")
    except Exception as e:
        flash(f"Failed to create user: {e}", "danger")

    return redirect(url_for('admin_users_page'))


@app.route('/admin/import_students', methods=['POST'])
@role_required('placement')
def admin_import_students():
    """Batch-import student accounts from uploaded CSV file."""
    csv_file = request.files.get('csv_file')
    if not csv_file or not csv_file.filename:
        flash("Please upload a valid CSV file.", "warning")
        return redirect(url_for('admin_users_page'))

    try:
        content = csv_file.read().decode('utf-8', errors='ignore')
        created, skipped, creds = import_students_from_csv(content)
        log_audit_event(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="students_batch_import",
            endpoint="/admin/import_students",
            query_text=f"Created: {created}, Skipped: {skipped}",
            status="success",
            ip_address=request.remote_addr
        )
        flash(f"Import completed: {created} new student account(s) generated, {skipped} duplicate(s) skipped.", "success")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username, role, student_id, must_change_password, active, created_at FROM users ORDER BY id DESC")
        users = [dict(r) for r in cur.fetchall()]
        conn.close()
        return render_template('admin_users.html', users=users, credentials_report=creds, active_page='users')
    except Exception as e:
        flash(f"Student CSV import error: {e}", "danger")
        return redirect(url_for('admin_users_page'))


@app.route('/audit_logs', methods=['GET'])
@role_required('placement')
def audit_logs_page():
    """Security audit log viewer for compliance monitoring."""
    logs = get_audit_logs(200)
    return render_template('audit_logs.html', logs=logs, active_page='audit')


# =========================================================================
# Core QA Studio & Document Routes
# =========================================================================

@app.route('/', methods=['GET'])
@login_required
def index():
    """Main Local QA Studio View with role-based scoping."""
    db_stats = stats()
    models = list_ollama_models()
    query = request.args.get('q', '').strip()
    selected_model = request.args.get('model', DEFAULT_OLLAMA_MODEL if DEFAULT_OLLAMA_MODEL in models else (models[0] if models else DEFAULT_OLLAMA_MODEL))
    selected_sources = request.args.getlist('sources')
    mode = request.args.get('mode', 'rag')  # 'rag', 'direct', 'search_only'
    top_k = request.args.get('top_k', 4, type=int)

    results = None
    answer = None
    retrieval_time = 0.0
    generation_time = 0.0

    if query:
        t0 = time.time()
        
        # 1. Student Scoped Path
        if current_user.role == 'student':
            if is_aggregate_query(query):
                answer = (
                    "**Access Restricted:** Institutional aggregates, batch statistics, and peer rankings "
                    "are confidential and reserved for Placement Officers. "
                    "You may ask questions about placement eligibility criteria, company visit schedules, "
                    "or your personal placement profile."
                )
                results = []
            else:
                stu_id = current_user.student_id or current_user.username
                final_prompt, sql_q, sql_res, citations = execute_student_scoped_query(
                    query=query,
                    student_id=stu_id,
                    documents_dir=DOCUMENTS_DIR,
                    model_name=selected_model
                )
                if final_prompt:
                    t2 = time.time()
                    answer = generate_ollama_answer(prompt=final_prompt, model_name=selected_model)
                    results = citations
                    generation_time = round(time.time() - t2, 3)
                else:
                    # Student Semantic Search strictly on public documents
                    query_vec = embed_query(query)
                    hits = search(
                        query_embedding=query_vec,
                        top_k=top_k,
                        source_filters=selected_sources if selected_sources else None,
                        visibility="public"
                    )
                    retrieval_time = round(time.time() - t0, 3)
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

        # 2. Placement Officer Path (Unrestricted)
        else:
            if mode == 'rag' and is_aggregate_query(query):
                final_prompt, sql_q, sql_res, citations = execute_universal_structured_query(
                    query=query,
                    documents_dir=DOCUMENTS_DIR,
                    selected_sources=selected_sources if selected_sources else None,
                    model_name=selected_model
                )
                if final_prompt:
                    t2 = time.time()
                    answer = generate_ollama_answer(prompt=final_prompt, model_name=selected_model)
                    results = citations
                    generation_time = round(time.time() - t2, 3)

            if answer is None:
                query_vec = embed_query(query)
                hits = search(
                    query_embedding=query_vec,
                    top_k=top_k,
                    source_filters=selected_sources if selected_sources else None
                )
                retrieval_time = round(time.time() - t0, 3)
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
@role_required('placement')
def documents_page():
    """Document Ingestion & Vector DB Management View (Placement Officers only)."""
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
@role_required('placement')
def system_info_page():
    """System & Model Diagnostics View (Placement Officers only)."""
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
@role_required('placement')
def api_upload():
    """Handle document uploads, parsing, chunking, and ChromaDB vector indexing with streaming progress and visibility tagging."""
    uploaded_files = request.files.getlist('files')
    visibility = request.form.get('visibility', 'internal').strip().lower()
    clean_visibility = "public" if visibility == "public" else "internal"
    
    is_ajax = 'application/json' in request.headers.get('Accept', '') or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if not uploaded_files or not uploaded_files[0].filename:
        if is_ajax:
            return jsonify({"status": "error", "message": "No files selected."}), 400
        flash("No files selected for upload.", "warning")
        return redirect(url_for('documents_page'))

    files_data = []
    for f in uploaded_files:
        if f.filename:
            files_data.append((f.filename, f.read()))

    def generate():
        known = ingested_hashes()
        indexed_count = 0
        skipped_count = 0

        for filename, content in files_data:
            try:
                if is_ajax:
                    yield json.dumps({"status": "progress", "message": f"Processing file: {filename} ({clean_visibility})..."}) + "\n"
                
                if not content:
                    continue
                digest = file_hash(content)
                if digest in known:
                    skipped_count += 1
                    if is_ajax:
                        yield json.dumps({"status": "progress", "message": f"Skipping {filename} (already indexed)."}) + "\n"
                    continue

                if is_ajax:
                    yield json.dumps({"status": "progress", "message": f"Extracting pages from {filename}..."}) + "\n"
                pages = extract_pages(BytesIO(content), filename)
                if not pages:
                    if is_ajax:
                        yield json.dumps({"status": "error", "message": f"Extraction failed for {filename}. The file might be empty or unsupported."}) + "\n"
                    continue

                if is_ajax:
                    yield json.dumps({"status": "progress", "message": f"Chunking {filename} with '{clean_visibility}' visibility..."}) + "\n"
                chunks = chunk_pages(pages, filename, visibility=clean_visibility)
                
                if is_ajax:
                    yield json.dumps({"status": "progress", "message": f"Embedding {len(chunks)} chunks for {filename}..."}) + "\n"
                embeddings = embed_documents([c["text"] for c in chunks])
                
                if is_ajax:
                    yield json.dumps({"status": "progress", "message": f"Saving {filename} to database..."}) + "\n"
                add_chunks(chunks, embeddings, digest)

                save_path = Path(DOCUMENTS_DIR) / filename
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(content)

                known.add(digest)
                indexed_count += 1
                
                log_audit_event(
                    user_id=current_user.id,
                    username=current_user.username,
                    role=current_user.role,
                    action="document_upload",
                    endpoint="/api/upload",
                    query_text=f"File: {filename}, Scope: {clean_visibility}, Chunks: {len(chunks)}",
                    status="success",
                    ip_address=request.remote_addr
                )

                if is_ajax:
                    yield json.dumps({"status": "progress", "message": f"Finished {filename}!"}) + "\n"
            except Exception as e:
                if is_ajax:
                    yield json.dumps({"status": "error", "message": f"Error processing {filename}: {str(e)}"}) + "\n"
                else:
                    flash(f"Error processing {filename}: {e}", "danger")

        if is_ajax:
            yield json.dumps({"status": "done", "indexed": indexed_count, "skipped": skipped_count}) + "\n"

    if is_ajax:
        return Response(stream_with_context(generate()), mimetype='application/x-ndjson')
    
    for _ in generate():
        pass
        
    if indexed_count > 0:
        flash(f"Successfully indexed {indexed_count} new document(s) ({clean_visibility}) into ChromaDB!", "success")
    elif skipped_count > 0:
        flash(f"Skipped {skipped_count} duplicate file(s) already present in database.", "info")

    return redirect(url_for('documents_page'))


@app.route('/api/update_doc_visibility', methods=['POST'])
@role_required('placement')
def api_update_doc_visibility():
    """Toggle document visibility between 'public' and 'internal'."""
    source_name = request.form.get('source_name', '').strip()
    new_visibility = request.form.get('new_visibility', 'internal').strip().lower()
    clean_visibility = "public" if new_visibility == "public" else "internal"
    
    if source_name:
        update_source_visibility(source_name, clean_visibility)
        log_audit_event(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="update_visibility",
            endpoint="/api/update_doc_visibility",
            query_text=f"{source_name} -> {clean_visibility}",
            status="success",
            ip_address=request.remote_addr
        )
        flash(f"Document '{source_name}' visibility set to {clean_visibility.upper()}.", "info")
    return redirect(url_for('documents_page'))


@app.route('/api/delete_doc', methods=['POST'])
@role_required('placement')
def api_delete_doc():
    """Delete document source and vector embeddings."""
    source_name = request.form.get('source_name')
    if source_name:
        delete_source(source_name)
        log_audit_event(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="document_delete",
            endpoint="/api/delete_doc",
            query_text=f"Deleted source: {source_name}",
            status="success",
            ip_address=request.remote_addr
        )
        flash(f"Document '{source_name}' and its vector embeddings were removed.", "info")
    return redirect(url_for('documents_page'))


@app.route('/api/reset_db', methods=['POST'])
@role_required('placement')
def api_reset_db():
    """Completely wipe the ChromaDB collection with mandatory password verification."""
    admin_password = request.form.get('admin_password', '')
    user_row = get_user_by_username(current_user.username)
    
    if not user_row or not check_password_hash(user_row["password_hash"], admin_password):
        log_audit_event(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="reset_db_attempt",
            endpoint="/api/reset_db",
            status="forbidden",
            ip_address=request.remote_addr
        )
        flash("Password verification failed. Database reset rejected.", "danger")
        return redirect(url_for('documents_page'))

    reset_collection()
    import shutil
    if os.path.exists(DOCUMENTS_DIR):
        try:
            shutil.rmtree(DOCUMENTS_DIR)
        except Exception as e:
            print(f"Error removing documents directory: {e}")

    log_audit_event(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="reset_db_confirmed",
        endpoint="/api/reset_db",
        status="success",
        ip_address=request.remote_addr
    )
    flash("Local database wiped successfully.", "warning")
    return redirect(url_for('documents_page'))


@app.route('/api/stream_query', methods=['POST'])
@login_required
def api_stream_query():
    """Stream response tokens from Ollama using SSE with strict student/placement data isolation."""
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    model = data.get('model') or list_ollama_models()[0]
    sources = data.get('sources', [])
    mode = data.get('mode', 'rag')
    top_k = data.get('top_k', 4)

    if not query:
        return jsonify({"error": "Empty query"}), 400

    # Record query into immutable audit trail
    log_audit_event(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="stream_query",
        endpoint="/api/stream_query",
        query_text=query[:200],
        status="success",
        ip_address=request.remote_addr
    )

    def event_stream():
        # -------------------------------------------------------------
        # Path A: Authenticated Student Role (Zero-Trust Scoped Guard)
        # -------------------------------------------------------------
        if current_user.role == 'student':
            # 1. Prevent students from executing arbitrary or cross-student aggregates
            if is_aggregate_query(query):
                notice_msg = (
                    "**Access Restricted:** Institutional aggregates, batch statistics, and peer rankings "
                    "are confidential and reserved for Placement Officers. "
                    "You may ask questions about placement eligibility criteria, company visit schedules, "
                    "or your personal placement profile."
                )
                yield f"data: {json.dumps({'type': 'context', 'citations': []})}\n\n"
                yield f"data: {json.dumps({'token': notice_msg})}\n\n"
                return

            # 2. Check student personal record
            stu_id = current_user.student_id or current_user.username
            final_prompt, sql_q, sql_res, citations = execute_student_scoped_query(
                query=query,
                student_id=stu_id,
                documents_dir=DOCUMENTS_DIR,
                model_name=model
            )
            if final_prompt:
                yield f"data: {json.dumps({'type': 'context', 'citations': citations})}\n\n"
                for stream_chunk in generate_ollama_stream(prompt=final_prompt, model_name=model):
                    yield stream_chunk
                return

            # Semantic Vector Search: Strictly visibility='public'
            context_chunks = []
            if mode == 'rag':
                query_vec = embed_query(query)
                context_chunks = search(
                    query_vec,
                    top_k=top_k,
                    source_filters=sources if sources else None,
                    visibility="public"
                )

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

            for stream_chunk in generate_ollama_stream(prompt=prompt, model_name=model):
                yield stream_chunk
            return

        # -------------------------------------------------------------
        # Path B: Placement Officer Role (Full Administrative Scope)
        # -------------------------------------------------------------
        if mode == 'rag' and is_aggregate_query(query):
            final_prompt, sql_q, sql_res, citations = execute_universal_structured_query(
                query=query,
                documents_dir=DOCUMENTS_DIR,
                selected_sources=sources if sources else None,
                model_name=model
            )
            if final_prompt:
                yield f"data: {json.dumps({'type': 'context', 'citations': citations})}\n\n"
                for stream_chunk in generate_ollama_stream(prompt=final_prompt, model_name=model):
                    yield stream_chunk
                return

        context_chunks = []
        if mode == 'rag':
            query_vec = embed_query(query)
            context_chunks = search(query_vec, top_k=top_k, source_filters=sources if sources else None)

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

        for stream_chunk in generate_ollama_stream(prompt=prompt, model_name=model):
            yield stream_chunk

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")


@app.route('/api/verify_trust', methods=['POST'])
@login_required
def api_verify_trust():
    """Asynchronous background endpoint to verify hallucination claims."""
    data = request.get_json() or {}
    draft_answer = data.get('answer', '').strip()
    context_texts = data.get('context_texts', [])
    
    if not draft_answer or not context_texts:
        return jsonify({"score": 100, "claims": []})
        
    from src.trust_layer import verify_claims
    verification = verify_claims(draft_answer, context_texts)
    return jsonify(verification)


@app.route('/api/trigger_voice_typing', methods=['GET', 'POST'])
@login_required
def trigger_voice_typing():
    """Trigger Windows Voice Typing (Win+H) using Win32 ctypes keybd_event or pyautogui fallback."""
    import platform, time
    success = False
    err_msg = ""
    
    if platform.system() == "Windows":
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(0x48, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(0x48, 0, 2, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(0x5B, 0, 2, 0)
            success = True
        except Exception as e:
            err_msg = str(e)

    if not success and pyautogui is not None:
        try:
            pyautogui.hotkey('win', 'h')
            success = True
        except Exception as e:
            err_msg = str(e)

    if success:
        return jsonify({"status": "success", "message": "Triggered Win+H"})
    return jsonify({"status": "error", "message": err_msg or "Failed to trigger Win+H"}), 500


@app.route('/api/stop_voice_typing', methods=['GET', 'POST'])
@login_required
def stop_voice_typing():
    """Dismiss Windows Dictation popup (Esc) using Win32 ctypes keybd_event or pyautogui fallback."""
    import platform, time
    success = False
    err_msg = ""

    if platform.system() == "Windows":
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(0x1B, 0, 2, 0)
            success = True
        except Exception as e:
            err_msg = str(e)

    if not success and pyautogui is not None:
        try:
            pyautogui.press('esc')
            success = True
        except Exception as e:
            err_msg = str(e)

    if success:
        return jsonify({"status": "success", "message": "Triggered Esc"})
    return jsonify({"status": "error", "message": err_msg or "Failed to trigger Esc"}), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print("\n" + "=" * 65)
    print("  LOCAL DATABASE QUESTION-ANSWERING SYSTEM (RBAC SECURED)")
    print(f"  ACCESS AT: http://127.0.0.1:{port}")
    print("=" * 65 + "\n")
    app.run(host="0.0.0.0", port=port, debug=True)
