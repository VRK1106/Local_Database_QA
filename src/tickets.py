"""Ticket-Based Issue Resolving System for Students, Placement Coordinators, and Developers.

Manages issue triage, zero-trust RBAC scoping, threaded communications,
resolution documentation, and cross-role status coordination.
"""

from __future__ import annotations
import secrets
import datetime
from src.auth import get_db_connection


# Standard Ticket Categories
CATEGORIES_STUDENT = [
    ("academic_record", "Academic Record / CGPA Discrepancy"),
    ("placement_eligibility", "Placement Drive Eligibility Inquiry"),
    ("backlog_correction", "Backlog Status Record Correction"),
    ("circular_query", "Placement Policy / Circular Question"),
    ("technical_issue", "Technical Portal / System Glitch"),
    ("other", "General Inquiry / Other"),
]

CATEGORIES_PLACEMENT = [
    ("vector_db_sync", "Vector DB & Document Ingestion Request"),
    ("llm_hallucination", "LLM Inference Discrepancy / Hallucination Bug"),
    ("roster_import_issue", "Student Roster / Excel Import Failure"),
    ("permission_request", "Permission / Access Request"),
    ("feature_request", "System Feature Request"),
    ("other_technical", "Engineering / Infrastructure Issue"),
]

CATEGORIES_DEVELOPER = [
    ("diagnostics", "Diagnostics & Infrastructure Investigation"),
    ("cross_team", "Cross-Team Coordination & Clarification"),
    ("system_maintenance", "Scheduled Maintenance Notice / Task"),
]

VALID_STATUSES = {"open", "in_progress", "resolved", "closed"}
VALID_PRIORITIES = {"low", "medium", "high", "urgent"}


def generate_ticket_number() -> str:
    """Generate a unique human-friendly ticket identifier (e.g. TCK-8F3A)."""
    conn = get_db_connection()
    cur = conn.cursor()
    for _ in range(10):
        code = f"TCK-{secrets.token_hex(2).upper()}"
        cur.execute("SELECT id FROM tickets WHERE ticket_number = ?", (code,))
        if not cur.fetchone():
            conn.close()
            return code
    conn.close()
    return f"TCK-{int(datetime.datetime.now().timestamp())}"


def create_ticket(
    creator_id: int | str,
    creator_username: str,
    creator_role: str,
    target_role: str,
    category: str,
    priority: str,
    title: str,
    description: str,
    student_id: str | None = None
) -> int:
    """Create a new support ticket and return its primary key ID."""
    ticket_num = generate_ticket_number()
    priority = priority.lower() if priority.lower() in VALID_PRIORITIES else "medium"
    target_role = "developer" if target_role == "developer" else "placement"
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tickets (
            ticket_number, creator_id, creator_username, creator_role,
            target_role, category, priority, status, title, description,
            student_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        ticket_num, int(creator_id), creator_username, creator_role,
        target_role, category, priority, title.strip(), description.strip(),
        student_id
    ))
    ticket_id = cur.lastrowid
    conn.commit()
    conn.close()
    return ticket_id


def get_ticket_by_id(ticket_id: int) -> dict | None:
    """Fetch a single ticket record by ID."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def can_user_access_ticket(user, ticket: dict) -> bool:
    """
    Enforce Zero-Trust boundaries for ticket access:
    - Students can ONLY see tickets they created.
    - Placement Coordinators can see tickets targeted to placement or created by themselves.
    - Developers can see all tickets (global engineering transparency).
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_developer:
        return True
    
    user_id = int(user.id)
    if user.is_student:
        return ticket.get("creator_id") == user_id
    
    if user.is_placement:
        # Placement can see tickets assigned/targeted to placement cell, or tickets they filed
        return ticket.get("target_role") == "placement" or ticket.get("creator_id") == user_id
    
    return False


