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


# -------------------------------------------------------------------------
# Student intent classification
# -------------------------------------------------------------------------
# Students need a narrower guard than is_aggregate_query(): words such as
# "last", "first", "which", "top" or "over" appear in ordinary questions about
# circulars ("last date to register", "which companies are visiting"), so the
# aggregate block only applies when the question targets other people's records.

_FIRST_PERSON_RE = re.compile(r"\b(my|mine|me|myself|i|i'm|im|i've|am i|do i|can i|have i)\b")

_PERSONAL_FIELD_RE = re.compile(
    r"\b(cgpa|gpa|backlogs?|arrears?|profile|record|internships?|speciali[sz]ation|branch|department|placed|marks|percentage)\b"
    r"|\bplacement status\b"
)

_PUBLIC_TOPIC_RE = re.compile(
    r"\b(eligib\w*|criteria|cut-?off|company|companies|circular|notice|policy|policies|drive|drives|rules?|"
    r"ctc|package|salary|stipend|compensation|deadline|date|dates|schedule|registration|register|"
    r"venue|location|interview|rounds?|selection|assessment|test|dress|attire|resume|documents?|"
    r"training|role|designation|recruit\w*|apex|tcs|infosys|wipro|visiting|hiring|bond|probation|"
    r"required|requirements?|needed|allowed)\b"
)

_PEER_TARGET_RE = re.compile(
    r"\b(students|classmates?|peers?|batch|batchmates?|everyone|everybody|others|other students?|"
    r"friends?|people|candidates|toppers?|class)\b"
)

_PEER_STATS_RE = re.compile(
    r"\b(how many|count|number of|average|mean|total|sum|percentage of|placement rate|"
    r"rank|ranking|ranked|topper|highest|lowest|maximum|minimum|top \d+|bottom \d+|"
    r"list|who (?:has|have|had|got|is|are)|whose|which students?|compare|comparison)\b"
)

_ELIGIBILITY_RE = re.compile(
    r"\b(eligib\w*|qualif\w*|apply|applying|can i|could i|am i allowed|allowed to|meet|meets|criteria|cut-?off|"
    r"sit for|attend|participate)\b"
)

_FIELD_STATS_RE = re.compile(
    r"\b(how many|count|number of|average|mean|total|sum|rank|highest|lowest|top \d+|list|who|whose|compare)\b"
)

_STUDENT_ID_RE = re.compile(r"\b(stu\d{2,})\b", re.IGNORECASE)

_names_cache: list[tuple[str, str]] | None = None
_names_cache_time = 0.0


def _known_student_names() -> list[tuple[str, str]]:
    """Return cached (student_id, lowercase name) pairs used to detect cross-student lookups."""
    global _names_cache, _names_cache_time
    import time
    now = time.time()
    if _names_cache is not None and (now - _names_cache_time) < 60.0:
        return _names_cache
    pairs = []
    try:
        from src.auth import get_all_student_records
        for rec in get_all_student_records():
            sid = str(rec.get("student_id") or "").strip()
            name = str(rec.get("name") or "").strip().lower()
            if sid and name and name != sid.lower():
                pairs.append((sid, name))
    except Exception:
        pairs = _names_cache or []
    _names_cache = pairs
    _names_cache_time = now
    return pairs


def mentions_other_student(query: str, own_student_id: str) -> bool:
    """True if the query names a student ID or a registered student name other than the caller's own."""
    own = (own_student_id or "").strip().lower()
    query_lower = query.lower()
    for sid in _STUDENT_ID_RE.findall(query_lower):
        if sid.lower() != own:
            return True
    for sid, name in _known_student_names():
        if sid.lower() != own and re.search(rf"\b{re.escape(name)}\b", query_lower):
            return True
    return False


def is_student_restricted_query(query: str, own_student_id: str) -> bool:
    """
    Student-scope guard: True when the question asks for batch statistics, rankings, peer
    comparisons, or another named student's record. Questions about circulars, schedules,
    company drives or the student's own record are allowed through.
    """
    query_lower = query.lower()
    if mentions_other_student(query, own_student_id):
        return True
    if _PEER_TARGET_RE.search(query_lower) and _PEER_STATS_RE.search(query_lower):
        return True
    # Statistics over record fields without a first-person anchor ("who has the highest CGPA?",
    # "average backlogs"); cutoff questions ("minimum CGPA required") are left to the circulars.
    if (_PERSONAL_FIELD_RE.search(query_lower) and _FIELD_STATS_RE.search(query_lower)
            and not _FIRST_PERSON_RE.search(query_lower) and not _PUBLIC_TOPIC_RE.search(query_lower)):
        return True
    # Ranking-style questions about oneself still reveal peer data ("what is my rank in the batch?")
    if re.search(r"\b(rank|ranking|ranked|percentile|topper)\b", query_lower):
        return True
    return False


