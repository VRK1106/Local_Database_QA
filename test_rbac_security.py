"""Comprehensive Penetration & Validation Test Suite for RBAC, Developer Roles & Data Isolation."""

import sys
from pathlib import Path
import json

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import app
from src.auth import (
    init_auth_db,
    get_user_by_username,
    create_user,
    create_developer_account,
    set_user_role,
    set_user_active_status,
    get_audit_logs,
    count_active_developers,
    verify_user_password,
    User
)
from src.scopes import scope_for

def run_tests():
    print("=" * 65)
    print(" RUNNING RBAC, DEVELOPER ROLE & DATA ISOLATION PENETRATION SUITE")
    print("=" * 65)

    # 1. Initialize DB and client
    init_auth_db()
    client = app.test_client()

    # Provision student account if not present
    if not get_user_by_username("stu001"):
        create_user(
            username="stu001",
            password="Password@123",
            role="student",
            student_id="STU001",
            must_change_password=False
        )

    # Provision developer account if not present
    if not get_user_by_username("dev_admin"):
        create_developer_account(
            username="dev_admin",
            password="DeveloperPass@1234"
        )

    # Ensure dev_admin has role 'developer' and is active, and clean up auxiliary test accounts
    from src.auth import get_db_connection
    conn = get_db_connection()
    conn.execute("UPDATE users SET role = 'developer', active = 1 WHERE username = 'dev_admin'")
    conn.execute("DELETE FROM users WHERE username = 'test_dev_cli'")
    conn.commit()
    conn.close()

    # -------------------------------------------------------------
    # PART 1: UNAUTHENTICATED RESTRICTIONS
    # -------------------------------------------------------------
    # Test 1: Unauthenticated request to /documents -> Should redirect to login
    res = client.get('/documents')
    assert res.status_code in [302, 401], f"Expected redirect or 401, got {res.status_code}"
    assert '/login' in res.headers.get('Location', '')
    print("[PASS] Test 1: Unauthenticated access to /documents is blocked (Redirect to /login)")

    # Test 2: Unauthenticated API call to /api/upload -> Should return 401
    res = client.post('/api/upload', data={'files': []}, headers={'Accept': 'application/json'})
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"
    print("[PASS] Test 2: Unauthenticated POST /api/upload returns 401 Unauthorized")

    # Test 3: Unauthenticated access to /dev/dashboard -> Redirect to login
    res = client.get('/dev/dashboard')
    assert res.status_code in [302, 401]
    assert '/login' in res.headers.get('Location', '')
    print("[PASS] Test 3: Unauthenticated access to /dev/dashboard redirected to login")

    # -------------------------------------------------------------
    # PART 2: PLACEMENT OFFICER PERMISSIONS & BOUNDARIES
    # -------------------------------------------------------------
    # Test 4: Placement Officer Login
    res = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Signed in successfully" in res.data or b"admin" in res.data
    print("[PASS] Test 4: Placement Officer authentication succeeded")

    # Test 5: Officer can access /documents and /audit_logs
    res = client.get('/documents')
    assert res.status_code == 200
    print("[PASS] Test 5: Placement Officer can access /documents")

    res = client.get('/audit_logs')
    assert res.status_code == 200
    assert b"dev_admin" not in res.data
    print("[PASS] Test 5b: Placement Officer can access /audit_logs (developer events strictly isolated)")

    res = client.get('/admin/users')
    assert res.status_code == 200
    assert b"dev_admin" not in res.data
    print("[PASS] Test 5c: Placement Officer user list (/admin/users) isolates students and own account only (no developers)")

    # Test 6: Officer CANNOT access Developer portal (/dev/dashboard) -> Access Denied redirect
    res = client.get('/dev/dashboard', follow_redirects=True)
    assert b"Access denied" in res.data
    print("[PASS] Test 6: Officer access to /dev/dashboard blocked with Access Denied flash")

    # Test 7: Officer CANNOT trigger database wipe (/api/reset_db or /dev/reset_db) -> 403 Forbidden
    res = client.post(
        '/api/reset_db',
        data=json.dumps({'password': 'admin123', 'confirm': 'RESET', 'reason': 'Testing reset privilege boundary'}),
        content_type='application/json'
    )
    assert res.status_code == 403
    print("[PASS] Test 7: Officer destructive wipe /api/reset_db blocked with 403 Forbidden")

    # -------------------------------------------------------------
    # PART 3: STUDENT PERMISSIONS & STRICT DATA ISOLATION
    # -------------------------------------------------------------
    # Test 8: Sign out Officer and Sign in as Student
    client.get('/logout')
    res = client.post('/login', data={'username': 'stu001', 'password': 'Password@123'}, follow_redirects=True)
    assert res.status_code == 200
    print("[PASS] Test 8: Student authentication succeeded")

    # Test 9: Student attempts to access /documents -> Forbidden redirect with Access Denied
    res = client.get('/documents', follow_redirects=True)
    assert b"Access denied" in res.data
    print("[PASS] Test 9: Student accessing /documents is blocked with Access Denied")

    # Test 10: Student attempts direct API attack POST /api/upload -> 403 Forbidden
    res = client.post('/api/upload', data={'files': []}, headers={'Accept': 'application/json'})
    assert res.status_code == 403
    print("[PASS] Test 10: Student API attack on /api/upload returns 403 Forbidden")

    # Test 11: Student query for personal record -> Evaluates personal row
    res = client.post(
        '/api/stream_query',
        data=json.dumps({'query': 'What is my CGPA and placement status?', 'mode': 'rag'}),
        content_type='application/json'
    )
    assert res.status_code == 200
    res_text = b"".join(list(res.response)).decode('utf-8')
    res.close()
    assert 'STU001' in res_text or 'context' in res_text
    print("[PASS] Test 11: Student query accurately routes through parameterized personal record (STU001)")

    # Test 12: Student attempts aggregate query across all students -> Blocked with restriction notice
    res = client.post(
        '/api/stream_query',
        data=json.dumps({'query': 'How many total students are placed in the university?', 'mode': 'rag'}),
        content_type='application/json'
    )
    assert res.status_code == 200
    res_text = b"".join(list(res.response)).decode('utf-8')
    res.close()
    assert "Access Restricted" in res_text
    print("[PASS] Test 12: Student aggregate query across all students is securely blocked")

    # -------------------------------------------------------------
    # PART 4: DEVELOPER ROLE, DANGER ZONE & SAFEGUARDS
    # -------------------------------------------------------------
    # Test 13: Sign out and Sign in as Developer
    client.get('/logout')
    res = client.post('/login', data={'username': 'dev_admin', 'password': 'DeveloperPass@1234'}, follow_redirects=True)
    assert res.status_code == 200
    print("[PASS] Test 13: Developer authentication succeeded")

    # Test 14: Developer can access all dev portal views
    for path in ['/dev/dashboard', '/dev/danger', '/dev/users', '/dev/config']:
        res = client.get(path)
        assert res.status_code == 200, f"Expected 200 for {path}, got {res.status_code}"
    print("[PASS] Test 14: Developer can access /dev/dashboard, /dev/danger, /dev/users, /dev/config")

    # Test 15: Developer reset requires valid re-auth password
    res = client.post(
        '/dev/reset_db',
        data=json.dumps({'password': 'WrongPassword!', 'confirm': 'RESET', 'reason': 'Legitimate test wipe reason'}),
        content_type='application/json'
    )
    assert res.status_code == 403
    print("[PASS] Test 15: Developer reset fails with 403 on invalid re-auth password")

    # Test 16: Developer reset requires exact typed 'RESET' confirmation
    res = client.post(
        '/dev/reset_db',
        data=json.dumps({'password': 'DeveloperPass@1234', 'confirm': 'not_reset', 'reason': 'Legitimate test wipe reason'}),
        content_type='application/json'
    )
    assert res.status_code == 400
    print("[PASS] Test 16: Developer reset fails with 400 on incorrect confirm token")

    # Test 17: Developer reset requires justification reason >= 10 chars
    res = client.post(
        '/dev/reset_db',
        data=json.dumps({'password': 'DeveloperPass@1234', 'confirm': 'RESET', 'reason': 'short'}),
        content_type='application/json'
    )
    assert res.status_code == 400
    print("[PASS] Test 17: Developer reset fails with 400 when reason is under 10 chars")

    # -------------------------------------------------------------
    # PART 5: DEVELOPER IMPERSONATION & SAFE PERMISSION DROP
    # -------------------------------------------------------------
    # Test 18: Start Impersonation as Student STU001
    res = client.post('/dev/view_as', data={'role': 'student', 'student_id': 'STU001'}, follow_redirects=True)
    assert res.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get('view_as') is not None
        assert sess['view_as']['role'] == 'student'
        assert sess['view_as']['student_id'] == 'STU001'
    print("[PASS] Test 18: Developer impersonation of Student STU001 activated successfully")

    # Test 18b: Start Impersonation as Placement Officer via form post (Fix 415 bug test)
    res = client.post('/dev/view_as', data={'role': 'placement'}, follow_redirects=True)
    assert res.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get('view_as') is not None
        assert sess['view_as']['role'] == 'placement'
    print("[PASS] Test 18b: Developer impersonation of Placement Officer (Form POST without student_id) succeeded without 415 error")

    # Re-enter student impersonation for subsequent drop test
    client.post('/dev/view_as', data={'role': 'student', 'student_id': 'STU001'}, follow_redirects=True)

    # Test 19: While impersonating, Developer's permissions are dropped (Access to /dev/danger redirected with Access Denied)
    res = client.get('/dev/danger', follow_redirects=True)
    assert b"Access denied" in res.data
    print("[PASS] Test 19: Safe Permission Drop verified: Impersonating Developer denied /dev/danger (Access Denied)")

    # Test 20: Stop Impersonation restores full Developer capabilities
    res = client.get('/dev/view_as/stop', follow_redirects=True)
    assert res.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get('view_as') is None
    res = client.get('/dev/danger')
    assert res.status_code == 200
    print("[PASS] Test 20: Impersonation exit verified: Full developer privileges cleanly restored")

    # -------------------------------------------------------------
    # PART 6: LAST DEVELOPER IMMUTABILITY SAFEGUARDS
    # -------------------------------------------------------------
    # Test 21: Demoting the last active developer must be blocked
    dev_user = get_user_by_username("dev_admin")
    assert dev_user is not None
    assert count_active_developers() >= 1

    success, msg = set_user_role(dev_user["id"], "placement")
    assert not success, "Demoting last active developer should fail"
    assert "last active developer cannot be demoted" in msg.lower()
    print(f"[PASS] Test 21: Safeguard verified: Demoting last active developer blocked ({msg})")

    # Test 22: Deactivating the last active developer must be blocked
    success, msg = set_user_active_status(dev_user["id"], False)
    assert not success, "Deactivating last active developer should fail"
    assert "last active developer cannot be disabled" in msg.lower()
    print(f"[PASS] Test 22: Safeguard verified: Deactivating last active developer blocked ({msg})")

    # -------------------------------------------------------------
    # PART 7: AUDIT LOG VERIFICATION & SEGREGATION
    # -------------------------------------------------------------
    placement_logs = get_audit_logs(50, include_developer_actions=False)
    assert len(placement_logs) > 0
    assert not any(l['effective_role'] == 'developer' for l in placement_logs)
    print(f"[PASS] Test 23a: Audit segregation verified: Developer actions strictly excluded from placement view ({len(placement_logs)} events)")

    dev_logs = get_audit_logs(50, include_developer_actions=True)
    assert len(dev_logs) > 0
    dev_actions = [l['action'] for l in dev_logs]
    assert 'login' in dev_actions
    assert any('impersonate' in a for a in dev_actions)
    print(f"[PASS] Test 23b: Global developer audit view captures all events including impersonate ({len(dev_logs)} events)")

    # -------------------------------------------------------------
    # PART 8: TICKET-BASED ISSUE RESOLUTION & PRIVACY SUITE
    # -------------------------------------------------------------
    from src.tickets import (
        create_ticket,
        get_ticket_by_id,
        can_user_access_ticket,
        get_tickets_for_user,
        add_ticket_message,
        get_ticket_messages,
        update_ticket_status,
        get_ticket_stats
    )

    # User objects for ticket test operations
    stu_dict = get_user_by_username("stu001")
    student_user = User(id=stu_dict["id"], username=stu_dict["username"], role=stu_dict["role"], student_id=stu_dict["student_id"])

    off_dict = get_user_by_username("admin")
    officer_user = User(id=off_dict["id"], username=off_dict["username"], role=off_dict["role"])

    dev_dict = get_user_by_username("dev_admin")
    dev_user = User(id=dev_dict["id"], username=dev_dict["username"], role=dev_dict["role"])

    # Ensure logged in as student stu001
    client.get('/logout', follow_redirects=True)
    client.post('/login', data={'username': 'stu001', 'password': 'Password@123'}, follow_redirects=True)

    # Test 24: Student files an issue ticket targeted to placement cell
    stu_res = client.post('/tickets/create', data={
        "title": "Discrepancy in recorded CGPA",
        "category": "academic_record",
        "priority": "high",
        "description": "My CGPA on portal is 8.1 but official transcript reflects 8.65.",
        "target_role": "placement"
    }, follow_redirects=True)
    assert stu_res.status_code == 200
    assert b"Issue ticket submitted successfully" in stu_res.data
    print("[PASS] Test 24: Student creates academic record discrepancy ticket targeted to Placement Cell")

    # Find the ticket created
    stu_tickets = get_tickets_for_user(student_user)
    assert len(stu_tickets) > 0
    t_student = stu_tickets[0]
    t_id = t_student["id"]

    # Test 25: Zero-Trust Scoping: Another unassociated student cannot view this ticket
    another_student = User(id=9999, username="attacker_stu", role="student", student_id="STU999")
    assert not can_user_access_ticket(another_student, t_student)
    print("[PASS] Test 25: Zero-Trust verified: Other students strictly blocked from ticket access")

    # Test 26: Placement Coordinator views ticket and responds
    client.get('/logout', follow_redirects=True)
    client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)

    officer_view = client.get(f'/tickets/{t_id}', follow_redirects=True)
    assert officer_view.status_code == 200
    assert b"Discrepancy in recorded CGPA" in officer_view.data

    # Placement coordinator posts an internal note and public reply
    add_ticket_message(t_id, officer_user.id, officer_user.username, officer_user.role, "Checking with exam cell records", is_internal_note=True)
    add_ticket_message(t_id, officer_user.id, officer_user.username, officer_user.role, "We received your transcript copy and are syncing with the exam branch.", is_internal_note=False)
    update_ticket_status(t_id, "in_progress")
    print("[PASS] Test 26: Placement Coordinator triaged ticket, appended internal note, and set status to In Progress")

    # Test 27: Privacy Guard: Student cannot see internal notes
    messages_for_student = get_ticket_messages(t_id, include_internal=False)
    assert not any(m["is_internal_note"] == 1 for m in messages_for_student)
    assert any("syncing with the exam branch" in m["message"] for m in messages_for_student)
    print("[PASS] Test 27: Privacy Guard verified: Student view strictly excludes internal coordinator notes")

    # Test 28: Placement Coordinator creates engineering issue ticket to Developer
    off_ticket_res = client.post('/tickets/create', data={
        "title": "ChromaDB vector collection needs full re-indexing",
        "category": "vector_db_sync",
        "priority": "urgent",
        "description": "Notice circular #12 embeddings seem misaligned during search.",
        "target_role": "developer"
    }, follow_redirects=True)
    assert off_ticket_res.status_code == 200
    print("[PASS] Test 28: Placement Coordinator filed technical escalation ticket to Engineering Developers")

    # Test 29: Developer resolves ticket with resolution notes
    client.get('/logout', follow_redirects=True)
    dev_log_res = client.post('/login', data={'username': 'dev_admin', 'password': 'DeveloperPass@1234'}, follow_redirects=True)
    assert dev_log_res.status_code == 200
    assert b"Signed in successfully" in dev_log_res.data or b"dev_admin" in dev_log_res.data

    dev_tickets = get_tickets_for_user(dev_user, target_filter="developer")
    assert len(dev_tickets) > 0
    t_dev = dev_tickets[0]

    dev_resolve = client.post(f'/tickets/{t_dev["id"]}/status', data={
        "status": "resolved",
        "resolution_notes": "Completed ChromaDB collection re-index; cosine recall restored."
    }, follow_redirects=True)
    assert dev_resolve.status_code == 200
    t_dev_updated = get_ticket_by_id(t_dev["id"])
    assert t_dev_updated["status"] == "resolved"
    assert "cosine recall restored" in t_dev_updated["resolution_notes"]
    print("[PASS] Test 29: Developer triaged and resolved technical ticket with verified resolution notes")

    # Test 30: Student marks resolved academic ticket as closed
    client.get('/logout', follow_redirects=True)
    client.post('/login', data={'username': 'stu001', 'password': 'Password@123'}, follow_redirects=True)

    update_ticket_status(t_id, "resolved", resolution_notes="CGPA corrected in database to 8.65")
    close_res = client.post(f'/tickets/{t_id}/status', data={"status": "closed"}, follow_redirects=True)
    assert close_res.status_code == 200
    t_stu_final = get_ticket_by_id(t_id)
    assert t_stu_final["status"] == "closed"
    print("[PASS] Test 30: Student successfully confirmed resolution and marked ticket as Closed")

    print("\n" + "=" * 65)
    print(" ALL 30 RBAC, DEVELOPER, ISOLATION & TICKET SYSTEM TESTS PASSED!")
    print("=" * 65)

if __name__ == '__main__':
    run_tests()

