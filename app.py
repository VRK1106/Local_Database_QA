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
    flash,
    session,
    abort,
    send_from_directory
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

from src.config import (
    DOCUMENTS_DIR,
    EMBEDDING_MODEL_NAME,
    OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    APP_SECRET_KEY,
    CHROMA_DB_PATH,
    AUTH_DB_PATH
)
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
    execute_student_scoped_query,
    get_student_record
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
    get_db_connection,
    has_permission,
    PERMISSIONS,
    set_user_role,
    set_user_active_status,
    seed_student_records_from_documents,
    get_all_student_records,
    upsert_student_record,
    delete_student_record
)
from src.scopes import (
    QueryScope,
    StudentScope,
    PlacementScope,
    DeveloperScope,
    scope_for
)
from src.cli import create_developer_cmd
from src.tickets import (
    create_ticket,
    get_ticket_by_id,
    can_user_access_ticket,
    get_tickets_for_user,
    add_ticket_message,
    get_ticket_messages,
    update_ticket_status,
    get_ticket_stats,
    CATEGORIES_STUDENT,
    CATEGORIES_PLACEMENT,
    CATEGORIES_DEVELOPER,
)

app = Flask(__name__)
app.secret_key = APP_SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Register CLI commands
app.cli.add_command(create_developer_cmd)

# Initialize SQLite tables & default seed
init_auth_db()
seed_student_records_from_documents(DOCUMENTS_DIR)

# Setup Flask-Login session manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please sign in to access the Local Database QA System."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)


def permission_required(perm: str):
    """Decorator to enforce granular permission checks with audit logging and impersonation support."""
    def decorator(f):
        @wraps(f)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({"status": "error", "message": "Authentication required."}), 401
                flash("Please sign in to access this page.", "warning")
                return redirect(url_for('login', next=request.url))

            if not has_permission(current_user, perm):
                eff_role = session.get("view_as", {}).get("role") if session.get("view_as") else current_user.role
                eff_stu_id = session.get("view_as", {}).get("student_id") if session.get("view_as") else getattr(current_user, "student_id", None)
                log_audit_event(
                    actor_user_id=current_user.id,
                    actor_username=current_user.username,
                    effective_role=eff_role,
                    effective_student_id=eff_stu_id,
                    action="permission_denied",
                    endpoint=request.path,
                    detail=f"Required permission: '{perm}'",
                    status="forbidden",
                    ip_address=request.remote_addr
                )
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({"status": "error", "message": f"Access forbidden: requires permission '{perm}'."}), 403
                flash(f"Access denied: you do not hold permission '{perm}'.", "danger")
                return redirect(url_for('index'))

            return f(*args, **kwargs)
        return decorated_view
    return decorator


