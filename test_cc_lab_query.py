import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

from pathlib import Path
from io import BytesIO
import pandas as pd
import sqlite3
import tempfile
from src.ingest import extract_pages, chunk_pages, file_hash
from src.embeddings import embed_documents, embed_query
from src.vectorstore import reset_collection, add_chunks, search
from src.ollama_client import generate_ollama_answer, build_rag_prompt

def test_dual_path():
    print("==================================================")
    print("   TESTING DUAL-PATH EXCEL ROUTING & RETRIEVAL")
    print("==================================================")
    
    # 1. Prepare Data
    file_path = Path('sample_pilot_documents/Training_Venue_Schedule.xlsx')
    if not file_path.exists():
        print(f"Test file {file_path} not found.")
        return
        
    data = file_path.read_bytes()
    digest = file_hash(data)
    pages = extract_pages(BytesIO(data), file_path.name)
    chunks = chunk_pages(pages, file_path.name)
    
    print(f"\n[+] Extracted {len(pages)} pages and {len(chunks)} row-aware semantic chunks.")
    print(f"Sample Chunk 0:\n{chunks[0]['text'][:300]}...\n")
    
    reset_collection()
    embeds = embed_documents([c['text'] for c in chunks])
    add_chunks(chunks, embeds, digest)
    
    # 2. Test Semantic RAG Path
    q_semantic = "Which department is Student_12 in and what is their venue?"
    print(f"\n--- SEMANTIC RAG PATH ---")
    print(f"Query: '{q_semantic}'")
    emb = embed_query(q_semantic)
    res = search(emb, top_k=2)
    print(f"Retrieved Context:")
    for r in res:
        print(f"  -> {r['text'][:150]}...")
    
    rag_prompt = build_rag_prompt(q_semantic, res)
    ans_semantic = generate_ollama_answer(rag_prompt, "qwen2.5-coder")
    print(f"AI Answer:\n{ans_semantic}")
    
    # 3. Test Universal Structured Query Path
    q_structured = "How many students are assigned to the CC LAB?"
    print(f"\n--- UNIVERSAL STRUCTURED SQL PATH ---")
    print(f"Query: '{q_structured}'")
    
    from src.structured_query import execute_universal_structured_query
    final_prompt, sql_query, sql_result, citations = execute_universal_structured_query(
        query=q_structured,
        documents_dir=Path('sample_pilot_documents'),
        selected_sources=None,
        model_name="qwen2.5-coder"
    )
    
    print(f"Generated SQL: {sql_query}")
    print(f"SQL Result: {sql_result}")
    if final_prompt:
        ans_structured = generate_ollama_answer(final_prompt, "qwen2.5-coder")
        print(f"AI Answer:\n{ans_structured}")

if __name__ == '__main__':
    test_dual_path()
