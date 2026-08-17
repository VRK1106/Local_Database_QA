import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

from pathlib import Path
from io import BytesIO
from src.ingest import extract_pages, chunk_pages, file_hash
from src.embeddings import embed_documents, embed_query
from src.vectorstore import reset_collection, add_chunks, search
from src.ollama_client import generate_ollama_answer, build_rag_prompt

# Read Excel file
data = Path('documents/III Year Training Venue.xlsx').read_bytes()
digest = file_hash(data)
pages = extract_pages(BytesIO(data), 'III Year Training Venue.xlsx')

def smart_chunk_pages(pages: list[dict], source_name: str, chunk_size: int = 400, chunk_overlap: int = 50) -> list[dict]:
    chunks = []
    chunk_counter = 0

    for page_info in pages:
        page_num = page_info["page"]
        text = page_info["text"]
        
        # Check if text contains a structured header section
        header_prefix = ""
        body_text = text
        if "=== Detailed Records ===" in text:
            parts = text.split("=== Detailed Records ===")
            header_prefix = parts[0].strip() + "\n=== Detailed Records ===\n"
            body_text = parts[1].strip()
        elif "\nRow #" in text:
            lines = text.split("\nRow #")[0]
            header_prefix = lines.strip() + "\n"
            body_text = text[len(lines):].strip()

        words = body_text.split()
        prefix_words = header_prefix.split() if header_prefix else []
        effective_chunk_size = max(100, chunk_size - len(prefix_words))
        step = max(50, effective_chunk_size - chunk_overlap)

        if len(words) <= effective_chunk_size:
            chunk_text = (header_prefix + body_text).strip()
            chunks.append({
                "id": f"{source_name}_p{page_num}_c{chunk_counter}",
                "text": chunk_text,
                "metadata": {"source": source_name, "page": page_num, "chunk_index": chunk_counter}
            })
            chunk_counter += 1
        else:
            for i in range(0, len(words), step):
                chunk_words = words[i:i + effective_chunk_size]
                if not chunk_words:
                    continue
                sub_body = " ".join(chunk_words)
                chunk_text = (header_prefix + sub_body).strip()
                chunks.append({
                    "id": f"{source_name}_p{page_num}_c{chunk_counter}",
                    "text": chunk_text,
                    "metadata": {"source": source_name, "page": page_num, "chunk_index": chunk_counter}
                })
                chunk_counter += 1

    return chunks

chunks = smart_chunk_pages(pages, 'III Year Training Venue.xlsx')

# Index into ChromaDB
reset_collection()
embeds = embed_documents([c['text'] for c in chunks])
add_chunks(chunks, embeds, digest)

# Perform Test Query
q = "How many students are assigned to the CC Lab?"
emb = embed_query(q)
res = search(emb, top_k=3, source_filters=['III Year Training Venue.xlsx'])

print(f"\n==================================================")
print(f"Query: '{q}'")
print(f"Retrieved {len(res)} chunks.")
for r in res:
    print(f"Match [{r['chunk_id']}]: {r['text'][:200]}...\n")

rag_prompt = build_rag_prompt(q, res)
ans = generate_ollama_answer(rag_prompt, "qwen2.5-coder")
print("==================================================")
print(f"AI Response:\n{ans}")
print("==================================================")