def role_required(*roles):
    """Backwards-compatibility role decorator mapping into role/permission checks."""
    def decorator(f):
        @wraps(f)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({"status": "error", "message": "Authentication required."}), 401
                flash("Please sign in to access this page.", "warning")
                return redirect(url_for('login', next=request.url))

            eff_role = session.get("view_as", {}).get("role") if session.get("view_as") else current_user.role
            allowed = set(roles)
            if "placement" in allowed:
                allowed.add("developer")

            if eff_role not in allowed:
                log_audit_event(
                    actor_user_id=current_user.id,
                    actor_username=current_user.username,
                    effective_role=eff_role,
                    action="role_denied",
                    endpoint=request.path,
                    detail=f"Required roles: {roles}",
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
    open_tickets_count = 0
    if current_user.is_authenticated:
        try:
            stats_dict = get_ticket_stats(current_user)
            open_tickets_count = stats_dict.get('open', 0)
        except Exception:
            open_tickets_count = 0
    return {
        "db_stats": db_stats,
        "ollama_ok": ollama_ok,
        "available_models": available_models,
        "embedding_model": EMBEDDING_MODEL_NAME,
        "open_tickets_count": open_tickets_count
    }


# =========================================================================
# Authentication & User Management Routes
# =========================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Sign-in portal for Placement Officers, Students, and Developers."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = verify_user_password(username, password)
        if user:
            login_user(user)
            log_audit_event(
                actor_user_id=user.id,
                actor_username=user.username,
                effective_role=user.role,
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
                actor_user_id=None,
                actor_username=username,
                effective_role=None,
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
    """Sign out the current user session, purge impersonation state, and record audit trail."""
    log_audit_event(
        actor_user_id=current_user.id,
        actor_username=current_user.username,
        effective_role=current_user.role,
        action="logout",
        endpoint="/logout",
        status="success",
        ip_address=request.remote_addr
    )
    session.clear()
    logout_user()
    flash("You have been signed out safely.", "info")
    return redirect(url_for('login'))


@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Allow students, officers, and developers to update their own password."""
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
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            effective_role=current_user.role,
            action="password_change",
            endpoint="/change_password",
            status="success",
            ip_address=request.remote_addr
        )
        flash("Password updated successfully!", "success")
        return redirect(url_for('index'))

    return render_template('change_password.html', active_page='password')


@app.route('/admin/users', methods=['GET'])
@permission_required('users.import_students')
def admin_users_page():
    """User account administration and student batch import view."""
    conn = get_db_connection()
    cur = conn.cursor()
    if has_permission(current_user, 'users.set_role'):
        cur.execute("SELECT id, username, role, student_id, must_change_password, active, created_at FROM users ORDER BY id DESC")
    else:
        # Placement officer view: isolate strictly to students and own coordinator account
        cur.execute("""
            SELECT id, username, role, student_id, must_change_password, active, created_at 
            FROM users 
            WHERE role = 'student' OR id = ?
            ORDER BY id DESC
        """, (current_user.id,))
    users = [dict(r) for r in cur.fetchall()]
    conn.close()
    return render_template('admin_users.html', users=users, active_page='users')


@app.route('/admin/create_user', methods=['POST'])
@login_required
def admin_create_user():
    """Register individual student or placement account (strictly guarded against unauthorized privilege escalation)."""
    username = request.form.get('username', '').strip()
    role = request.form.get('role', 'student').strip().lower()
    student_id = request.form.get('student_id', '').strip() or None
    password = request.form.get('password', '')

    if not username or not password:
        flash("Username and password are required.", "danger")
        return redirect(url_for('admin_users_page'))

    # Security Guard: Only developer can create developer or placement roles
    if role == "developer":
        flash("Security Directive: Developer accounts cannot be created from web UI. Use CLI create-developer.", "danger")
        return redirect(url_for('admin_users_page'))

    if role == "placement" and not has_permission(current_user, "users.create_placement"):
        flash("Access Denied: Only Developers can create Placement Officer accounts.", "danger")
        return redirect(url_for('admin_users_page'))

    try:
        create_user(username, password, role, student_id=student_id, must_change_password=False)
        log_audit_event(
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            effective_role=current_user.role,
            action="user_created",
            endpoint="/admin/create_user",
            detail=f"User: {username} ({role})",
            status="success",
            ip_address=request.remote_addr
        )
        flash(f"Account '{username}' ({role.capitalize()}) created successfully!", "success")
    except Exception as e:
        flash(f"Failed to create user: {e}", "danger")

    return redirect(url_for('admin_users_page'))


@app.route('/admin/import_students', methods=['POST'])
@permission_required('users.import_students')
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
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            effective_role=current_user.role,
            action="students_batch_import",
            endpoint="/admin/import_students",
            detail=f"Created: {created}, Skipped: {skipped}",
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


@app.route('/admin/students', methods=['GET'])
@permission_required('students.manage')
def admin_students_page():
    """Placement officer & Coordinator portal to view, alter, and manage student records."""
    seed_student_records_from_documents(DOCUMENTS_DIR)
    students = get_all_student_records()
    return render_template('admin_students.html', students=students, active_page='students')


@app.route('/admin/students/save', methods=['POST'])
@permission_required('students.manage')
def admin_students_save():
    """Modify or insert a student academic and placement record."""
    student_id = request.form.get('student_id', '').strip()
    name = request.form.get('name', '').strip()
    specialization = request.form.get('specialization', '').strip()
    cgpa = request.form.get('cgpa', '0.0').strip()
    backlogs = request.form.get('backlogs', '0').strip()
    placement_status = request.form.get('placement_status', 'Eligible').strip()
    placed_company = request.form.get('placed_company', '').strip() or None

    if not student_id or not name:
        flash("Student ID and Full Name are required.", "danger")
        return redirect(url_for('admin_students_page'))

    data = {
        "student_id": student_id,
        "name": name,
        "specialization": specialization or "Computer Science",
        "cgpa": cgpa,
        "backlogs": backlogs,
        "placement_status": placement_status,
        "placed_company": placed_company
    }

    success = upsert_student_record(data)
    if success:
        log_audit_event(
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            effective_role=current_user.role,
            action="student_record_modified",
            endpoint="/admin/students/save",
            detail=f"Modified student {student_id} ({name}): CGPA={cgpa}, Backlogs={backlogs}, Status={placement_status}",
            effective_student_id=student_id,
            status="success",
            ip_address=request.remote_addr
        )
        flash(f"Student record for '{student_id}' ({name}) updated successfully!", "success")
    else:
        flash("Failed to save student record.", "danger")

    return redirect(url_for('admin_students_page'))


@app.route('/admin/students/delete/<student_id>', methods=['POST'])
@permission_required('students.manage')
def admin_students_delete(student_id):
    """Delete a student record with audit tracking."""
    deleted = delete_student_record(student_id)
    if deleted:
        log_audit_event(
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            effective_role=current_user.role,
            action="student_record_deleted",
            endpoint=f"/admin/students/delete/{student_id}",
            detail=f"Deleted student record: {student_id}",
            effective_student_id=student_id,
            status="success",
            ip_address=request.remote_addr
        )
        flash(f"Student record '{student_id}' was removed.", "info")
    return redirect(url_for('admin_students_page'))


@app.route('/audit_logs', methods=['GET'])
@permission_required('audit.view_own_portal')
def audit_logs_page():
    """Security audit log viewer for compliance monitoring."""
    include_dev = has_permission(current_user, 'audit.view_all')
    logs = get_audit_logs(
        200,
        include_developer_actions=include_dev,
        officer_user_id=None if include_dev else current_user.id
    )
    return render_template('audit_logs.html', logs=logs, active_page='audit')


# =========================================================================
# Developer Operations & Impersonation Routes
# =========================================================================

@app.route('/dev', methods=['GET'])
@app.route('/dev/dashboard', methods=['GET'])
@permission_required('system.config')
def dev_dashboard():
    """Developer operations dashboard."""
    scope = scope_for(current_user)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    conn.close()

    return render_template(
        'dev/dashboard.html',
        active_page='dev_dashboard',
        active_scope_name=scope.name,
        chroma_filter=scope.chroma_where(),
        sql_mode=scope.sql_mode(),
        total_users=total_users
    )


@app.route('/dev/users', methods=['GET'])
@permission_required('users.set_role')
def dev_users_page():
    """Developer user & role authority view."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, student_id, must_change_password, active, created_at FROM users ORDER BY id DESC")
    users = [dict(r) for r in cur.fetchall()]
    conn.close()
    return render_template('dev/users.html', users=users, active_page='dev_users')


@app.route('/dev/update_user_role', methods=['POST'])
@permission_required('users.set_role')
def dev_update_user_role():
    """Promote or demote user roles while guaranteeing the last developer cannot be demoted."""
    user_id = request.form.get('user_id')
    new_role = request.form.get('new_role')
    ok, msg = set_user_role(user_id, new_role)
    if ok:
        log_audit_event(
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            effective_role=current_user.role,
            action="user.set_role",
            endpoint="/dev/update_user_role",
            detail=f"User #{user_id} role set to {new_role}",
            status="success",
            ip_address=request.remote_addr
        )
        flash(f"User role updated to {new_role.capitalize()}.", "success")
    else:
        flash(msg, "danger")
    return redirect(url_for('dev_users_page'))


@app.route('/dev/toggle_user_status', methods=['POST'])
@permission_required('users.set_role')
def dev_toggle_user_status():
    """Toggle user active status while guaranteeing the last developer cannot be disabled."""
    user_id = request.form.get('user_id')
    active = request.form.get('active') == '1'
    ok, msg = set_user_active_status(user_id, active)
    if ok:
        status_name = "enabled" if active else "disabled"
        log_audit_event(
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            effective_role=current_user.role,
            action="user.set_active",
            endpoint="/dev/toggle_user_status",
            detail=f"User #{user_id} {status_name}",
            status="success",
            ip_address=request.remote_addr
        )
        flash(f"User account {status_name}.", "info")
    else:
        flash(msg, "danger")
    return redirect(url_for('dev_users_page'))


@app.route('/dev/config', methods=['GET'])
@permission_required('system.config')
def dev_config_page():
    """Runtime engine parameters inspection."""
    return render_template(
        'dev/config.html',
        active_page='dev_config',
        default_model=DEFAULT_OLLAMA_MODEL,
        embedding_model=EMBEDDING_MODEL_NAME,
        ollama_url=OLLAMA_BASE_URL,
        chroma_path=CHROMA_DB_PATH,
        auth_db_path=str(AUTH_DB_PATH),
        permissions_map=PERMISSIONS
    )


@app.route('/dev/logs', methods=['GET'])
@permission_required('audit.view_all')
def dev_logs_page():
    """Global audit trail including developer actions."""
    logs = get_audit_logs(300, include_developer_actions=True)
    return render_template('audit_logs.html', logs=logs, active_page='dev_logs')


@app.route('/dev/danger', methods=['GET'])
@permission_required('db.reset')
def dev_danger_page():
    """Protected developer danger zone view."""
    return render_template('dev/danger.html', active_page='dev_danger')


@app.route('/dev/reset_db', methods=['POST'])
@app.route('/api/reset_db', methods=['POST'], endpoint='api_reset_db')
@permission_required('db.reset')
def dev_reset_db():
    """
    Destructive database wipe strictly reserved for developer.
    Requires password re-auth, reason string (>= 10 chars), and typed 'RESET' confirmation.
    """
    json_data = request.get_json(silent=True) or {}
    password = request.form.get('password') or json_data.get('password', '')
    confirm_text = request.form.get('confirm') or json_data.get('confirm', '')
    reason = (request.form.get('reason') or json_data.get('reason', '')).strip()

    is_json = request.is_json or request.path.startswith('/api/')

    user_row = get_user_by_username(current_user.username)
    if not user_row or not check_password_hash(user_row["password_hash"], password):
        log_audit_event(
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            effective_role=current_user.role,
            action="db.reset_rejected",
            endpoint=request.path,
            detail="Failed password verification",
            status="forbidden",
            ip_address=request.remote_addr
        )
        if is_json:
            return jsonify({"status": "error", "message": "Password verification failed."}), 403
        flash("Password verification failed. Database wipe aborted.", "danger")
        return redirect(url_for('dev_danger_page'))

    if confirm_text != "RESET":
        if is_json:
            return jsonify({"status": "error", "message": "Must type exact confirmation 'RESET'."}), 400
        flash("Confirmation failed: You must type RESET exactly in all caps.", "warning")
        return redirect(url_for('dev_danger_page'))

    if len(reason) < 10:
        if is_json:
            return jsonify({"status": "error", "message": "A justification reason of at least 10 characters is required."}), 400
        flash("Audit requirement: A justification reason of at least 10 characters is required.", "warning")
        return redirect(url_for('dev_danger_page'))

    reset_collection()
    import shutil
    if os.path.exists(DOCUMENTS_DIR):
        try:
            shutil.rmtree(DOCUMENTS_DIR)
        except Exception as e:
            print(f"Error removing documents directory: {e}")

    log_audit_event(
        actor_user_id=current_user.id,
        actor_username=current_user.username,
        effective_role=current_user.role,
        action="db.reset",
        endpoint=request.path,
        detail=f"Reason: {reason}",
        status="success",
        ip_address=request.remote_addr
    )

    if is_json:
        return jsonify({"status": "success", "message": "Database wiped successfully.", "reason": reason})

    flash(f"Local database purged successfully. Reason logged: '{reason}'.", "warning")
    return redirect(url_for('dev_dashboard'))


@app.route('/dev/view_as', methods=['POST'])
@login_required
def start_view_as():
    """Enter developer impersonation ('view as') mode with automatic permission drop."""
    if not getattr(current_user, 'is_developer', False):
        abort(403)

    json_data = request.get_json(silent=True) or {}
    target_role = (request.form.get('role') or json_data.get('role', '')).strip().lower()
    target_stu_id = (request.form.get('student_id') or json_data.get('student_id', '')).strip()

    if target_role == "student":
        session["view_as"] = {"role": "student", "student_id": target_stu_id or "STU001"}
    elif target_role == "placement":
        session["view_as"] = {"role": "placement", "student_id": None}
    else:
        abort(400)

    log_audit_event(
        actor_user_id=current_user.id,
        actor_username=current_user.username,
        effective_role=target_role,
        effective_student_id=session["view_as"].get("student_id"),
        action="impersonate.start",
        endpoint="/dev/view_as",
        detail=f"Target: {target_role} ({session['view_as'].get('student_id')})",
        status="success",
        ip_address=request.remote_addr
    )
    flash(f"Developer Impersonation Active: Now viewing system as {target_role.capitalize()}.", "info")
    return redirect(url_for('index'))


@app.route('/dev/view_as/stop', methods=['GET', 'POST'])
@login_required
def stop_view_as():
    """Exit developer impersonation mode and restore developer authorities."""
    if session.get("view_as"):
        prior = session.pop("view_as", None)
        log_audit_event(
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            effective_role=current_user.role,
            action="impersonate.stop",
            endpoint="/dev/view_as/stop",
            detail=f"Exited view-as for {prior}",
            status="success",
            ip_address=request.remote_addr
        )
        flash("Exited View-As mode. Full developer privileges restored.", "success")
    return redirect(url_for('dev_dashboard') if current_user.is_developer else url_for('index'))


# =========================================================================
# Core QA Studio & Document Routes (Scope-Driven)
# =========================================================================

@app.route('/', methods=['GET'])
@login_required
def index():
    """Main Local QA Studio View driven by QueryScope abstraction."""
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

    scope = scope_for(current_user)

    if query:
        t0 = time.time()
        
        # Scope Path A: Student Scope (Restricted to own row and public notices)
        if scope.sql_mode() == "own_record":
            if is_aggregate_query(query):
                answer = (
                    "**Access Restricted:** Institutional aggregates, batch statistics, and peer rankings "
                    "are confidential and reserved for Placement Officers. "
                    "You may ask questions about placement eligibility criteria, company visit schedules, "
                    "or your personal placement profile."
                )
                results = []
            else:
                final_prompt, sql_q, sql_res, citations = execute_student_scoped_query(
                    query=query,
                    student_id=scope.bound_student_id(),
                    documents_dir=DOCUMENTS_DIR,
                    model_name=selected_model
                )
                if final_prompt:
                    t2 = time.time()
                    answer = generate_ollama_answer(prompt=final_prompt, model_name=selected_model)
                    results = citations
                    generation_time = round(time.time() - t2, 3)
                else:
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

        # Scope Path B: Placement / Developer Scope (Full Unrestricted Scope)
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

    student_record = None
    if scope.name == "student" and scope.bound_student_id():
        try:
            student_record = get_student_record(scope.bound_student_id(), Path(DOCUMENTS_DIR))
        except Exception:
            student_record = None

    public_docs = [d for d in (db_stats.get('source_details') or []) if d.get('visibility') == 'public']

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
        student_record=student_record,
        public_docs=public_docs,
        active_page='qa'
    )


