#!/usr/bin/env python3
"""
Live end-to-end workflow check against the running Docker stack (backend + PostgreSQL + ChromaDB + Ollama).

Exercises every persona through the real HTTP API, including LLM-generated answers:
  - student: own profile, eligibility, public circular RAG, peer/aggregate blocking
  - placement: SQL aggregates, internal memo RAG, document upload / visibility / delete
  - developer: View-As impersonation, system pages
  - shared: tickets (create / reply / status), trust-layer verification, page RBAC

Side effects are cleaned up: the uploaded test document is deleted and the test ticket is closed.

Usage:
    python test_resources/e2e_live_workflow.py [--base-url http://127.0.0.1:5000]
"""

import argparse
import json
import re
import sys
import time

import requests

USERS = {
    "student": ("stu001", "Password@123"),
    "placement": ("admin", "admin123"),
    "developer": ("dev_admin", "DeveloperPass@1234"),
}
TEST_DOC = "e2e_public_notice_test.txt"
TEST_FACT = "The E2E mock hackathon will be held in Hall Zeta-9 on campus."


class Runner:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.passed = 0
        self.failed = []

    def check(self, name, cond, detail=""):
        if cond:
            self.passed += 1
            print(f"  [PASS] {name}")
        else:
            self.failed.append(name)
            print(f"  [FAIL] {name}\n         -> {detail[:400]}")

    def login(self, role):
        s = requests.Session()
        user, pwd = USERS[role]
        r = s.post(f"{self.base}/login", data={"username": user, "password": pwd})
        return s, r

    def ask(self, s, query, **kw):
        t0 = time.time()
        r = s.post(f"{self.base}/api/stream_query", json={"query": query, "mode": "rag", **kw}, stream=True, timeout=300)
        answer, context, errors, verified = "", {}, [], None
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            d = json.loads(line[5:].strip())
            if "token" in d:
                answer += d["token"]
            if d.get("type") == "context":
                context = d
            if d.get("type") == "verification":
                verified = d.get("result")
            if "error" in d:
                errors.append(d["error"])
        return {"answer": answer.strip(), "context": context, "errors": errors,
                "verified": verified, "status": r.status_code, "secs": round(time.time() - t0, 1)}


