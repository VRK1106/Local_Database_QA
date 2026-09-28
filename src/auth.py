"""Authentication, User Management, and Security Auditing for RBAC."""

from __future__ import annotations
import sqlite3
import datetime
import secrets
import string
from pathlib import Path
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from src.config import AUTH_DB_PATH


class User(UserMixin):
    """Flask-Login compatible User model."""
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


def get_db_connection() -> sqlite3.Connection:
    """Return a thread-safe connection to the authentication SQLite database."""
    conn = sqlite3.connect(str(AUTH_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db():
    """Initialize SQLite tables for users and audit logs, creating default accounts if empty."""
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
            user_id INTEGER,
            username TEXT,
            role TEXT,
            action TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            query_text TEXT,
            status TEXT DEFAULT 'success',
            ip_address TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()

    # Seed default placement administrator if no placement user exists
    cur.execute("SELECT id FROM users WHERE role = 'placement' LIMIT 1;")
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
    user_id: int | str | None,
    username: str | None,
    role: str | None,
    action: str,
    endpoint: str,
    query_text: str = "",
    status: str = "success",
    ip_address: str = ""
):
    """Record an audit trail entry for security compliance."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_logs (user_id, username, role, action, endpoint, query_text, status, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            username or "anonymous",
            role or "unauthenticated",
            action,
            endpoint,
            query_text,
            status,
            ip_address
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[AUDIT ERROR] Failed to record audit log: {e}")


def get_audit_logs(limit: int = 150) -> list[dict]:
    """Retrieve the most recent audit logs."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, user_id, username, role, action, endpoint, query_text, status, ip_address, timestamp
        FROM audit_logs
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
    Import students from CSV text containing headers like (Roll Number / USN, Name, optional Email).
    Generates accounts with temporary passwords and must_change_password=True.
    Returns (created_count, skipped_count, list_of_created_credentials).
    """
    import io
    import csv

    f = io.StringIO(csv_content)
    reader = csv.DictReader(f)
    
    # Identify headers flexibly
    headers = [h.strip() for h in (reader.fieldnames or [])]
    id_col = None
    for h in headers:
        if any(term in h.lower() for term in ["roll", "usn", "id", "reg", "student_id"]):
            id_col = h
            break

    if not id_col:
        # Fallback to first column
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
        # Check if already exists
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