@app.route('/documents', methods=['GET'])
@permission_required('docs.inspect')
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


@app.route('/documents/view/<path:filename>', methods=['GET'])
@login_required
def view_document_file(filename):
    """Serve or view an uploaded document file honoring visibility scope."""
    doc_path = Path(DOCUMENTS_DIR) / filename
    if not doc_path.exists() or not doc_path.is_file():
        abort(404)

    # Check permission for internal documents
    if not has_permission(current_user, 'docs.inspect'):
        db_st = stats()
        doc_info = next((d for d in (db_st.get("source_details") or []) if d.get("name") == filename), None)
        if not doc_info or doc_info.get("visibility") != "public":
            abort(403)

    return send_from_directory(str(Path(DOCUMENTS_DIR).resolve()), filename)


@app.route('/profile', methods=['GET'])
@login_required
def profile_page():
    """Unified user profile view tailored for Student, Officer, and Developer roles."""
    scope = scope_for(current_user)
    student_record = None
    if scope.name == "student" and scope.bound_student_id():
        try:
            student_record = get_student_record(scope.bound_student_id(), Path(DOCUMENTS_DIR))
        except Exception:
            student_record = None

    db_stats = stats()
    total_users_count = 0
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        total_users_count = cur.fetchone()[0]
        conn.close()
    except Exception:
        pass

    return render_template(
        'profile.html',
        student_record=student_record,
        db_stats=db_stats,
        total_users=total_users_count,
        active_page='profile'
    )