def has(text, *needles):
    low = text.lower()
    return all(n.lower() in low for n in needles)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:5000")
    R = Runner(ap.parse_args().base_url)

    print("\n== Health & authentication")
    R.check("health endpoint", requests.get(f"{R.base}/health").status_code == 200)
    sessions = {}
    for role in USERS:
        s, r = R.login(role)
        sessions[role] = s
        R.check(f"{role} login lands on QA studio", r.status_code == 200 and r.url.rstrip("/") == R.base, r.url)
    bad = requests.post(f"{R.base}/login", data={"username": "stu001", "password": "wrong"})
    R.check("wrong password rejected", "/login" in bad.url)
    R.check("unauthenticated query rejected",
            requests.post(f"{R.base}/api/stream_query", json={"query": "hi"}, allow_redirects=False).status_code in (302, 401))

    stu, plc, dev = sessions["student"], sessions["placement"], sessions["developer"]

    print("\n== Student queries")
    r = R.ask(stu, "What is my CGPA?")
    R.check("own CGPA answered instantly from registry", has(r["answer"], "8.2", "STU001") and r["verified"], r["answer"])
    r = R.ask(stu, "What is the dress code for the interview?")
    R.check("dress code answered from circular (not canned profile)",
            has(r["answer"], "formal") and "Cumulative GPA" not in r["answer"], r["answer"])
    r = R.ask(stu, "What is the last date to register for the placement drive?")
    R.check("registration deadline not blocked as aggregate", has(r["answer"], "october 20") and "Access Restricted" not in r["answer"], r["answer"])
    r = R.ask(stu, "What is the CTC offered by Apex?")
    R.check("CTC answered from public circular", re.search(r"12(,00,000| ?lpa)", r["answer"].lower()) is not None, r["answer"])
    r = R.ask(stu, "Am I eligible for the Apex drive?")
    R.check("eligibility uses own record + circular", has(r["answer"], "7.5") and not r["errors"], r["answer"])
    R.check("eligibility answer sends real context for trust verification",
            any("Verified student record" in t for t in r["context"].get("context_texts", [])), str(r["context"])[:300])
    for q in ("How many students are placed?", "Who has the highest CGPA?", "What is Priya Sharma's CGPA?", "Show STU002 record"):
        r = R.ask(stu, q)
        R.check(f"blocked: {q}", "Access Restricted" in r["answer"] and "9.1" not in r["answer"], r["answer"])
    r = R.ask(stu, "What is the placement strategy in the internal memo?")
    R.check("internal memo never reaches students",
            not any(c.get("source", "").startswith("sample_internal") for c in r["context"].get("citations", []))
            and "Room 204" not in r["answer"], r["answer"])

    print("\n== Placement officer queries")
    r = R.ask(plc, "How many students have CGPA above 8?")
    R.check("SQL aggregate answered", re.search(r"\d+", r["answer"]) is not None and r["verified"], r["answer"])
    r = R.ask(plc, "Who has the highest CGPA?")
    R.check("SQL superlative answered", has(r["answer"], "rahul verma"), r["answer"])
    r = R.ask(plc, "What is the placement strategy in the internal memo?")
    R.check("internal memo visible to officers",
            any(c.get("source", "").startswith("sample_internal") for c in r["context"].get("citations", [])), str(r["context"])[:300])

    print("\n== Trust layer")
    t = plc.post(f"{R.base}/api/verify_trust", timeout=300, json={
        "answer": "The minimum CGPA is 7.50. The CTC is 50 LPA.",
        "context_texts": ["Academic Threshold: Minimum CGPA of 7.50 with no active backlogs. CTC: INR 12,00,000 per annum."]})
    ok = t.status_code == 200 and "claims" in t.json()
    R.check("verify_trust returns claim verdicts", ok, t.text[:300])
    if ok:
        statuses = [c["status"] for c in t.json()["claims"]]
        R.check("true claim entailed, false claim not entailed",
                statuses and statuses[0] == "entailment" and statuses[-1] != "entailment", str(t.json()))

    print("\n== Document lifecycle (upload -> student visibility -> internal -> delete)")
    up = plc.post(f"{R.base}/api/upload", data={"visibility": "public"},
                  files={"files": (TEST_DOC, TEST_FACT.encode(), "text/plain")},
                  headers={"Accept": "application/json"}, timeout=300)
    R.check("upload streams completion", '"status": "done"' in up.text and '"indexed": 1' in up.text, up.text[-300:])
    r = R.ask(stu, "Where will the E2E mock hackathon be held?", sources=[TEST_DOC])
    R.check("student can query a newly public document", has(r["answer"], "zeta-9"), r["answer"])
    R.check("student can open public document file",
            stu.get(f"{R.base}/documents/view/{TEST_DOC}").status_code == 200)
    plc.post(f"{R.base}/api/update_doc_visibility", data={"source_name": TEST_DOC, "new_visibility": "internal"})
    r = R.ask(stu, "Where will the E2E mock hackathon be held?", sources=[TEST_DOC])
    R.check("student loses access after doc set internal", "zeta-9" not in r["answer"].lower(), r["answer"])
    R.check("student blocked from internal document file",
            stu.get(f"{R.base}/documents/view/{TEST_DOC}").status_code == 403)
    plc.post(f"{R.base}/api/delete_doc", data={"source_name": TEST_DOC})
    docs = plc.get(f"{R.base}/documents").text
    R.check("deleted document removed", TEST_DOC not in docs)
    R.check("student cannot upload", stu.post(f"{R.base}/api/upload", files={"files": ("x.txt", b"x")},
                                              headers={"Accept": "application/json"}).status_code == 403)

    print("\n== Tickets")
    title = f"[E2E] CGPA record check {int(time.time())}"
    stu.post(f"{R.base}/tickets/create", data={"title": title, "category": "academic_record",
                                               "priority": "low", "description": "Automated workflow test ticket."})
    listing = plc.get(f"{R.base}/tickets").text
    m = re.search(r'/tickets/(\d+)[^<]{0,400}?' + re.escape(title), listing, re.S) or \
        re.search(re.escape(title) + r'.{0,2000}?/tickets/(\d+)', listing, re.S)
    R.check("student ticket reaches placement queue", m is not None, "ticket not found in /tickets")
    if m:
        tid = m.group(1)
        plc.post(f"{R.base}/tickets/{tid}/reply", data={"message": "E2E reply from placement."})
        R.check("placement reply visible to student", "E2E reply from placement." in stu.get(f"{R.base}/tickets/{tid}").text)
        plc.post(f"{R.base}/tickets/{tid}/status", data={"status": "closed", "resolution_notes": "E2E cleanup"})
        R.check("ticket closed", "closed" in plc.get(f"{R.base}/tickets/{tid}").text.lower())
        R.check("developer cannot be locked out of ticket", dev.get(f"{R.base}/tickets/{tid}").status_code in (200, 302))

    print("\n== Developer View-As impersonation")
    dev.post(f"{R.base}/dev/view_as", data={"role": "student", "student_id": "STU001"})
    r = R.ask(dev, "What is my CGPA?")
    R.check("view-as student gets student-scoped answer", has(r["answer"], "8.2"), r["answer"])
    r = R.ask(dev, "How many students are placed?")
    R.check("view-as student is blocked from aggregates", "Access Restricted" in r["answer"], r["answer"])
    dev.post(f"{R.base}/dev/view_as/stop")
    r = R.ask(dev, "How many students have CGPA above 8?")
    R.check("developer scope restored after stop", "Access Restricted" not in r["answer"], r["answer"])

    print("\n== Page access control")
    matrix = {
        "student": {"/profile": 200, "/tickets": 200, "/documents": 302, "/admin/students": 302, "/dev/dashboard": 302},
        "placement": {"/documents": 200, "/admin/students": 200, "/admin/users": 200, "/audit_logs": 200, "/dev/dashboard": 302},
        "developer": {"/dev/dashboard": 200, "/dev/users": 200, "/dev/config": 200, "/system_info": 200, "/documents": 200},
    }
    for role, pages in matrix.items():
        for path, code in pages.items():
            got = sessions[role].get(f"{R.base}{path}", allow_redirects=False).status_code
            R.check(f"{role} {path} -> {code}", got == code, f"got {got}")
    prof = stu.get(f"{R.base}/profile").text
    R.check("student profile shows own record", "Aarav Patel" in prof and "Priya Sharma" not in prof)

    print(f"\n== RESULT: {R.passed} passed, {len(R.failed)} failed")
    for name in R.failed:
        print(f"   - {name}")
    sys.exit(1 if R.failed else 0)


if __name__ == "__main__":
    main()
