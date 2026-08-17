import sqlite3
import json
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

from pathlib import Path
from io import BytesIO
from src.ingest import extract_pages, chunk_pages, file_hash
from src.embeddings import embed_documents, embed_query
from src.vectorstore import reset_collection, add_chunks, search, stats

print("==================================================================")
print("  PREPARING OFFICIAL PILOT DOCUMENTATION SUITE FOR DEMO & TESTING")
print("==================================================================")

# 1. Reset vectorstore collection cleanly
reset_collection()
print("\n[+] Reset ChromaDB Vector Collection cleanly.")

# 2. Create/Verify Official Enterprise Policy Markdown Document
policy_path = Path('documents/Official_Enterprise_Policy.md')
policy_text = """# Official Enterprise Information Technology & Security Policy

## Document Control
- Document ID: POL-2026-SEC-09
- Version: 4.2
- Effective Date: January 1, 2026
- Classification: Confidential / Internal Only

---

## 1. Work From Home & Remote Access Policy
- All employee laptops accessing corporate networks must use dual-factor authentication (2FA).
- VPN connections automatically terminate after 8 hours of continuous session activity.
- The maximum allowable password age is 90 days. Passwords cannot be reused for 5 previous cycles.

## 2. Information Security & Data Protection
- Data classification levels are Public, Internal, Confidential, and Restricted.
- Customer Personal Identifiable Information (PII) must be encrypted both at rest (AES-256) and in transit (TLS 1.3).
- Data breaches must be reported to the Chief Information Security Officer (CISO) within 2 hours of discovery.

## 3. Travel & Reimbursement Policy
- Domestic business travel expenses must be submitted within 15 calendar days of trip completion.
- The maximum daily meal allowance for business travel is $75 USD per day.
- Hotel accommodation limit is capped at $200 USD per night for standard tier cities.
"""
policy_path.write_text(policy_text, encoding='utf-8')
print("[+] Created/Updated: Official_Enterprise_Policy.md")

# 3. Create/Verify SQL Database (company_records.db)
sql_path = Path('documents/company_records.db')
conn = sqlite3.connect(sql_path)
cur = conn.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS employees (id INT, name TEXT, department TEXT, salary INT, project TEXT);')
cur.execute('DELETE FROM employees;')
cur.execute("INSERT INTO employees VALUES (101, 'Rohan Sharma', 'AI Systems', 95000, 'TalentSphere');")
cur.execute("INSERT INTO employees VALUES (102, 'Ananya Patel', 'Cloud Architecture', 105000, 'Springboard');")
cur.execute("INSERT INTO employees VALUES (103, 'Vikram Malhotra', 'Data Science', 88000, 'Local Database QA');")
conn.commit()
conn.close()
print("[+] Created/Updated: company_records.db (SQL Relational DB)")

# 4. Create/Verify NoSQL Database (users_nosql.json)
nosql_path = Path('documents/users_nosql.json')
nosql_data = [
    {"user_id": "u_901", "username": "alex_dev", "role": "Lead Engineer", "access_level": "Admin", "status": "Active"},
    {"user_id": "u_902", "username": "priya_m", "role": "Product Manager", "access_level": "Standard", "status": "Active"},
    {"user_id": "u_903", "username": "sam_cloud", "role": "DevOps Specialist", "access_level": "Admin", "status": "Inactive"}
]
nosql_path.write_text(json.dumps(nosql_data, indent=2), encoding='utf-8')
print("[+] Created/Updated: users_nosql.json (NoSQL Document DB)")

# 5. Ingest ALL official documents in documents/ directory into ChromaDB
print("\n[+] Indexing all pilot source files into ChromaDB Vector Engine...")
doc_dir = Path('documents')
total_chunks_added = 0

for doc_file in doc_dir.iterdir():
    if doc_file.is_file():
        data = doc_file.read_bytes()
        digest = file_hash(data)
        pages = extract_pages(BytesIO(data), doc_file.name)
        chunks = chunk_pages(pages, doc_file.name)
        if chunks:
            embeds = embed_documents([c['text'] for c in chunks])
            added = add_chunks(chunks, embeds, digest)
            total_chunks_added += added
            print(f"    - Ingested '{doc_file.name}': {len(pages)} pages/tables -> {added} vector chunks")

st = stats()
print("\n==================================================================")
print(f"  PILOT SUITE READY! Total Indexed Documents: {st['sources']} | Chunks: {st['total_chunks']}")
print("==================================================================")