@app.route('/settings', methods=['GET'])
@login_required
def settings_page():
    """Application preferences and accessibility settings."""
    return render_template(
        'settings.html',
        active_page='settings'
    )


@app.route('/system_info', methods=['GET'])
@permission_required('system.config')
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
@permission_required('docs.upload')
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
                    actor_user_id=current_user.id,
                    actor_username=current_user.username,
                    effective_role=current_user.role,
                    action="document_upload",
                    endpoint="/api/upload",
                    detail=f"File: {filename}, Scope: {clean_visibility}, Chunks: {len(chunks)}",
                    sources=filename,
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
@permission_required('docs.tag')
def api_update_doc_visibility():
    """Toggle document visibility between 'public' and 'internal'."""
    source_name = request.form.get('source_name', '').strip()
    new_visibility = request.form.get('new_visibility', 'internal').strip().lower()
    clean_visibility = "public" if new_visibility == "public" else "internal"
    
    if source_name:
        update_source_visibility(source_name, clean_visibility)
        log_audit_event(
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            effective_role=current_user.role,
            action="update_visibility",
            endpoint="/api/update_doc_visibility",
            detail=f"{source_name} -> {clean_visibility}",
            sources=source_name,
            status="success",
            ip_address=request.remote_addr
        )
        flash(f"Document '{source_name}' visibility set to {clean_visibility.upper()}.", "info")
    return redirect(url_for('documents_page'))


