import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

from src.embeddings import embed_query
from src.vectorstore import search
from src.ollama_client import generate_ollama_answer, build_rag_prompt

queries = [
    ("SQL Database", "company_records.db", "Which employee works in AI Systems and what is their salary?"),
    ("NoSQL Database", "users_nosql.json", "Who has Lead Engineer role and what is their access level?"),
    ("Corporate Policy", "Official_Enterprise_Policy.md", "What is the maximum daily meal allowance for business travel?")
]

print("==================================================================")
print("  VERIFYING PILOT DEMO TEST QUERIES")
print("==================================================================")

for label, doc, q in queries:
    emb = embed_query(q)
    chunks = search(emb, top_k=2, source_filters=[doc] if doc else None)
    print(f"\n--- [{label}] Source Filter: {doc} ---")
    print(f"Query: '{q}'")
    print(f"Retrieved {len(chunks)} chunks:")
    for c in chunks:
        print(f"  > [{c['source']}]: {c['text'][:100]}...")
    
    rag_prompt = build_rag_prompt(q, chunks)
    ans = generate_ollama_answer(rag_prompt, "qwen2.5-coder")
    print(f"AI Answer:\n{ans}\n")
