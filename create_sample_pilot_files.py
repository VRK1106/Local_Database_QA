import sqlite3
import json
import pandas as pd
from pathlib import Path

sample_dir = Path('sample_pilot_documents')
sample_dir.mkdir(parents=True, exist_ok=True)

# 1. Enterprise Security Policy Markdown
policy_path = sample_dir / 'Official_Enterprise_Policy.md'
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

# 2. SQLite Database
sql_path = sample_dir / 'company_records.db'
conn = sqlite3.connect(sql_path)
cur = conn.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS employees (id INT, name TEXT, department TEXT, salary INT, project TEXT);')
cur.execute('DELETE FROM employees;')
cur.execute("INSERT INTO employees VALUES (101, 'Rohan Sharma', 'AI Systems', 95000, 'TalentSphere');")
cur.execute("INSERT INTO employees VALUES (102, 'Ananya Patel', 'Cloud Architecture', 105000, 'Springboard');")
cur.execute("INSERT INTO employees VALUES (103, 'Vikram Malhotra', 'Data Science', 88000, 'Local Database QA');")
conn.commit()
conn.close()

# 3. NoSQL JSON Profile Collection
nosql_path = sample_dir / 'users_nosql.json'
nosql_data = [
    {"user_id": "u_901", "username": "alex_dev", "role": "Lead Engineer", "access_level": "Admin", "status": "Active"},
    {"user_id": "u_902", "username": "priya_m", "role": "Product Manager", "access_level": "Standard", "status": "Active"},
    {"user_id": "u_903", "username": "sam_cloud", "role": "DevOps Specialist", "access_level": "Admin", "status": "Inactive"}
]
nosql_path.write_text(json.dumps(nosql_data, indent=2), encoding='utf-8')

# 4. Excel Training Venue Schedule
xlsx_path = sample_dir / 'Training_Venue_Schedule.xlsx'
departments = ['AD', 'AD', 'CSE', 'CSE', 'ML', 'ECE']
venues = ['III AD Classroom A', 'III AD Classroom B', 'III CSE A Classroom', 'CC LAB', 'HPC LAB', 'NMS LAB']
rows = []
for i in range(1, 61):
    dept = departments[i % len(departments)]
    venue = venues[i % len(venues)]
    rows.append({
        'slNo': i,
        'Name': f'Student_{i}',
        'Roll No': f'24{dept}{i:03d}',
        'Dept': dept,
        'Mobile': f'987654{i:04d}',
        'Mail ID': f'student{i}@kpriet.ac.in',
        'Venue': venue
    })
df = pd.DataFrame(rows)
df.to_excel(xlsx_path, index=False)

print('Sample pilot files generated successfully in sample_pilot_documents/')