@app.route('/api/delete_doc', methods=['POST'])
@permission_required('docs.delete')
def api_delete_doc():
    """Delete document source and vector embeddings."""
    source_name = request.form.get('source_name')
    if source_name:
        delete_source(source_name)
        log_audit_event(
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            effective_role=current_user.role,
            action="document_delete",
            endpoint="/api/delete_doc",
            detail=f"Deleted source: {source_name}",
            sources=source_name,
            status="success",
            ip_address=request.remote_addr
        )
        flash(f"Document '{source_name}' and its vector embeddings were removed.", "info")
    return redirect(url_for('documents_page'))


@app.route('/api/stream_query', methods=['POST'])
@login_required
def api_stream_query():
    """Stream response tokens from Ollama using SSE with strict QueryScope data isolation."""
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    model = data.get('model') or list_ollama_models()[0]
    sources = data.get('sources', [])
    mode = data.get('mode', 'rag')
    top_k = data.get('top_k', 4)

    if not query:
        return jsonify({"error": "Empty query"}), 400

    scope = scope_for(current_user)

    # Record query into immutable audit trail with actor vs effective role
    eff_role = session.get("view_as", {}).get("role") if session.get("view_as") else current_user.role
    eff_stu_id = session.get("view_as", {}).get("student_id") if session.get("view_as") else getattr(current_user, "student_id", None)
    log_audit_event(
        actor_user_id=current_user.id,
        actor_username=current_user.username,
        effective_role=eff_role,
        effective_student_id=eff_stu_id,
        action="stream_query",
        endpoint="/api/stream_query",
        detail=query[:200],
        status="success",
        ip_address=request.remote_addr
    )

    def event_stream():
        # Flush immediate SSE comment so Cloudflare / reverse proxies immediately open the stream
        yield ": ping\n\n"
        try:
            # -------------------------------------------------------------
            # Path A: Authenticated Student Scope (Zero-Trust Row-Level Isolation)
            # -------------------------------------------------------------
            if scope.sql_mode() == "own_record":
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

                final_prompt, sql_q, sql_res, citations = execute_student_scoped_query(
                    query=query,
                    student_id=scope.bound_student_id(),
                    documents_dir=DOCUMENTS_DIR,
                    model_name=model
                )
                if final_prompt:
                    # Students do not require citations for answer retrieval
                    yield f"data: {json.dumps({'type': 'context', 'citations': []})}\n\n"
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

                    # Students do not require citations for answer retrieval
                    yield f"data: {json.dumps({'type': 'context', 'citations': []})}\n\n"
                    prompt = build_rag_prompt(query, context_chunks)
                else:
                    prompt = query
                    yield f"data: {json.dumps({'type': 'context', 'citations': []})}\n\n"

                for stream_chunk in generate_ollama_stream(prompt=prompt, model_name=model):
                    yield stream_chunk
                return

            # -------------------------------------------------------------
            # Path B: Placement Officer & Developer Scope (Full Administrative Reach)
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

        except Exception as e:
            yield f"data: {json.dumps({'error': f'Streaming backend error: {str(e)}'})}\n\n"

    response = Response(stream_with_context(event_stream()), mimetype="text/event-stream")
    response.headers['Cache-Control'] = 'no-cache, no-transform'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


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
    import platform
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
    import platform
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


