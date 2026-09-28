import os
import re
import sqlite3
import tempfile
from pathlib import Path
import pandas as pd

from src.ollama_client import generate_ollama_answer

def sanitize_table_name(name: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', name).strip('_')
    if not cleaned or cleaned[0].isdigit():
        cleaned = "tbl_" + cleaned
    return cleaned.lower()

def is_aggregate_query(query: str) -> bool:
    """
    Universally detects if a query is structured/tabular (SQL intent) using NLP regex patterns.
    It looks for mathematical operations, comparisons, extremes, or strict filtering.
    """
    import re
    query_lower = query.lower()
    
    # Pattern 1: Aggregations & Math
    agg_pattern = r'\b(how many|count|average|mean|total|sum|group by)\b'
    if re.search(agg_pattern, query_lower):
        return True
        
    # Pattern 2: Comparatives & Inequalities (numeric filters)
    comp_pattern = r'\b(greater than|less than|more than|fewer than|above|below|at least|at most|over|under|equal to|exceeding)\b'
    if re.search(comp_pattern, query_lower):
        return True
        
    # Pattern 3: Superlatives & Extremes
    ext_pattern = r'\b(highest|lowest|maximum|minimum|top|bottom|most|least|first|last)\b'
    if re.search(ext_pattern, query_lower):
        return True
        
    # Pattern 4: Strict Set Extractions / Filters
    # E.g. "show me all", "list all", "which students", "who has", "find all", "who have"
    extract_pattern = r'\b(show me all|list all|find all|which \w+|who (has|have|had)|whose|filter by)\b'
    if re.search(extract_pattern, query_lower):
        return True
        
    return False

def prepare_dataframe_for_sql(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    
    # 1. Sanitize column names
    new_cols = []
    seen = set()
    for c in df.columns:
        cl = re.sub(r'[^a-zA-Z0-9_]', '_', str(c)).strip('_')
        cl = re.sub(r'_+', '_', cl).lower()
        if not cl:
            cl = 'unnamed'
        elif cl[0].isdigit():
            cl = 'col_' + cl
        
        orig = cl
        i = 1
        while cl in seen:
            cl = f"{orig}_{i}"
            i += 1
        seen.add(cl)
        new_cols.append(cl)
        
    df.columns = new_cols
    
    # 2. Infer types (cast strings to numeric if possible)
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except Exception:
            pass
    
    return df


def build_universal_sqlite_db(documents_dir: Path, selected_sources: list[str] = None) -> tuple[str, sqlite3.Connection, dict]:
    """
    Scans documents_dir (filtered by selected_sources if provided),
    loads ALL structured data formats (Excel, CSV, TSV, JSON, SQLite, SQL)
    into a single temporary SQLite database connection and returns (tmp_db_path, conn, table_schemas).
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_path = tmp.name
    tmp.close()
    
    conn = sqlite3.connect(tmp_path)
    
    target_files = []
    if documents_dir.exists():
        for p in documents_dir.glob("**/*"):
            if p.is_file():
                if selected_sources:
                    if p.name in selected_sources or str(p.relative_to(documents_dir)) in selected_sources:
                        target_files.append(p)
                else:
                    target_files.append(p)

    table_schemas = {}

    for p in target_files:
        ext = p.suffix.lower()
        base_name = sanitize_table_name(p.stem)
        
        try:
            if ext in [".xlsx", ".xls", ".xlsm"]:
                excel_file = pd.ExcelFile(p)
                for sheet in excel_file.sheet_names:
                    # Read without headers to detect the actual header row
                    df = pd.read_excel(excel_file, sheet_name=sheet, header=None).dropna(how='all')
                    if not df.empty:
                        # Find the label index of the row with the most non-null values (usually the header)
                        header_label = df.notna().sum(axis=1).idxmax()
                        header_pos = df.index.get_loc(header_label)
                        
                        # Set the columns and keep only data rows
                        df.columns = df.iloc[header_pos].astype(str).str.strip()
                        df = df.iloc[header_pos + 1:].reset_index(drop=True)
                        df = df.dropna(how='all', axis=1)
                        
                        if df.empty:
                            continue
                            
                        df = prepare_dataframe_for_sql(df)
                        t_name = base_name if len(excel_file.sheet_names) == 1 else sanitize_table_name(f"{base_name}_{sheet}")
                        df.to_sql(t_name, conn, index=False, if_exists="replace")
                        
                        samples = {}
                        for col in df.columns:
                            unique_vals = [str(v).strip() for v in df[col].dropna().unique()[:3] if str(v).strip()]
                            samples[str(col)] = unique_vals
                            
                        table_schemas[t_name] = {
                            "source_file": p.name,
                            "columns": list(df.columns),
                            "samples": samples,
                            "row_count": len(df)
                        }
            elif ext in [".csv", ".tsv", ".txt"]:
                sep = '\t' if ext == ".tsv" else ','
                try:
                    df = pd.read_csv(p, sep=sep).dropna(how='all')
                    if not df.empty and len(df.columns) > 1:
                        df = prepare_dataframe_for_sql(df)
                        t_name = base_name
                        df.to_sql(t_name, conn, index=False, if_exists="replace")
                        
                        samples = {}
                        for col in df.columns:
                            unique_vals = [str(v).strip() for v in df[col].dropna().unique()[:3] if str(v).strip()]
                            samples[str(col)] = unique_vals
                            
                        table_schemas[t_name] = {
                            "source_file": p.name,
                            "columns": list(df.columns),
                            "samples": samples,
                            "row_count": len(df)
                        }
                except Exception:
                    pass
            elif ext in [".json", ".jsonl"]:
                try:
                    df = pd.read_json(p, lines=(ext == ".jsonl"))
                    if not df.empty:
                        df = prepare_dataframe_for_sql(df)
                        t_name = base_name
                        df.to_sql(t_name, conn, index=False, if_exists="replace")
                        
                        samples = {}
                        for col in df.columns:
                            unique_vals = [str(v).strip() for v in df[col].dropna().unique()[:3] if str(v).strip()]
                            samples[str(col)] = unique_vals
                            
                        table_schemas[t_name] = {
                            "source_file": p.name,
                            "columns": list(df.columns),
                            "samples": samples,
                            "row_count": len(df)
                        }
                except Exception:
                    pass
            elif ext in [".db", ".sqlite", ".sqlite3"]:
                try:
                    src_conn = sqlite3.connect(p)
                    cursor = src_conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                    tables = [row[0] for row in cursor.fetchall() if not row[0].startswith('sqlite_')]
                    for t in tables:
                        df = pd.read_sql_query(f"SELECT * FROM `{t}`", src_conn)
                        df = prepare_dataframe_for_sql(df)
                        t_name = sanitize_table_name(f"{base_name}_{t}")
                        df.to_sql(t_name, conn, index=False, if_exists="replace")
                        
                        samples = {}
                        for col in df.columns:
                            unique_vals = [str(v).strip() for v in df[col].dropna().unique()[:3] if str(v).strip()]
                            samples[str(col)] = unique_vals
                            
                        table_schemas[t_name] = {
                            "source_file": p.name,
                            "columns": list(df.columns),
                            "samples": samples,
                            "row_count": len(df)
                        }
                    src_conn.close()
                except Exception:
                    pass
            elif ext == ".sql":
                try:
                    sql_text = p.read_text(encoding='utf-8', errors='ignore')
                    conn.executescript(sql_text)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                    tables = [row[0] for row in cursor.fetchall() if not row[0].startswith('sqlite_')]
                    for t in tables:
                        if t not in table_schemas:
                            df = pd.read_sql_query(f"SELECT * FROM `{t}`", conn)
                            df = prepare_dataframe_for_sql(df)
                            samples = {}
                            for col in df.columns:
                                unique_vals = [str(v).strip() for v in df[col].dropna().unique()[:3] if str(v).strip()]
                                samples[str(col)] = unique_vals
                                
                            table_schemas[t] = {
                                "source_file": p.name,
                                "columns": list(df.columns),
                                "samples": samples,
                                "row_count": len(df)
                            }
                except Exception:
                    pass
        except Exception as e:
            print(f"Error loading {p.name} into universal SQL engine: {e}")

    return tmp_path, conn, table_schemas

def execute_universal_structured_query(query: str, documents_dir: Path, selected_sources: list[str], model_name: str):
    """
    Executes a structured SQL calculation across all target structured files.
    Returns (final_prompt_for_prose, sql_query, sql_result, citations) or (None, None, None, []) if failed/not applicable.
    """
    tmp_path, conn, table_schemas = build_universal_sqlite_db(documents_dir, selected_sources)
    
    if not table_schemas:
        if conn:
            conn.close()
        try:
            os.remove(tmp_path)
        except:
            pass
        return None, None, None, []

    schema_descriptions = []
    for t_name, info in table_schemas.items():
        cols_desc = []
        for c, samples in info["samples"].items():
            sample_str = f" (e.g. {', '.join([repr(s) for s in samples])})" if samples else ""
            cols_desc.append(f"{c}{sample_str}")
            
        schema_descriptions.append(
            f"Table Name: '{t_name}' (Source File: {info['source_file']}, Total Rows: {info['row_count']})\n"
            f"Columns with sample data:\n" + "\n".join(f"  - {cd}" for cd in cols_desc)
        )
        
    schema_prompt = "\n\n".join(schema_descriptions)
    
    sql_prompt = (
        f"You are a SQL expert. Given the following SQLite database tables and column schemas (with sample data):\n\n"
        f"{schema_prompt}\n\n"
        f"User Question: '{query}'\n\n"
        f"Write a valid SQLite SELECT query to accurately answer the question. "
        f"Guidelines:\n"
        f"- Use exact column and table names from the schema provided above. Do NOT invent or guess column names.\n"
        f"- Compare numeric columns mathematically (e.g. >, <, =).\n"
        f"- Use case-insensitive matching (e.g. LIKE '%term%' or LOWER(column) = 'term') for string comparisons.\n"
        f"- ONLY return the raw SQL query without markdown formatting, code blocks, or explanations."
    )

    sql_query = generate_ollama_answer(sql_prompt, model_name).strip()
    sql_query = sql_query.replace("```sql", "").replace("```", "").strip()

    try:
        cur = conn.cursor()
        cur.execute(sql_query)
        sql_result = cur.fetchall()
        col_names = [description[0] for description in cur.description] if cur.description else []
        conn.close()
        try:
            os.remove(tmp_path)
        except:
            pass
            
        unique_sources = ", ".join(list(set(info["source_file"] for info in table_schemas.values())))
        citations = [{
            "source": unique_sources,
            "page": 1,
            "score": 1.0,
            "text": f"Universal Structured Execution:\nQuery: {sql_query}\nColumns: {col_names}\nResult: {sql_result}"
        }]
        
        final_prompt = (
            f"The user asked: '{query}'.\n"
            f"The database execution result for query [{sql_query}] is:\n"
            f"Result Rows: {sql_result}\n\n"
            f"Formulate a clear, direct, concise, and natural language response answering the user's question based strictly on this database result."
        )
        
        return final_prompt, sql_query, sql_result, citations
        
    except Exception as e:
        print(f"Universal SQL execution error: {e}")
        if conn:
            conn.close()
        try:
            os.remove(tmp_path)
        except:
            pass
        return None, None, None, []


def execute_student_scoped_query(query: str, student_id: str, documents_dir: Path, model_name: str):
    """
    Ironclad row-level student scoping:
    Executes a hardcoded, parameterized query strictly bound to the authenticated student_id.
    Bypasses LLM SQL generation, completely preventing cross-student data exfiltration.
    Returns (final_prompt, sql_query, sql_result, citations) or (None, None, None, []).
    """
    import json
    if not student_id:
        return None, None, None, []

    # Only invoke row-level personal DB query if the query asks about self/record
    personal_keywords = [
        "my", "mine", "me", "i", "cgpa", "gpa", "marks", "grade", "score",
        "backlog", "placed", "placement", "offer", "package", "salary",
        "eligib", "status", "profile", "record", "details", "resume"
    ]
    query_lower = query.lower()
    is_personal_intent = any(k in query_lower.split() or k in query_lower for k in personal_keywords) or (student_id.lower() in query_lower)
    if not is_personal_intent:
        return None, None, None, []

    tmp_path, conn, table_schemas = build_universal_sqlite_db(documents_dir, None)
    if not table_schemas:
        if conn:
            conn.close()
        try:
            os.remove(tmp_path)
        except:
            pass
        return None, None, None, []

    # Find table with student identifier column
    target_table = None
    id_column = None
    for t_name, info in table_schemas.items():
        for col in info["samples"].keys():
            if col.lower() in ["student_id", "usn", "roll_number", "roll_no", "id", "reg_no"]:
                target_table = t_name
                id_column = col
                break
        if target_table:
            break

    if not target_table or not id_column:
        conn.close()
        try:
            os.remove(tmp_path)
        except:
            pass
        return None, None, None, []

    safe_sql = f"SELECT * FROM \"{target_table}\" WHERE LOWER(TRIM(\"{id_column}\")) = ? LIMIT 1;"
    cur = conn.cursor()
    cur.execute(safe_sql, (student_id.strip().lower(),))
    row = cur.fetchone()
    col_names = [description[0] for description in cur.description] if cur.description else []
    conn.close()
    try:
        os.remove(tmp_path)
    except:
        pass

    if not row:
        return None, None, None, []

    student_record = dict(zip(col_names, row))
    citations = [{
        "source": table_schemas[target_table]["source_file"],
        "page": 1,
        "score": 1.0,
        "text": f"Authenticated Student Record ({student_id}): {student_record}"
    }]

    final_prompt = (
        f"You are the Placement Office Assistant answering an authenticated student whose verified ID is '{student_id}'.\n"
        f"The student asks: '{query}'\n\n"
        f"Verified student's personal record from the official database:\n{json.dumps(student_record, indent=2)}\n\n"
        f"Security & Privacy Directives:\n"
        f"1. You may ONLY discuss and display information concerning this verified student (ID: '{student_id}').\n"
        f"2. If the student asks about any other student, their classmates' CGPA, ranks, or aggregate university statistics, strictly refuse and inform them that cross-student records are confidential.\n"
        f"3. Provide a helpful, clear, and reassuring response based strictly on their official record above."
    )
    return final_prompt, safe_sql, [row], citations


def get_student_record(student_id: str, documents_dir: Path) -> dict | None:
    """Fetch the single verified row for student_id from any indexed structured placement database."""
    if not student_id:
        return None
    tmp_path, conn, table_schemas = build_universal_sqlite_db(documents_dir, None)
    if not table_schemas:
        if conn:
            conn.close()
        try:
            os.remove(tmp_path)
        except:
            pass
        return None

    target_table = None
    id_column = None
    for t_name, info in table_schemas.items():
        for col in info["samples"].keys():
            if col.lower() in ["student_id", "usn", "roll_number", "roll_no", "id", "reg_no"]:
                target_table = t_name
                id_column = col
                break
        if target_table:
            break

    if not target_table or not id_column:
        conn.close()
        try:
            os.remove(tmp_path)
        except:
            pass
        return None

    safe_sql = f"SELECT * FROM \"{target_table}\" WHERE LOWER(TRIM(\"{id_column}\")) = ? LIMIT 1;"
    cur = conn.cursor()
    cur.execute(safe_sql, (student_id.strip().lower(),))
    row = cur.fetchone()
    col_names = [description[0] for description in cur.description] if cur.description else []
    conn.close()
    try:
        os.remove(tmp_path)
    except:
        pass

    if not row:
        return None
    return dict(zip(col_names, row))

