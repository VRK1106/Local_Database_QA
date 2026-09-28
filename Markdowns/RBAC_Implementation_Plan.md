# RBAC Implementation Plan: Placement QA System

**Scope:** Add the student perspective to the existing placement-department-only system, using two roles: `placement` and `student`.
**Stack:** Flask, Ollama, ChromaDB, SQLite in-memory router, DeBERTa trust layer.

Confidence tags used below: **[Certain]** hard evidence, **[Likely]** strong inference, **[Guessing]** filling gaps.

---

## 1. Core Principle

Role checks alone will not protect student data. RBAC only decides which **routes** a role can call. It says nothing about which **rows** a student can see once inside `/api/query`.

If you add a `student` role but keep one shared ChromaDB collection and one SQLite table, a logged-in student can still retrieve another student's CGPA. **[Certain]**

You need two layers:

1. **RBAC** (route-level): who can call which endpoint.
2. **Data-layer scoping** (row-level): what data each role's query can physically reach. This must be enforced server-side, before the LLM sees any data, and never through prompt instructions.

---

## 2. Why These Changes Are Needed

| Problem (from the evaluation report) | Consequence if unfixed |
| :--- | :--- |
| `/api/reset_db`, `/api/upload`, `/api/delete_doc` are unauthenticated | Anyone on the network can wipe all documents with one HTTP POST **[Certain]** |
| Shared vector/SQL space with no isolation | Any student can ask "What is Rohan Gupta's CGPA?" and get a real answer **[Certain]** |
| Prompt-level restrictions are the only guard | A prompt rule is a suggestion the model can be argued out of **[Likely]** |
| No audit trail | No record of who queried which student data |

---

## 3. The Two Roles

### Role 1: `placement` (TPO / Coordinators)

| Area | Allowed |
| :--- | :--- |
| Documents | Upload, delete, view chunks, tag each file as `public` or `internal` |
| Queries | Unrestricted: full-table SQL router, aggregates, shortlists, all-student lookups |
| Users | Import student accounts from the master list, reset student passwords, disable accounts |
| System | Schema inspection, model and Top-K settings, view audit log |
| Destructive | `/api/reset_db` only after re-entering their password (second confirmation) |

### Role 2: `student`

| Area | Allowed |
| :--- | :--- |
| Documents | Nothing: no upload, delete, chunk inspection, or file picker |
| Queries | Policy, criteria, schedule, and notice questions, answered from `public` documents only |
| Own record | Their own CGPA, backlogs, offer status, and eligible drives |
| Denied | Questions about any other student, any all-student list, any cross-student aggregate |
| System | Change own password only |

**[Likely]** Two roles is enough for v1. The weakness is that `placement` lumps an everyday coordinator with someone who can wipe the database. Adding an `is_superadmin` flag later is cheap if needed.

---

## 4. Access Matrix

| Endpoint / Action | placement | student |
| :--- | :---: | :---: |
| `POST /login`, `POST /logout` | ✅ | ✅ |
| `POST /api/query` | ✅ full scope | ✅ scoped |
| `GET /documents`, chunk modal | ✅ | ❌ |
| `POST /api/upload`, `/api/delete_doc` | ✅ | ❌ |
| `POST /api/reset_db` | ✅ + re-auth | ❌ |
| `POST /admin/import_students` | ✅ | ❌ |
| `GET /api/audit_log` | ✅ | ❌ |
| `POST /api/change_password` | ✅ | ✅ (own only) |

---

## 5. What to Build

### 5.1 Authentication

- Create a `users` table:

  | Column | Notes |
  | :--- | :--- |
  | `id` | primary key |
  | `username` | roll number for students |
  | `password_hash` | never plaintext |
  | `role` | `placement` or `student` |
  | `student_id` | null for placement users; links to the student row |
  | `active` | boolean |
  | `must_change_password` | boolean |

- Hash passwords with `werkzeug.security.generate_password_hash`. **[Certain]**
- **No self-signup.** Student accounts are created from the master list. Initial password should be random or one-time, with a forced change on first login. Roll number plus DOB as a password is guessable, so avoid it. **[Likely]**
- Session cookie flags: `HttpOnly`, `SameSite=Lax`. Load the secret key from an environment variable, not from source code.