# =========================================================================
# Issue Resolving & Support Ticket Routes
# =========================================================================

@app.route('/tickets', methods=['GET'])
@login_required
def tickets_list():
    """List issues and support tickets scoped strictly to user role."""
    status_filter = request.args.get('status')
    category_filter = request.args.get('category')
    priority_filter = request.args.get('priority')
    target_filter = request.args.get('target')

    tickets = get_tickets_for_user(
        current_user,
        status_filter=status_filter,
        category_filter=category_filter,
        priority_filter=priority_filter,
        target_filter=target_filter
    )
    ticket_stats = get_ticket_stats(current_user)

    # Determine eligible categories and available targets based on role
    if current_user.is_student:
        available_categories = CATEGORIES_STUDENT
        default_target = "placement"
    elif current_user.is_placement:
        available_categories = CATEGORIES_PLACEMENT
        default_target = "developer"
    else:
        available_categories = CATEGORIES_DEVELOPER + CATEGORIES_PLACEMENT
        default_target = "placement"

    return render_template(
        'tickets/list.html',
        active_page='tickets',
        tickets=tickets,
        ticket_stats=ticket_stats,
        available_categories=available_categories,
        default_target=default_target,
        status_filter=status_filter,
        category_filter=category_filter,
        priority_filter=priority_filter,
        target_filter=target_filter
    )


