import sys
import json
import time
import requests

BASE_URL = "http://localhost:5000"

def log_test(name, success, details=""):
    symbol = "[PASS]" if success else "[FAIL]"
    print(f"{symbol} [{name}]: {details}")
    return success

def run_tests():
    print("=" * 75)
    print("AUTOMATED DEEP END-TO-END SYSTEM ASSESSMENT FOR INDUSTRY DEMO")
    print("=" * 75)
    
    results = []

    # 1. Health Endpoint
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        h_data = r.json()
        s = log_test("Health Check", r.status_code == 200 and h_data.get("status") == "healthy", f"Status: {h_data.get('status')}")
        results.append(s)
    except Exception as e:
        results.append(log_test("Health Check", False, str(e)))

    # 2. Authentication Test - All 3 Roles
    roles = [
        ("Student (stu001)", "stu001", "Password@123", "student"),
        ("Placement Officer (admin)", "admin", "admin123", "placement"),
        ("Developer (dev_admin)", "dev_admin", "DeveloperPass@1234", "developer")
    ]
    sessions = {}
    for label, uname, pwd, expected_role in roles:
        s = requests.Session()
        r = s.post(f"{BASE_URL}/login", data={"username": uname, "password": pwd}, allow_redirects=True)
        success = (r.status_code == 200 and "/login" not in r.url and "Login" not in r.text)
        sessions[expected_role] = s
        results.append(log_test(f"Auth - {label}", success, f"URL: {r.url}"))

    stu_s = sessions.get("student")
    plc_s = sessions.get("placement")
    dev_s = sessions.get("developer")

    # 3. Role-Based Access Control (RBAC) Security Verification
    r_dev = stu_s.get(f"{BASE_URL}/dev/dashboard", allow_redirects=False)
    stu_dev_blocked = (r_dev.status_code == 302 and r_dev.headers.get("Location") in ["/", "/login"])
    results.append(log_test("RBAC Security: Student blocked from Dev Dashboard", stu_dev_blocked, f"Status: {r_dev.status_code} Redirect: {r_dev.headers.get('Location')}"))

    r_admin = stu_s.get(f"{BASE_URL}/admin/students", allow_redirects=False)
    stu_admin_blocked = (r_admin.status_code == 302 and r_admin.headers.get("Location") in ["/", "/login"])
    results.append(log_test("RBAC Security: Student blocked from Admin Student Management", stu_admin_blocked, f"Status: {r_admin.status_code} Redirect: {r_admin.headers.get('Location')}"))

    r_plc_dev = plc_s.get(f"{BASE_URL}/dev/dashboard", allow_redirects=False)
    plc_dev_blocked = (r_plc_dev.status_code == 302)
    results.append(log_test("RBAC Security: Placement Officer blocked from Dev Console", plc_dev_blocked, f"Status: {r_plc_dev.status_code}"))

    r_plc_stu = plc_s.get(f"{BASE_URL}/admin/students")
    plc_ok = (r_plc_stu.status_code == 200 and "Student Records" in r_plc_stu.text)
    results.append(log_test("RBAC: Placement Officer access to Student Records", plc_ok, f"Status: {r_plc_stu.status_code}"))

    r_dev_ok = dev_s.get(f"{BASE_URL}/dev/dashboard")
    dev_allowed = (r_dev_ok.status_code == 200 and "Developer Control Center" in r_dev_ok.text)
    results.append(log_test("RBAC: Developer access to Dev Console", dev_allowed, f"Status: {r_dev_ok.status_code}"))

    # 4. Student Instant Personal Profile Queries (Structured Query Pipeline)
    t0 = time.time()
    r_cgpa = stu_s.post(f"{BASE_URL}/api/stream_query", json={"query": "What is my cgpa?", "mode": "rag", "model": "qwen2.5-coder:latest"}, stream=True)
    body_cgpa = ""
    for line in r_cgpa.iter_lines():
        if line:
            l = line.decode('utf-8')
            if l.startswith("data:"):
                try:
                    d = json.loads(l[5:].strip())
                    if "token" in d:
                        body_cgpa += d["token"]
                except:
                    pass
    cgpa_time = time.time() - t0
    cgpa_success = ("8.2" in body_cgpa) and (cgpa_time < 3.0)
    results.append(log_test("Student Query: Deterministic CGPA Lookup", cgpa_success, f"Time: {cgpa_time:.3f}s | Output: {body_cgpa[:55]}..."))

    t0 = time.time()
    r_stat = stu_s.post(f"{BASE_URL}/api/stream_query", json={"query": "Am I placed?", "mode": "rag", "model": "qwen2.5-coder:latest"}, stream=True)
    body_stat = ""
    for line in r_stat.iter_lines():
        if line:
            l = line.decode('utf-8')
            if l.startswith("data:"):
                try:
                    d = json.loads(l[5:].strip())
                    if "token" in d:
                        body_stat += d["token"]
                except:
                    pass
    stat_time = time.time() - t0
    stat_success = ("Not Placed" in body_stat or "not placed" in body_stat.lower())
    results.append(log_test("Student Query: Placement Status", stat_success, f"Time: {stat_time:.3f}s | Output: {body_stat[:55]}..."))

    # 5. Placement Officer Document RAG Pipeline & Stream Query
    t0 = time.time()
    r_rag = plc_s.post(f"{BASE_URL}/api/stream_query", json={"query": "What are the eligibility criteria and rules for placement drives?", "mode": "rag", "model": "qwen2.5-coder:latest", "top_k": 3}, stream=True)
    rag_tokens = []
    rag_citations = []
    for line in r_rag.iter_lines():
        if line:
            l = line.decode('utf-8')
            if l.startswith("data:"):
                try:
                    d = json.loads(l[5:].strip())
                    if "token" in d:
                        rag_tokens.append(d["token"])
                    if d.get("type") == "context":
                        rag_citations = d.get("citations", [])
                except:
                    pass
    rag_time = time.time() - t0
    rag_text = "".join(rag_tokens)
    rag_success = len(rag_text) > 20 and len(rag_citations) > 0
    results.append(log_test("RAG Pipeline: Search + Context + LLM Stream", rag_success, f"Time: {rag_time:.2f}s | Citations: {len(rag_citations)} | Generated Tokens: {len(rag_tokens)}"))

    # 6. Search-Only Pipeline (Vector Retrieval Mode)
    t0 = time.time()
    r_search = plc_s.post(f"{BASE_URL}/api/stream_query", json={"query": "training venue schedule", "mode": "search_only"}, stream=True)
    search_tokens = []
    for line in r_search.iter_lines():
        if line:
            l = line.decode('utf-8')
            if l.startswith("data:"):
                try:
                    d = json.loads(l[5:].strip())
                    if "token" in d:
                        search_tokens.append(d["token"])
                except:
                    pass
    search_time = time.time() - t0
    search_output = "".join(search_tokens)
    search_ok = ("Vector" in search_output or "Match" in search_output) and (search_time < 2.0)
    results.append(log_test("Search-Only Pipeline: k-NN Vector Retrieval", search_ok, f"Time: {search_time:.3f}s | Length: {len(search_output)} chars"))

    # 7. Trust & Verification Layer (NLI / Faithfulness)
    try:
        sample_context = ["Students with CGPA above 7.0 and zero standing backlogs are eligible for Tier-1 drives."]
        sample_ans = "According to placement guidelines, students with CGPA >= 7.0 and no active backlogs can attend Tier-1 drives."
        r_trust = plc_s.post(f"{BASE_URL}/api/verify_trust", json={"answer": sample_ans, "context_texts": sample_context})
        t_data = r_trust.json()
        trust_ok = (r_trust.status_code == 200 and "score" in t_data)
        results.append(log_test("Trust Verification Pipeline (NLI)", trust_ok, f"Score: {t_data.get('score')}% | Claims: {len(t_data.get('claims', []))}"))
    except Exception as e:
        results.append(log_test("Trust Verification Pipeline (NLI)", False, str(e)))

    # 8. Voice Typing API Endpoints
    try:
        r_voice_start = plc_s.post(f"{BASE_URL}/api/trigger_voice_typing")
        v_start_data = r_voice_start.json()
        r_voice_stop = plc_s.post(f"{BASE_URL}/api/stop_voice_typing")
        v_stop_data = r_voice_stop.json()
        v_ok = (r_voice_start.status_code == 200 and r_voice_stop.status_code == 200 and v_start_data.get("status") == "success")
        results.append(log_test("Voice Typing API Endpoints", v_ok, f"Start: {v_start_data.get('status')} | Stop: {v_stop_data.get('status')}"))
    except Exception as e:
        results.append(log_test("Voice Typing API Endpoints", False, str(e)))

    # 9. Support Ticket System Pipeline
    try:
        t_payload = {
            "title": "Audit Test Ticket - Interview Query",
            "category": "placement_drive",
            "priority": "normal",
            "target_role": "placement",
            "description": "Verification of interview slots for campus drive."
        }
        r_t_create = stu_s.post(f"{BASE_URL}/tickets/create", data=t_payload, allow_redirects=True)
        t_create_ok = (r_t_create.status_code == 200 and "Audit Test Ticket" in r_t_create.text)
        results.append(log_test("Ticketing: Student Create Ticket", t_create_ok, f"Status: {r_t_create.status_code}"))

        r_t_plc = plc_s.get(f"{BASE_URL}/tickets")
        plc_ticket_view = (r_t_plc.status_code == 200 and "Audit Test Ticket" in r_t_plc.text)
        results.append(log_test("Ticketing: Placement Officer View Tickets", plc_ticket_view, f"Status: {r_t_plc.status_code}"))
    except Exception as e:
        results.append(log_test("Ticketing Workflow", False, str(e)))

    # 10. Document Scope Isolation (Internal vs Public)
    try:
        r_stu_memo = stu_s.post(f"{BASE_URL}/api/stream_query", json={"query": "Show me the internal confidential strategy memo", "mode": "rag", "model": "qwen2.5-coder:latest"}, stream=True)
        stu_memo_citations = []
        for line in r_stu_memo.iter_lines():
            if line:
                l = line.decode('utf-8')
                if l.startswith("data:"):
                    try:
                        d = json.loads(l[5:].strip())
                        if d.get("type") == "context":
                            stu_memo_citations = d.get("citations", [])
                    except:
                        pass
        internal_leaked = any("internal" in str(c.get("source", "")).lower() for c in stu_memo_citations)
        results.append(log_test("Data Isolation: Internal Docs Hidden from Students", not internal_leaked, f"Internal citations leaked: {internal_leaked}"))
    except Exception as e:
        results.append(log_test("Data Isolation: Internal Docs Hidden from Students", False, str(e)))

    # 11. Developer Impersonation ("View As") Feature
    try:
        r_view_as = dev_s.post(f"{BASE_URL}/dev/view_as", data={"role": "student", "student_id": "STU001"}, allow_redirects=True)
        view_as_ok = (r_view_as.status_code == 200 and "Student" in r_view_as.text)
        results.append(log_test("Developer Tools: 'View As' Impersonation", view_as_ok, f"Status: {r_view_as.status_code}"))
        dev_s.get(f"{BASE_URL}/dev/view_as/stop", allow_redirects=True)
    except Exception as e:
        results.append(log_test("Developer Tools: 'View As' Impersonation", False, str(e)))

    print("=" * 75)
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r)
    print(f"OVERALL SUMMARY: {passed_tests}/{total_tests} Tests Passed ({passed_tests/total_tests*100:.1f}%)")
    print("=" * 75)

if __name__ == "__main__":
    run_tests()
