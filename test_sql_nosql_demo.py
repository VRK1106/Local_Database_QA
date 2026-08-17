import sqlite3
import json
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

from pathlib import Path
from io import BytesIO
from src.ingest import extract_pages, chunk_pages, file_hash
from src.embeddings import embed_documents, embed_query
from src.vectorstore import add_chunks, search

print("=== 1. CREATING SAMPLE SQL DATABASE (company_records.db) ===")
db_path = Path('documents/company_records.db')
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS employees (id INT, name TEXT, department TEXT, salary INT, project TEXT);')
cur.execute('DELETE FROM employees;')
cur.execute("INSERT INTO employees VALUES (101, 'Rohan Sharma', 'AI Systems', 95000, 'TalentSphere');")
cur.execute("INSERT INTO employees VALUES (102, 'Ananya Patel', 'Cloud Architecture', 105000, 'Springboard');")
cur.execute("INSERT INTO employees VALUES (103, 'Vikram Malhotra', 'Data Science', 88000, 'Local Database QA');")
conn.commit()
conn.close()
print("SQL Database created successfully with table 'employees'!")

print("\n=== 2. CREATING SAMPLE NoSQL DATABASE (users_nosql.json) ===")
nosql_path = Path('documents/users_nosql.json')
nosql_data = [
    {"user_id": "u_901", "username": "alex_dev", "role": "Lead Engineer", "access_level": "Admin", "status": "Active"},
    {"user_id": "u_902", "username": "priya_m", "role": "Product Manager", "access_level": "Standard", "status": "Active"},
    {"user_id": "u_903", "username": "sam_cloud", "role": "DevOps Specialist", "access_level": "Admin", "status": "Inactive"}
]
nosql_path.write_text(json.dumps(nosql_data, indent=2))
print("NoSQL Document Store created successfully with 3 user documents!")

print("\n=== 3. INGESTING SQL DATABASE INTO VECTOR ENGINE ===")
db_bytes = db_path.read_bytes()
db_pages = extract_pages(BytesIO(db_bytes), db_path.name)
db_chunks = chunk_pages(db_pages, db_path.name)
db_embeds = embed_documents([c['text'] for c in db_chunks])
added_sql = add_chunks(db_chunks, db_embeds, file_hash(db_bytes))
print(f"Added {added_sql} SQL database chunks!")

print("\n=== 4. INGESTING NoSQL DATABASE INTO VECTOR ENGINE ===")
nosql_bytes = nosql_path.read_bytes()
nosql_pages = extract_pages(BytesIO(nosql_bytes), nosql_path.name)
nosql_chunks = chunk_pages(nosql_pages, nosql_path.name)
nosql_embeds = embed_documents([c['text'] for c in nosql_chunks])
added_nosql = add_chunks(nosql_chunks, nosql_embeds, file_hash(nosql_bytes))
print(f"Added {added_nosql} NoSQL document chunks!")

print("\n=== 5. TESTING QUERY RETRIEVAL ON SQL DATABASE ===")
q1 = 'Which employee works in Data Science and what project are they on?'
h1 = search(embed_query(q1), top_k=1, source_filters=['company_records.db'])
if h1:
    print(f"Hit Source: {h1[0]['source']} (Score: {h1[0]['score']})")
    print(f"Text Content:\n{h1[0]['text']}")
else:
    print("No hit found for SQL query.")

print("\n=== 6. TESTING QUERY RETRIEVAL ON NoSQL DATABASE ===")
q2 = 'What is the user role for alex_dev in NoSQL?'
h2 = search(embed_query(q2), top_k=1, source_filters=['users_nosql.json'])
if h2:
    print(f"Hit Source: {h2[0]['source']} (Score: {h2[0]['score']})")
    print(f"Text Content:\n{h2[0]['text']}")
else:
    print("No hit found for NoSQL query.")