@app.route('/tickets/create', methods=['POST'])
@login_required
def create_ticket_route():
    """File a new issue / discrepancy ticket."""
    title = request.form.get('title', '').strip()
    category = request.form.get('category', '').strip()
    priority = request.form.get('priority', 'medium').strip().lower()
    description = request.form.get('description', '').strip()
    target_role = request.form.get('target_role', '').strip().lower()

    if not title or not description:
        flash("Ticket title and description cannot be empty.", "warning")
        return redirect(url_for('tickets_list'))

    # If student, target is placement by default unless reporting a technical system issue
    if current_user.is_student:
        if category == "technical_issue":
            target_role = target_role if target_role in ("placement", "developer") else "developer"
        else:
            target_role = "placement"
        student_id = current_user.student_id or None
    elif current_user.is_placement:
        target_role = target_role if target_role in ("placement", "developer") else "developer"
        student_id = request.form.get('student_id', '').strip() or None
    else:
        target_role = target_role if target_role in ("placement", "developer") else "placement"
        student_id = request.form.get('student_id', '').strip() or None

    ticket_id = create_ticket(
        creator_id=current_user.id,
        creator_username=current_user.username,
        creator_role=current_user.role,
        target_role=target_role,
        category=category,
        priority=priority,
        title=title,
        description=description,
        student_id=student_id
    )

    log_audit_event(
        actor_user_id=current_user.id,
        actor_username=current_user.username,
        effective_role=current_user.role,
        action="ticket.create",
        endpoint="/tickets/create",
        detail=f"Created ticket #{ticket_id}: '{title}' -> target: {target_role}",
        status="success",
        ip_address=request.remote_addr
    )

    flash("Issue ticket submitted successfully. Support team has been notified.", "success")
    return redirect(url_for('view_ticket_route', ticket_id=ticket_id))


@app.route('/tickets/<int:ticket_id>', methods=['GET'])
@login_required
def view_ticket_route(ticket_id: int):
    """View ticket details, student record context, and discussion thread."""
    ticket = get_ticket_by_id(ticket_id)
    if not ticket:
        flash("Ticket not found.", "warning")
        return redirect(url_for('tickets_list'))

    if not can_user_access_ticket(current_user, ticket):
        log_audit_event(
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            effective_role=current_user.role,
            action="ticket.unauthorized_access",
            endpoint=f"/tickets/{ticket_id}",
            detail=f"Denied access to ticket #{ticket_id}",
            status="forbidden",
            ip_address=request.remote_addr
        )
        flash("Access Denied: You do not have permission to view this ticket.", "danger")
        return redirect(url_for('tickets_list'))

    # Student cannot see internal notes; coordinators and developers can
    messages = get_ticket_messages(ticket_id, include_internal=not current_user.is_student)

    # Optional: fetch student record snapshot if ticket has a student_id
    student_record = None
    if ticket.get("student_id"):
        try:
            student_record = get_student_record(ticket["student_id"], DOCUMENTS_DIR)
        except Exception:
            student_record = None

    return render_template(
        'tickets/view.html',
        active_page='tickets',
        ticket=ticket,
        messages=messages,
        student_record=student_record
    )