def classify_student_query(query: str) -> str:
    """
    Route an (already permitted) student question:
      'profile'     - only about the student's own record  -> deterministic answer, no LLM
      'eligibility' - own record combined with circulars    -> LLM over record + public chunks
      'public'      - general question about public notices -> public-only RAG
    """
    query_lower = query.lower()
    first_person = bool(_FIRST_PERSON_RE.search(query_lower))
    personal_field = bool(_PERSONAL_FIELD_RE.search(query_lower))
    public_topic = bool(_PUBLIC_TOPIC_RE.search(query_lower))

    if first_person and _ELIGIBILITY_RE.search(query_lower):
        return "eligibility"
    if first_person and personal_field:
        return "profile"
    if public_topic:
        # First-person questions about circular content ("what should I carry?") are public RAG
        return "public"
    if first_person or personal_field:
        return "profile"
    return "public"


def _clean_record_for_display(rec: dict) -> dict:
    """Drop bookkeeping columns before a record is shown to the student or sent to the LLM."""
    hidden = {"id", "updated_at", "CGPA", "Branch", "Department", "Backlogs", "Placed_Company"}
    return {k: v for k, v in rec.items() if k not in hidden and v not in (None, "")}

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
    Looks up only the record bound to the authenticated student_id (never LLM-generated SQL),
    then routes by intent (see classify_student_query):
      - 'profile'     -> deterministic instant answer from the verified record (no LLM)
      - 'eligibility' -> prompt combining the record with public circular chunks
      - 'public'      -> not handled here; caller falls back to public-only RAG
    Returns (final_prompt, sql_query, sql_result, citations, instant_answer); all empty when not applicable.
    """
    import json
    empty = (None, None, None, [], None)
    if not student_id:
        return empty

    intent = classify_student_query(query)
    if intent == "public":
        return empty

    # 1. Authoritative relational record (PostgreSQL / SQLite student_records)
    student_record = None
    safe_sql = "SELECT * FROM student_records WHERE LOWER(TRIM(student_id)) = %s LIMIT 1;"
    source_label = "PostgreSQL (student_records)"
    try:
        from src.auth import get_student_record_by_id
        db_rec = get_student_record_by_id(student_id)
        if db_rec:
            student_record = {}
            for k, v in db_rec.items():
                if hasattr(v, 'isoformat'):
                    student_record[k] = v.isoformat()
                elif hasattr(v, '__float__') and not isinstance(v, (int, float)):
                    student_record[k] = float(v)
                else:
                    student_record[k] = v
    except Exception:
        student_record = None

    # 2. Fallback: scan uploaded structured documents for the caller's own row
    if not student_record:
        rec = get_student_record(student_id, documents_dir)
        if rec:
            student_record = rec
            source_label = "Uploaded student roster"

    if not student_record:
        if intent == "profile":
            msg = (
                f"No verified academic record is registered for your student ID (`{student_id}`) yet. "
                f"Please contact the Placement Office, or raise a ticket under **Issue Resolver**, so your record can be added."
            )
            return None, None, None, [], msg
        return empty

    display_record = _clean_record_for_display(student_record)
    citations = [{
        "source": source_label,
        "page": 1,
        "score": 1.0,
        "text": f"Verified student record for {student_id}: " + "; ".join(f"{k}: {v}" for k, v in display_record.items())
    }]
    row = list(display_record.values())

    # 3. Instant profile resolution: deterministic, no LLM latency or hallucination risk
    if intent == "profile":
        name = display_record.get("name", student_id)
        status = display_record.get("placement_status") or "Not Placed"
        company = display_record.get("placed_company")
        backlogs = display_record.get("backlogs", 0)
        if company:
            status_line = f"**{status}** at **{company}**"
        elif str(status).lower() in ("not placed", "eligible", ""):
            status_line = f"**{status}** *(Eligible for upcoming recruitment drives)*"
        else:
            status_line = f"**{status}**"
        backlog_line = f"{backlogs} *(Clear academic record)*" if str(backlogs) in ("0", "0.0", "None") else f"**{backlogs} active backlog(s)**"

        lines = [
            f"- **Cumulative GPA (CGPA):** **{display_record.get('cgpa', '—')}** / 10.0",
            f"- **Placement Status:** {status_line}",
            f"- **Department / Specialization:** {display_record.get('specialization', '—')}",
            f"- **Active Backlogs:** {backlog_line}",
        ]
        if display_record.get("tenth_percent") is not None:
            lines.append(f"- **10th Aggregate:** {display_record['tenth_percent']}%")
        if display_record.get("twelfth_percent") is not None:
            lines.append(f"- **12th / Diploma Aggregate:** {display_record['twelfth_percent']}%")
        if "internships" in display_record:
            lines.append(f"- **Internships Completed:** {display_record['internships']}")
        instant_answer = (
            f"Hello **{name}** (`{student_id}`),\n\n"
            f"Here is your verified academic and placement status directly from the official registry:\n\n"
            + "\n".join(lines)
            + "\n\n> *Tip: Ask about eligibility for a drive (e.g. \"Am I eligible for the Apex drive?\") to check your record against the latest circulars.*"
        )
        return None, safe_sql, [row], citations, instant_answer

    # 4. Eligibility: combine the verified record with public circulars only (visibility='public')
    public_context = ""
    try:
        from src.embeddings import embed_query
        from src.vectorstore import search
        q_vec = embed_query(query)
        public_chunks = search(query_embedding=q_vec, top_k=3, visibility="public")
        if public_chunks:
            public_context = "\n\nOfficial Public Placement Notices:\n" + "\n---\n".join(c["text"] for c in public_chunks)
            for c in public_chunks:
                citations.append({
                    "source": c.get("source", "Public Placement Circular"),
                    "page": c.get("page", 1),
                    "score": c.get("score", 1.0),
                    "text": c.get("text", "")
                })
    except Exception as e:
        print(f"[STUDENT QUERY] Public circular retrieval failed: {e}")

    final_prompt = (
        f"You are the Placement Office Assistant answering an authenticated student whose verified ID is '{student_id}'.\n"
        f"The student asks: '{query}'\n\n"
        f"Verified student's personal record from the official database:\n{json.dumps(display_record, indent=2, default=str)}"
        f"{public_context or chr(10) + chr(10) + 'No public circular matched this question.'}\n\n"
        f"Rules:\n"
        f"1. Use ONLY the record and notices above. Do not assume any fact that is not written there "
        f"(for example degree, 10th/12th marks or gap years); if a criterion cannot be checked from the record, say so explicitly.\n"
        f"2. Compare each stated criterion against the record and conclude clearly (eligible / not eligible / cannot be fully confirmed).\n"
        f"3. Discuss only this student's own record. Never reveal or estimate other students' data.\n"
        f"4. Be concise and use short bullet points."
    )
    return final_prompt, safe_sql, [row], citations, None


def get_student_record(student_id: str, documents_dir: Path) -> dict | None:
    """Fetch the single verified row for student_id from auth.db student_records or universal documents."""
    if not student_id:
        return None

    # Step 1: Check authoritative student_records in auth.db
    try:
        from src.auth import get_student_record_by_id
        db_rec = get_student_record_by_id(student_id)
        if db_rec:
            rec = dict(db_rec)
            # Normalize canonical aliases for templates & prompt builders
            rec["CGPA"] = rec.get("cgpa", 0.0)
            rec["Branch"] = rec.get("specialization", "Computer Science")
            rec["Department"] = rec.get("specialization", "Computer Science")
            rec["Backlogs"] = rec.get("backlogs", 0)
            rec["Placed_Company"] = rec.get("placed_company") or rec.get("placement_status") or "Eligible"
            return rec
    except Exception:
        pass

    # Step 2: Fallback to scanning uploaded documents
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

    rec = dict(zip(col_names, row))
    # Normalize aliases
    rec["CGPA"] = rec.get("cgpa") or rec.get("CGPA") or "—"
    rec["Branch"] = rec.get("specialization") or rec.get("branch") or rec.get("department") or rec.get("Branch") or "General"
    rec["Department"] = rec["Branch"]
    rec["Backlogs"] = rec.get("backlogs") or rec.get("Backlogs") or 0
    rec["Placed_Company"] = rec.get("placement_status") or rec.get("placed_company") or rec.get("Placed_Company") or "Eligible"
    return rec