### 5.2 Route Guard

```python
from functools import wraps
from flask import abort
from flask_login import current_user

def role_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if not current_user.is_authenticated or current_user.role not in roles:
                abort(403)
            return f(*a, **kw)
        return wrapper
    return deco
```

Apply `@role_required("placement")` to: upload, delete, reset, documents, import, audit log.
Apply `@role_required("placement", "student")` to: `/api/query`, `/api/change_password`.

### 5.3 Two Data Paths Inside `/api/query`

The server picks the path from `current_user.role`. **Never** read the role or scope from the request body.

**Student path**

- **Policy questions:** query ChromaDB with a server-enforced filter:
  ```python
  collection.query(query_texts=[q], n_results=k, where={"visibility": "public"})
  ```
  The student cannot alter this filter.
- **Own-record questions:** run a fixed, parameterized SQL query bound to the session:
  ```python
  cur.execute("SELECT * FROM students WHERE student_id = ?", (current_user.student_id,))
  ```
  Pass that single row plus the retrieved public criteria to the LLM. Eligibility is then computed from their row against the criteria.
- **Never let the LLM write SQL on the student path.** If any part of the router has the model generate SQL, a student can talk it into `SELECT *`. Use templates only. **[Likely]** (depends on how the router builds SQL, which the report does not show)
- **Aggregates:** disable the SQL router's aggregate mode for students. Publish any stats you want them to see (for example, overall placement percentage) as a `public` document.

**Placement path**

Current behavior, unchanged.

### 5.4 Mask at Ingestion, Not in the Prompt

- Build the `public` index only from documents the TPO explicitly tagged `public`.
- Student master sheets stay `internal` and never enter the student-visible index.
- Telling the LLM "don't reveal other students" is not a control. **[Certain]**

### 5.5 Audit Log

Table: `user_id`, `role`, `query`, `path_used`, `sources`, `timestamp`.
Write a row on every query and every admin action. This closes the report's "no auditing" gap and is cheap to add now.

---

## 6. Order of Implementation

1. `users` table, login, session, and `role_required` on the destructive routes.
2. `visibility` tag on documents (a TPO upload option) and re-tagging of existing chunks.
3. Student query path: filtered Chroma plus parameterized own-record SQL.
4. Student account import from the master list.
5. Audit log.

**Deferred until the above is done:** multi-turn memory, `webkitSpeechRecognition` swap, broader intent detection, Gunicorn/Nginx deployment.

---

## 7. Risks

| Risk | Detail |
| :--- | :--- |
| **Identity key mismatch** | Own-record lookup needs one reliable `student_id` column across all spreadsheets. If headers differ between sheets or header auto-detect misfires, a student could be bound to the wrong row. Verify the mapping when importing accounts. **[Likely]** |
| **Old data in the index** | Existing ChromaDB chunks have no `visibility` tag. Filtering on the tag without re-indexing means untagged chunks either vanish or leak, depending on the filter. Re-ingest with tags and default untagged chunks to `internal`. |
| **Flask dev server over HTTP** | Fine for testing, but do not send real student credentials through it. Put it behind HTTPS before real use, since sessions over plain HTTP on campus Wi-Fi can be sniffed. **[Likely]** |
| **Masking done only at prompt level** | If the only protection is an instruction to the LLM, it fails against a determined student. All scoping must happen before data reaches the model. **[Certain]** |

---

## 8. Definition of Done

- [ ] Unauthenticated requests to any protected route return 401/403.
- [ ] A student session cannot retrieve any chunk tagged `internal`.
- [ ] A student asking about another student's record gets a refusal, and the log shows the SQL path was never invoked with another ID.
- [ ] `/api/reset_db` requires role `placement` plus password re-entry.
- [ ] Every query and admin action appears in the audit log.
- [ ] Re-indexed ChromaDB contains a `visibility` tag on every chunk.