def get_tickets_for_user(
    user,
    status_filter: str | None = None,
    category_filter: str | None = None,
    priority_filter: str | None = None,
    target_filter: str | None = None
) -> list[dict]:
    """Retrieve tickets scoped strictly to the current user's role and permission filters."""
    if not user or not user.is_authenticated:
        return []

    conn = get_db_connection()
    cur = conn.cursor()

    conditions = []
    params = []

    # RBAC Scoping
    if user.is_student:
        conditions.append("creator_id = ?")
        params.append(int(user.id))
    elif user.is_placement:
        conditions.append("(target_role = 'placement' OR creator_id = ?)")
        params.append(int(user.id))
    elif user.is_developer:
        # Developers have global oversight over all tickets
        pass

    # Optional Filters
    if status_filter and status_filter in VALID_STATUSES:
        conditions.append("status = ?")
        params.append(status_filter)
    if category_filter:
        conditions.append("category = ?")
        params.append(category_filter)
    if priority_filter and priority_filter in VALID_PRIORITIES:
        conditions.append("priority = ?")
        params.append(priority_filter)
    if target_filter and target_filter in ("placement", "developer"):
        conditions.append("target_role = ?")
        params.append(target_filter)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT * FROM tickets
        {where_clause}
        ORDER BY 
            CASE status 
                WHEN 'open' THEN 1 
                WHEN 'in_progress' THEN 2 
                WHEN 'resolved' THEN 3 
                ELSE 4 
            END,
            updated_at DESC, created_at DESC
    """
    cur.execute(query, tuple(params))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def add_ticket_message(
    ticket_id: int,
    sender_id: int | str,
    sender_username: str,
    sender_role: str,
    message: str,
    is_internal_note: bool = False
) -> int:
    """Append a reply or internal note to a ticket thread."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ticket_messages (
            ticket_id, sender_id, sender_username, sender_role, message, is_internal_note, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        ticket_id, int(sender_id), sender_username, sender_role,
        message.strip(), 1 if is_internal_note else 0
    ))
    msg_id = cur.lastrowid

    # Update ticket updated_at timestamp
    cur.execute("UPDATE tickets SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()
    return msg_id


def get_ticket_messages(ticket_id: int, include_internal: bool = True) -> list[dict]:
    """Retrieve chronological messages for a ticket thread, filtering internal notes if needed."""
    conn = get_db_connection()
    cur = conn.cursor()
    if include_internal:
        cur.execute("""
            SELECT * FROM ticket_messages 
            WHERE ticket_id = ? 
            ORDER BY created_at ASC, id ASC
        """, (ticket_id,))
    else:
        cur.execute("""
            SELECT * FROM ticket_messages 
            WHERE ticket_id = ? AND is_internal_note = 0
            ORDER BY created_at ASC, id ASC
        """, (ticket_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_ticket_status(
    ticket_id: int,
    new_status: str,
    resolution_notes: str | None = None,
    assigned_to_id: int | None = None,
    assigned_to_username: str | None = None
) -> bool:
    """Update ticket status, assignee, and optional resolution notes."""
    if new_status not in VALID_STATUSES:
        return False
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
    params = [new_status]
    
    if resolution_notes is not None:
        updates.append("resolution_notes = ?")
        params.append(resolution_notes.strip())
        
    if assigned_to_id is not None:
        updates.append("assigned_to_id = ?")
        params.append(assigned_to_id)
        updates.append("assigned_to_username = ?")
        params.append(assigned_to_username)
        
    params.append(ticket_id)
    cur.execute(f"UPDATE tickets SET {', '.join(updates)} WHERE id = ?", tuple(params))
    conn.commit()
    conn.close()
    return True


def get_ticket_stats(user) -> dict:
    """Return summary count metrics (total, open, in_progress, resolved, closed) scoped to the user."""
    if not user or not user.is_authenticated:
        return {"total": 0, "open": 0, "in_progress": 0, "resolved": 0, "closed": 0}

    tickets = get_tickets_for_user(user)
    stats = {
        "total": len(tickets),
        "open": sum(1 for t in tickets if t["status"] == "open"),
        "in_progress": sum(1 for t in tickets if t["status"] == "in_progress"),
        "resolved": sum(1 for t in tickets if t["status"] == "resolved"),
        "closed": sum(1 for t in tickets if t["status"] == "closed"),
    }
    return stats
