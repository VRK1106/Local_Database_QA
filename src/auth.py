"""Authentication, Permission Registry, and Security Auditing for Portals and Developer Role."""

from __future__ import annotations
import sqlite3
import datetime
import secrets
import string
from pathlib import Path
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from src.config import AUTH_DB_PATH


# =========================================================================
# Explicit Permissions Registry (One Core, Multi-Role)
# =========================================================================

PERMISSIONS = {
    "student": {
        "query.public",
        "query.own_record",
        "account.change_password",
        "tickets.create",
        "tickets.view_own",
    },
    "placement": {
        "query.public",
        "query.all",
        "account.change_password",
        "docs.upload",
        "docs.delete",
        "docs.inspect",
        "docs.tag",
        "users.import_students",
        "users.reset_student_password",
        "users.disable_student",
        "audit.view_own_portal",
        "tickets.create",
        "tickets.view_own",
        "tickets.manage_placement",
    },
}

PERMISSIONS["developer"] = PERMISSIONS["placement"] | {
    "query.own_record",
    "users.create_placement",
    "users.set_role",
    "system.config",
    "system.logs",
    "audit.view_all",
    "db.reindex",
    "db.reset",
    "impersonate.student",
    "impersonate.placement",
    "tickets.manage_developer",
    "tickets.view_all",
}


def has_permission(user, perm: str) -> bool:
    """
    Check if the user holds a specific permission string.
    During developer impersonation ('view_as'), permissions drop strictly to the target role.
    Unknown or unregistered permissions safely fail-closed (return False).
    """
    if not user:
        return False
    role = getattr(user, "role", None)
    if not role:
        return False

    from flask import session, has_request_context
    if has_request_context():
        view_as = session.get("view_as")
        if role == "developer" and view_as:
            role = view_as.get("role", role)

    return perm in PERMISSIONS.get(role, set())


# =========================================================================
# User Model
# =========================================================================

class User(UserMixin):
    """Flask-Login compatible User model with role helpers."""
    def __init__(
        self,
        id: int,
        username: str,
        role: str,
        student_id: str | None = None,
        must_change_password: bool = False,
        active: bool = True
    ):
        self.id = str(id)
        self.username = username
        self.role = role
        self.student_id = student_id
        self.must_change_password = bool(must_change_password)
        self.active = bool(active)

    @property
    def is_active(self) -> bool:
        return self.active

    @property
    def is_placement(self) -> bool:
        return self.role == "placement"

    @property
    def is_student(self) -> bool:
        return self.role == "student"

    @property
    def is_developer(self) -> bool:
        return self.role == "developer"

    def has_permission(self, perm: str) -> bool:
        """Check if user holds a specific permission string (considering view_as)."""
        return has_permission(self, perm)


