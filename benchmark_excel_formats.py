import os
import time
import json
from io import BytesIO, StringIO
from pathlib import Path

# Silence TF / Google warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import pandas as pd
import openpyxl

from src.ingest import extract_pages, chunk_pages, file_hash
from src.embeddings import embed_documents, embed_query
from src.vectorstore import reset_collection, add_chunks, search
from src.ollama_client import generate_ollama_answer, build_rag_prompt

def run_benchmark():
    xlsx_files = list(Path('.').rglob('*.xlsx')) + list(Path('documents').rglob('*.xlsx'))
    if not xlsx_files:
        print("No Excel files found for benchmark. Creating a sample synthetic benchmark Excel sheet...")
        sample_path = Path('documents/III_Year_Training_Venue_Benchmark.xlsx')
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Build synthetic multi-department training venue sheet
        departments = ['AD', 'CSE', 'ML', 'ECE', 'MECH']
        venues = ['III AD Classroom A', 'III AD Classroom B', 'III CSE A Classroom', 'CC LAB', 'HPC LAB']
        rows = []
        for i in range(1, 201):
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
        df.to_excel(sample_path, index=False)
        xlsx_files = [sample_path]

    xlsx_path = xlsx_files[0]
    print(f"=== BENCHMARKING EXCEL EMBEDDING FORMATS USING: {xlsx_path.name} ===")
    raw_bytes = xlsx_path.read_bytes()

    results = {}

    # -------------------------------------------------------------
    # FORMAT 1: CSV Preprocessing Conversion (.xlsx -> .csv)
    # -------------------------------------------------------------
    t0 = time.time()
    excel_file = pd.ExcelFile(BytesIO(raw_bytes))
    csv_pages = []
    for idx, sheet_name in enumerate(excel_file.sheet_names, start=1):
        df_sheet = pd.read_excel(excel_file, sheet_name=sheet_name).dropna(how='all')
        csv_buffer = StringIO()
        df_sheet.to_csv(csv_buffer, index=False)
        csv_text = f"[CSV Dataset: {xlsx_path.name} | Sheet: {sheet_name}]\n" + csv_buffer.getvalue()
        csv_pages.append({"page": idx, "text": csv_text})
    t_csv_extract = (time.time() - t0) * 1000
    csv_chunks = chunk_pages(csv_pages, xlsx_path.name + "_csv")

    results['CSV Conversion'] = {
        'extract_time_ms': round(t_csv_extract, 2),
        'total_pages': len(csv_pages),
        'total_chunks': len(csv_chunks),
        'total_chars': sum(len(c['text']) for c in csv_chunks),
        'sample_chunk': csv_chunks[0]['text'][:250]
    }

    # -------------------------------------------------------------
    # FORMAT 2: Markdown Table Preprocessing (.xlsx -> Markdown Table)
    # -------------------------------------------------------------
    t0 = time.time()
    md_pages = []
    excel_file = pd.ExcelFile(BytesIO(raw_bytes))
    for idx, sheet_name in enumerate(excel_file.sheet_names, start=1):
        df_sheet = pd.read_excel(excel_file, sheet_name=sheet_name).dropna(how='all')
        headers = df_sheet.columns.tolist()
        header_row = "| " + " | ".join(str(h) for h in headers) + " |"
        sep_row = "| " + " | ".join("---" for _ in headers) + " |"
        data_rows = ["| " + " | ".join(str(v) if pd.notna(v) else "" for v in row) + " |" for row in df_sheet.values]
        md_text = f"[Markdown Table: {xlsx_path.name} | Sheet: {sheet_name}]\n" + header_row + "\n" + sep_row + "\n" + "\n".join(data_rows)
        md_pages.append({"page": idx, "text": md_text})
    t_md_extract = (time.time() - t0) * 1000
    md_chunks = chunk_pages(md_pages, xlsx_path.name + "_md")

    results['Markdown Table'] = {
        'extract_time_ms': round(t_md_extract, 2),
        'total_pages': len(md_pages),
        'total_chunks': len(md_chunks),
        'total_chars': sum(len(c['text']) for c in md_chunks),
        'sample_chunk': md_chunks[0]['text'][:250]
    }

    # -------------------------------------------------------------
    # FORMAT 3: JSON Lines Preprocessing (.xlsx -> .jsonl)
    # -------------------------------------------------------------
    t0 = time.time()
    json_pages = []
    excel_file = pd.ExcelFile(BytesIO(raw_bytes))
    for idx, sheet_name in enumerate(excel_file.sheet_names, start=1):
        df_sheet = pd.read_excel(excel_file, sheet_name=sheet_name).dropna(how='all')
        json_lines = [json.dumps(row) for row in df_sheet.to_dict(orient='records')]
        json_text = f"[JSONL Dataset: {xlsx_path.name} | Sheet: {sheet_name}]\n" + "\n".join(json_lines)
        json_pages.append({"page": idx, "text": json_text})
    t_json_extract = (time.time() - t0) * 1000
    json_chunks = chunk_pages(json_pages, xlsx_path.name + "_json")

    results['JSON Lines'] = {
        'extract_time_ms': round(t_json_extract, 2),
        'total_pages': len(json_pages),
        'total_chunks': len(json_chunks),
        'total_chars': sum(len(c['text']) for c in json_chunks),
        'sample_chunk': json_chunks[0]['text'][:250]
    }

    # -------------------------------------------------------------
    # FORMAT 4: Header-Preserving Key-Value Engine (Current)
    # -------------------------------------------------------------
    t0 = time.time()
    kv_pages = extract_pages(BytesIO(raw_bytes), xlsx_path.name)
    t_kv_extract = (time.time() - t0) * 1000
    kv_chunks = chunk_pages(kv_pages, xlsx_path.name + "_kv")

    results['Key-Value + Distribution Summary (Current)'] = {
        'extract_time_ms': round(t_kv_extract, 2),
        'total_pages': len(kv_pages),
        'total_chunks': len(kv_chunks),
        'total_chars': sum(len(c['text']) for c in kv_chunks),
        'sample_chunk': kv_chunks[0]['text'][:250]
    }

    # -------------------------------------------------------------
    # VECTOR RETRIEVAL EVALUATION ACCROSS FORMATS
    # -------------------------------------------------------------
    test_queries = [
        "How many students are in the CC Lab?",
        "How many students are in III AD Classroom A?",
        "What is the venue for Student_5?"
    ]

    print("\n==========================================================================")
    print("                      SYSTEM EFFICIENCY & BENCHMARK SUMMARY               ")
    print("==========================================================================")
    print(f"{'Embedding Format':<45} | {'Extract (ms)':<12} | {'Chunks':<8} | {'Total Chars':<12}")
    print("-" * 85)
    for fmt_name, meta in results.items():
        print(f"{fmt_name:<45} | {meta['extract_time_ms']:<12} | {meta['total_chunks']:<8} | {meta['total_chars']:<12}")

    print("\n==========================================================================")
    print("                 RETRIEVAL EVALUATION FOR TEST QUERIES                    ")
    print("==========================================================================")

    all_format_chunks = [
        ('CSV Conversion', csv_chunks),
        ('Markdown Table', md_chunks),
        ('JSON Lines', json_chunks),
        ('Key-Value + Distribution Summary', kv_chunks)
    ]

    for fmt_name, chunks in all_format_chunks:
        print(f"\n---> Testing Vector Retrieval for: [{fmt_name}]")
        reset_collection()
        embeds = embed_documents([c['text'] for c in chunks])
        digest = file_hash(raw_bytes + fmt_name.encode())
        add_chunks(chunks, embeds, digest)

        for q in test_queries:
            emb = embed_query(q)
            res = search(emb, top_k=1)
            matched_text = res[0]['text'][:120].replace('\n', ' ') if res else 'NO MATCH'
            print(f"  Q: '{q}' -> Top Match Score ({res[0].get('score', 0):.4f}): {matched_text}...")

if __name__ == '__main__':
    run_benchmark()