@app.route('/tickets/<int:ticket_id>/reply', methods=['POST'])
@login_required
def reply_ticket_route(ticket_id: int):
    """Post a threaded reply or internal note on a ticket."""
    ticket = get_ticket_by_id(ticket_id)
    if not ticket or not can_user_access_ticket(current_user, ticket):
        flash("Access Denied or Ticket not found.", "danger")
        return redirect(url_for('tickets_list'))

    message = request.form.get('message', '').strip()
    if not message:
        flash("Message cannot be blank.", "warning")
        return redirect(url_for('view_ticket_route', ticket_id=ticket_id))

    is_internal = False
    # Only placement officers and developers can post internal notes
    if not current_user.is_student:
        is_internal = request.form.get('is_internal_note') == '1'

    add_ticket_message(
        ticket_id=ticket_id,
        sender_id=current_user.id,
        sender_username=current_user.username,
        sender_role=current_user.role,
        message=message,
        is_internal_note=is_internal
    )

    # If ticket was resolved or closed and student replies, reopen ticket as in_progress
    if current_user.is_student and ticket["status"] in ("resolved", "closed"):
        update_ticket_status(ticket_id, "in_progress")

    log_audit_event(
        actor_user_id=current_user.id,
        actor_username=current_user.username,
        effective_role=current_user.role,
        action="ticket.reply",
        endpoint=f"/tickets/{ticket_id}/reply",
        detail=f"Replied on ticket #{ticket_id} (Internal Note: {is_internal})",
        status="success",
        ip_address=request.remote_addr
    )

    flash("Reply posted successfully.", "success")
    return redirect(url_for('view_ticket_route', ticket_id=ticket_id))


@app.route('/tickets/<int:ticket_id>/status', methods=['POST'])
@login_required
def update_ticket_status_route(ticket_id: int):
    """Update ticket resolution status and documentation."""
    ticket = get_ticket_by_id(ticket_id)
    if not ticket or not can_user_access_ticket(current_user, ticket):
        flash("Access Denied or Ticket not found.", "danger")
        return redirect(url_for('tickets_list'))

    new_status = request.form.get('status', '').strip().lower()
    resolution_notes = request.form.get('resolution_notes', None)

    # Students can only close their own ticket if it is resolved, or reopen it
    if current_user.is_student:
        if new_status not in ("closed", "open"):
            flash("Students can only mark resolved tickets as Closed or Reopen them.", "warning")
            return redirect(url_for('view_ticket_route', ticket_id=ticket_id))
    else:
        # Placement and Developers have full status management
        if new_status not in ("open", "in_progress", "resolved", "closed"):
            flash("Invalid status selected.", "warning")
            return redirect(url_for('view_ticket_route', ticket_id=ticket_id))

    update_ticket_status(
        ticket_id=ticket_id,
        new_status=new_status,
        resolution_notes=resolution_notes,
        assigned_to_id=current_user.id if new_status == 'in_progress' and not ticket.get('assigned_to_id') else None,
        assigned_to_username=current_user.username if new_status == 'in_progress' and not ticket.get('assigned_to_id') else None
    )

    # If resolution notes were provided, also record them as an explicit system message in the thread
    if resolution_notes and resolution_notes.strip():
        add_ticket_message(
            ticket_id=ticket_id,
            sender_id=current_user.id,
            sender_username=current_user.username,
            sender_role=current_user.role,
            message=f"**Official Resolution:** {resolution_notes.strip()}",
            is_internal_note=False
        )

    log_audit_event(
        actor_user_id=current_user.id,
        actor_username=current_user.username,
        effective_role=current_user.role,
        action="ticket.status_update",
        endpoint=f"/tickets/{ticket_id}/status",
        detail=f"Ticket #{ticket_id} status changed to '{new_status}'",
        status="success",
        ip_address=request.remote_addr
    )

    flash(f"Ticket status updated to {new_status.replace('_', ' ').capitalize()}.", "info")
    return redirect(url_for('view_ticket_route', ticket_id=ticket_id))


@app.errorhandler(403)
def forbidden_error(e):
    return render_template('errors/403.html'), 403


@app.errorhandler(404)
def not_found_error(e):
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_error(e):
    return render_template('errors/500.html'), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print("\n" + "=" * 65)
    print("  LOCAL DATABASE QA SYSTEM (3-TIER RBAC & DEVELOPER CONTROL)")
    print(f"  ACCESS AT: http://127.0.0.1:{port}")
    print("=" * 65 + "\n")
    app.run(host="0.0.0.0", port=port, debug=True)