def get_db_connection() -> sqlite3.Connection:
    """Return a thread-safe connection to the authentication SQLite database."""
    conn = sqlite3.connect(str(AUTH_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db():
    """Initialize SQLite tables for users and enhanced audit logs, migrating schema if needed."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            student_id TEXT,
            must_change_password INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER,
            actor_username TEXT,
            effective_role TEXT,
            effective_student_id TEXT,
            action TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            detail TEXT,
            sources TEXT,
            status TEXT DEFAULT 'success',
            ip_address TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_number TEXT UNIQUE NOT NULL,
            creator_id INTEGER NOT NULL,
            creator_username TEXT NOT NULL,
            creator_role TEXT NOT NULL,
            target_role TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'open',
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            student_id TEXT,
            assigned_to_id INTEGER,
            assigned_to_username TEXT,
            resolution_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ticket_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            sender_username TEXT NOT NULL,
            sender_role TEXT NOT NULL,
            message TEXT NOT NULL,
            is_internal_note INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
        );
    """)
    conn.commit()

    # Migration check for existing audit_logs columns
    cur.execute("PRAGMA table_info(audit_logs);")
    existing_cols = {row[1] for row in cur.fetchall()}
    columns_to_add = [
        ("actor_user_id", "INTEGER"),
        ("actor_username", "TEXT"),
        ("effective_role", "TEXT"),
        ("effective_student_id", "TEXT"),
        ("detail", "TEXT"),
        ("sources", "TEXT"),
    ]
    for col_name, col_type in columns_to_add:
        if col_name not in existing_cols:
            try:
                cur.execute(f"ALTER TABLE audit_logs ADD COLUMN {col_name} {col_type};")
            except Exception:
                pass
    conn.commit()

    # Seed default placement administrator if no placement/developer user exists
    cur.execute("SELECT id FROM users WHERE role IN ('placement', 'developer') LIMIT 1;")
    if not cur.fetchone():
        admin_pass_hash = generate_password_hash("admin123")
        cur.execute("""
            INSERT INTO users (username, password_hash, role, student_id, must_change_password, active)
            VALUES (?, ?, 'placement', NULL, 0, 1)
        """, ("admin", admin_pass_hash))
        conn.commit()
        print("[AUTH] Initial placement administrator seeded: username='admin', password='admin123'")

    conn.close()


def get_user_by_id(user_id: int | str) -> User | None:
    """Fetch user by primary key ID."""
    if not user_id:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, student_id, must_change_password, active FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return User(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            student_id=row["student_id"],
            must_change_password=row["must_change_password"],
            active=row["active"]
        )
    return None


def get_user_by_username(username: str) -> dict | None:
    """Fetch user dict including password hash by username."""
    if not username:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def verify_user_password(username: str, password: str) -> User | None:
    """Verify credentials and return User instance if valid, else None."""
    user_row = get_user_by_username(username)
    if not user_row or not user_row.get("active"):
        return None
    if check_password_hash(user_row["password_hash"], password):
        return User(
            id=user_row["id"],
            username=user_row["username"],
            role=user_row["role"],
            student_id=user_row["student_id"],
            must_change_password=user_row["must_change_password"],
            active=user_row["active"]
        )
    return None


def create_user(
    username: str,
    password: str,
    role: str,
    student_id: str | None = None,
    must_change_password: bool = False
) -> int:
    """Create a new user and return the inserted ID."""
    conn = get_db_connection()
    cur = conn.cursor()
    pwd_hash = generate_password_hash(password)
    cur.execute("""
        INSERT INTO users (username, password_hash, role, student_id, must_change_password, active)
        VALUES (?, ?, ?, ?, ?, 1)
    """, (username.strip(), pwd_hash, role, student_id, 1 if must_change_password else 0))
    user_id = cur.lastrowid
    conn.commit()
    conn.close()
    return user_id


def create_developer_account(username: str, password: str) -> int:
    """CLI utility function to provision a new developer account with security checks."""
    if len(password) < 12:
        raise ValueError("Developer passwords must be at least 12 characters.")
    return create_user(
        username=username,
        password=password,
        role="developer",
        student_id=None,
        must_change_password=False
    )


def count_active_developers() -> int:
    """Return count of active developer accounts in the system."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'developer' AND active = 1;")
    res = cur.fetchone()
    count = res[0] if res else 0
    conn.close()
    return count


def set_user_role(user_id: int | str, new_role: str) -> tuple[bool, str]:
    """Change a user's role while enforcing that the last developer cannot be demoted."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT role, active FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, "User not found."

    if row["role"] == "developer" and new_role != "developer":
        if count_active_developers() <= 1:
            conn.close()
            return False, "Security constraint: The last active developer cannot be demoted."

    cur.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    conn.commit()
    conn.close()
    return True, "Role updated successfully."


def set_user_active_status(user_id: int | str, active: bool) -> tuple[bool, str]:
    """Enable or disable account while guaranteeing the last developer cannot be disabled."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT role, active FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, "User not found."

    if row["role"] == "developer" and not active:
        if count_active_developers() <= 1:
            conn.close()
            return False, "Security constraint: The last active developer cannot be disabled."

    cur.execute("UPDATE users SET active = ? WHERE id = ?", (1 if active else 0, user_id))
    conn.commit()
    conn.close()
    return True, "User active status updated."


def update_password(user_id: int | str, new_password: str) -> bool:
    """Update user password and clear the must_change_password flag."""
    conn = get_db_connection()
    cur = conn.cursor()
    pwd_hash = generate_password_hash(new_password)
    cur.execute("""
        UPDATE users
        SET password_hash = ?, must_change_password = 0
        WHERE id = ?
    """, (pwd_hash, user_id))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def log_audit_event(
    actor_user_id: int | str | None = None,
    actor_username: str | None = None,
    effective_role: str | None = None,
    action: str = "",
    endpoint: str = "",
    detail: str = "",
    sources: str = "",
    effective_student_id: str | None = None,
    status: str = "success",
    ip_address: str = "",
    # Backwards-compatibility keyword arguments:
    user_id: int | str | None = None,
    username: str | None = None,
    role: str | None = None,
    query_text: str = "",
):
    """Record an immutable audit trail entry distinguishing real actor from effective role."""
    try:
        final_actor_id = actor_user_id if actor_user_id is not None else user_id
        final_actor_name = actor_username if actor_username is not None else (username or "anonymous")
        final_role = effective_role if effective_role is not None else (role or "unauthenticated")
        final_detail = detail or query_text

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_logs (
                actor_user_id, actor_username, effective_role, effective_student_id,
                user_id, username, role, query_text,
                action, endpoint, detail, sources, status, ip_address
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            final_actor_id,
            final_actor_name,
            final_role,
            effective_student_id,
            final_actor_id,
            final_actor_name,
            final_role,
            final_detail,
            action,
            endpoint,
            final_detail,
            sources,
            status,
            ip_address
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[AUDIT ERROR] Failed to record audit log: {e}")


def get_audit_logs(
    limit: int = 150,
    include_developer_actions: bool = True,
    officer_user_id: int | str | None = None
) -> list[dict]:
    """
    Retrieve recent audit logs.
    - Global developer view (include_developer_actions=True): all records.
    - Scoped placement view (officer_user_id provided): only that specific officer's actions + student actions.
    - General fallback: excludes developer actions.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    select_fields = """
        id,
        COALESCE(NULLIF(actor_user_id, 0), user_id, 0) AS actor_user_id,
        COALESCE(NULLIF(actor_user_id, 0), user_id, 0) AS user_id,
        COALESCE(NULLIF(actor_username, ''), NULLIF(username, ''), 'anonymous') AS actor_username,
        COALESCE(NULLIF(actor_username, ''), NULLIF(username, ''), 'anonymous') AS username,
        COALESCE(NULLIF(effective_role, ''), NULLIF(role, ''), 'unauthenticated') AS effective_role,
        COALESCE(NULLIF(effective_role, ''), NULLIF(role, ''), 'unauthenticated') AS role,
        effective_student_id,
        action, endpoint,
        COALESCE(NULLIF(detail, ''), NULLIF(query_text, ''), '') AS detail,
        COALESCE(NULLIF(detail, ''), NULLIF(query_text, ''), '') AS query_text,
        COALESCE(sources, '') AS sources,
        status, ip_address, timestamp
    """

    if include_developer_actions:
        cur.execute(f"""
            SELECT {select_fields}
            FROM audit_logs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
    elif officer_user_id:
        cur.execute(f"""
            SELECT {select_fields}
            FROM audit_logs
            WHERE (
                COALESCE(NULLIF(effective_role, ''), role) = 'student'
                OR (COALESCE(NULLIF(effective_role, ''), role) = 'placement' AND (actor_user_id = ? OR user_id = ?))
            )
            AND actor_user_id NOT IN (SELECT id FROM users WHERE role = 'developer')
            AND COALESCE(NULLIF(effective_role, ''), role) != 'developer'
            ORDER BY id DESC
            LIMIT ?
        """, (int(officer_user_id), int(officer_user_id), limit))
    else:
        # Placement view fallback: show student and placement actions only
        cur.execute(f"""
            SELECT {select_fields}
            FROM audit_logs
            WHERE COALESCE(NULLIF(effective_role, ''), role) != 'developer'
              AND actor_user_id NOT IN (SELECT id FROM users WHERE role = 'developer')
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def generate_temp_password(length: int = 8) -> str:
    """Generate a random temporary password."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def import_students_from_csv(csv_content: str) -> tuple[int, int, list[dict]]:
    """
    Import students from CSV text containing headers (Roll Number / USN, Name, optional Email).
    Generates accounts with temporary passwords and must_change_password=True.
    Returns (created_count, skipped_count, list_of_created_credentials).
    """
    import io
    import csv

    f = io.StringIO(csv_content)
    reader = csv.DictReader(f)
    
    headers = [h.strip() for h in (reader.fieldnames or [])]
    id_col = None
    for h in headers:
        if any(term in h.lower() for term in ["roll", "usn", "id", "reg", "student_id"]):
            id_col = h
            break

    if not id_col:
        id_col = headers[0] if headers else None

    if not id_col:
        raise ValueError("Could not detect Student ID / Roll Number / USN column in CSV.")

    created = 0
    skipped = 0
    generated_credentials = []

    conn = get_db_connection()
    cur = conn.cursor()

    for row in reader:
        student_id_val = str(row.get(id_col, "")).strip()
        if not student_id_val:
            continue

        username = student_id_val.lower()
        cur.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cur.fetchone():
            skipped += 1
            continue

        temp_pwd = generate_temp_password(8)
        pwd_hash = generate_password_hash(temp_pwd)
        cur.execute("""
            INSERT INTO users (username, password_hash, role, student_id, must_change_password, active)
            VALUES (?, ?, 'student', ?, 1, 1)
        """, (username, pwd_hash, student_id_val))

        generated_credentials.append({
            "username": username,
            "student_id": student_id_val,
            "temporary_password": temp_pwd
        })
        created += 1

    conn.commit()
    conn.close()
    return created, skipped, generated_credentials
