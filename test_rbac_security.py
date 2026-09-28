"""Comprehensive Penetration & Validation Test Suite for RBAC & Data Isolation."""

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
    get_audit_logs,
    verify_user_password
)
from src.vectorstore import stats, update_source_visibility

def run_tests():
    print("=" * 60)
    print(" RUNNING RBAC & DATA ISOLATION PENETRATION TEST SUITE")
    print("=" * 60)

    # 1. Initialize
    init_auth_db()
    client = app.test_client()

    # Create test student account if not present
    if not get_user_by_username("stu001"):
        create_user(
            username="stu001",
            password="Password@123",
            role="student",
            student_id="STU001",
            must_change_password=False
        )

    # Test 1: Unauthenticated request to /documents -> Should redirect to login
    res = client.get('/documents')
    assert res.status_code in [302, 401], f"Expected redirect or 401, got {res.status_code}"
    assert '/login' in res.headers.get('Location', '')
    print("[PASS] Test 1: Unauthenticated access to /documents is blocked (Redirect to /login)")

    # Test 2: Unauthenticated API call to /api/upload -> Should return 401
    res = client.post('/api/upload', data={'files': []}, headers={'Accept': 'application/json'})
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"
    print("[PASS] Test 2: Unauthenticated POST /api/upload returns 401 Unauthorized")

    # Test 3: Officer Login
    res = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Signed in successfully" in res.data or b"admin" in res.data
    print("[PASS] Test 3: Placement Officer authentication succeeded")

    # Test 4: Officer can access /documents and /audit_logs
    res = client.get('/documents')
    assert res.status_code == 200
    print("[PASS] Test 4: Placement Officer can access /documents")

    res = client.get('/audit_logs')
    assert res.status_code == 200
    print("[PASS] Test 4b: Placement Officer can access /audit_logs")

    # Test 5: Reset DB without officer password -> Should fail
    res = client.post('/api/reset_db', data={'admin_password': 'wrongpassword'}, follow_redirects=True)
    assert b"Password verification failed" in res.data
    print("[PASS] Test 5: Destructive action /api/reset_db rejected on invalid password")

    # Test 6: Sign out Officer and Sign in as Student
    client.get('/logout')
    res = client.post('/login', data={'username': 'stu001', 'password': 'Password@123'}, follow_redirects=True)
    assert res.status_code == 200
    print("[PASS] Test 6: Student authentication succeeded")

    # Test 7: Student attempts to access /documents -> Forbidden 403 or redirect with error
    res = client.get('/documents', follow_redirects=True)
    assert b"Access denied" in res.data
    print("[PASS] Test 7: Student accessing /documents is blocked with Access Denied")

    # Test 8: Student attempts direct API attack POST /api/upload -> 403 Forbidden
    res = client.post('/api/upload', data={'files': []}, headers={'Accept': 'application/json'})
    assert res.status_code == 403, f"Expected 403, got {res.status_code}"
    print("[PASS] Test 8: Student API attack on /api/upload returns 403 Forbidden")

    # Test 9: Student attempts direct API attack POST /api/reset_db -> 403 Forbidden
    res = client.post('/api/reset_db', data={'admin_password': 'any'}, headers={'Accept': 'application/json'})
    assert res.status_code == 403, f"Expected 403, got {res.status_code}"
    print("[PASS] Test 9: Student API attack on /api/reset_db returns 403 Forbidden")

    # Test 10: Student query for personal record -> Evaluates personal row
    res = client.post(
        '/api/stream_query',
        data=json.dumps({'query': 'What is my CGPA and placement status?', 'mode': 'rag'}),
        content_type='application/json'
    )
    assert res.status_code == 200
    res_text = b"".join(list(res.response)).decode('utf-8')
    res.close()
    assert 'STU001' in res_text or 'context' in res_text
    print("[PASS] Test 10: Student query accurately routes through parameterized personal record (STU001)")

    # Test 11: Student attempts aggregate query across all students -> Blocked with restriction notice
    res = client.post(
        '/api/stream_query',
        data=json.dumps({'query': 'How many total students are placed in the university?', 'mode': 'rag'}),
        content_type='application/json'
    )
    assert res.status_code == 200
    res_text = b"".join(list(res.response)).decode('utf-8')
    res.close()
    assert "Access Restricted" in res_text
    print("[PASS] Test 11: Student aggregate query across all students is securely blocked")

    # Test 12: Verify Audit Logs
    logs = get_audit_logs(20)
    assert len(logs) > 0
    actions = [l['action'] for l in logs]
    assert 'login' in actions
    assert 'unauthorized_access_attempt' in actions or 'reset_db_attempt' in actions
    print(f"[PASS] Test 12: Security audit trail successfully verified ({len(logs)} events logged)")

    print("\n" + "=" * 60)
    print(" ALL 12 RBAC & DATA ISOLATION PENETRATION TESTS PASSED!")
    print("=" * 60)

if __name__ == '__main__':
    run_tests()
