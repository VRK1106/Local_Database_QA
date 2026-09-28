# Comprehensive Expert Evaluation Report: Local Database QA System
**Domain Focus:** University Placement Cell Operations & Student Campus Recruitment  
**System Architecture:** 100% Offline RAG (Ollama LLM + ChromaDB + SentenceTransformers + NLI DeBERTa Trust Layer + SQLite In-Memory Engine)

---

## Executive Summary

The **Local Database Question-Answering (QA) System** is a privacy-first, on-premise Retrieval-Augmented Generation (RAG) platform. By combining **Semantic Vector Retrieval** (ChromaDB) with an automated **Universal Structured SQL Router** (in-memory SQLite translation) and a **DeBERTa-v3 Cross-Encoder Trust Layer**, it addresses one of higher education's most sensitive operational domains: **Campus Placement Data Management**.

This report provides a 360-degree technical and functional audit of the system’s **Abilities** (strengths and operational wins) and **Disabilities** (architectural limitations, risks, and missing capabilities), viewed through the distinct lenses of two core stakeholders:
1. **The Placement Department** (Training & Placement Officers, Coordinators, Data Administrators)
2. **The Students** (Job Seekers, Campus Candidates, Interviewees)

---

## 1. Architectural & Feature Overview

```
                        ┌─────────────────────────────────────────────────────────┐
                        │             Web Interface (Flask / HTML5)               │
                        │   • Voice Typing (Win+H)    • Web Speech TTS Readout    │
                        │   • Document Filter Picker  • Model & Top-K Selectors   │
                        └───────────────────────────┬─────────────────────────────┘
                                                    │ User Query
                                                    ▼
                                    ┌──────────────────────────────┐
                                    │ NLP Intent / Aggregate Regex │
                                    └───────┬──────────────┬───────┘
                     Tabular / Math Query  │              │ Semantic / Free-text
                                            ▼              ▼
                     ┌─────────────────────────────┐  ┌─────────────────────────────┐
                     │   Universal SQL Router      │  │     ChromaDB Vector Store   │
                     │ • On-the-fly SQLite loader  │  │ • bge-small-en-v1.5 Embeds  │
                     │ • Header offset auto-detect │  │ • Row-preserving chunking   │
                     │ • Deterministic computation │  │ • Multi-format extractors   │
                     └──────────────┬──────────────┘  └──────────────┬──────────────┘
                                    │ SQL Result                     │ Retrieved Passages
                                    └──────────────┬─────────────────┘
                                                   ▼
                                    ┌─────────────────────────────┐
                                    │    Local Ollama Engine      │
                                    │  (qwen2.5-coder / Llama3)   │
                                    │   • temp=0.0 deterministic  │
                                    │   • Grading scale injection │
                                    └──────────────┬──────────────┘
                                                   ▼
                                    ┌─────────────────────────────┐
                                    │   Cross-Encoder Trust Layer │
                                    │  (nli-deberta-v3-small)     │
                                    │   • Hallucination detection │
                                    │   • Entailment highlighting │
                                    └─────────────────────────────┘
```

---

## 2. Perspective 1: The Placement Department (TPO / Coordinators)

The Placement Department handles large volumes of volatile, confidential data: student master lists, backlog records, CGPA sheets, company eligibility criteria, salary package offers (CTC), and room allotments.

### ✅ Abilities (Operational Strengths)

| Feature | Technical Implementation | Practical Benefit for Placement Officers |
| :--- | :--- | :--- |
| **Absolute Data Confidentiality** | 100% on-premise execution via Ollama and local ChromaDB. Zero cloud API calls. | Eliminates compliance risks (FERPA, GDPR, institutional data privacy). Student phone numbers, email addresses, GPAs, and offer letters never leave the university's physical premises. |
| **Dual-Path Structured Ingestion** | In-memory translation of Excel (`.xlsx`), CSV, and SQLite dumps into queryable SQL tables (`src/structured_query.py`). | **Solves the classic RAG math flaw.** When asking *"How many students have CGPA > 8.0 with zero backlogs?"*, the system executes an exact `COUNT(*)` SQL query rather than guessing from truncated vector chunks. |
| **Multi-Row Header Resilience** | Automatic header detection (`notna().sum(axis=1).idxmax()`) in `src/structured_query.py`. | Placement spreadsheets often have 3–4 rows of institutional banners, metadata, or merger cells before the column names (as seen in `Mock_Placement.xlsx`). The system automatically detects and offsets this without manual file cleanup. |
| **Heterogeneous Policy Synthesis** | Extracts from `.pdf`, `.docx`, `.sql`, and `.json`. | Allows the TPO to ingest disparate documents simultaneously—e.g., *Company Offer Policy (PDF)* + *Student Registry (Excel)* + *Interview Schedule (Word)*. |
| **Source Filtering & Inspection** | UI-level document checkboxes and vector chunk modal inspection in `templates/documents.html`. | Coordinators can isolate queries to a specific recruitment drive (e.g., filter exclusively to `TCS_Drive_Eligible.xlsx`), preventing cross-contamination from older placement seasons. |
| **Automated Fact Verification** | DeBERTa-v3 Cross-Encoder Trust Layer (`src/trust_layer.py`). | Labels outputs with a verifiable Trust Score and flags contradictions in red, mitigating risks of miscommunicating eligibility criteria. |

---

### ❌ Disabilities (Critical Gaps & Bottlenecks)

1. **Zero Access Control & User Roles (Critical Security Risk)**:
   - There is **no authentication (RBAC)**. Anyone with network access to the server can view administrative data.
   - The `/api/reset_db` endpoint allows anyone to wipe the entire database and delete all uploaded documents with a single unauthenticated HTTP POST request.
2. **Read-Only / No Transactional Updates**:
   - The system cannot update records via conversational prompts. A placement officer cannot say *"Mark STU004 as Placed in Infosys with 9.5 LPA"*. All updates require manual spreadsheet editing and re-uploading.
3. **No Multi-File Relational Joins across Spreadsheets**:
   - If `Students.xlsx` contains `Student_ID` and `Drives.xlsx` contains company criteria, the LLM cannot reliably perform cross-file multi-sheet joins unless they are pre-merged into a unified database or single workbook.
4. **Hardware Bottlenecks on High-Volume Days**:
   - Local LLM inference (e.g., `qwen2.5-coder` 7B or 14B) on consumer hardware handles roughly 1 query sequentially. During peak placement hours with dozens of staff members querying simultaneously, local queueing will cause server timeouts.
5. **No Auditing or Query History Logs**:
   - The department cannot audit which user accessed specific student files or keep an audit trail of shortlisted candidates generated by the model.

---

## 3. Perspective 2: The Students (Candidates / Applicants)

Students require instant, transparent clarity regarding recruitment schedules, company eligibility, test venues, and personal offer statuses.

### ✅ Abilities (Student-Centric Benefits)

| Feature | Technical Implementation | Practical Value for Students |
| :--- | :--- | :--- |
| **Instant Policy & Criteria Clarification** | Semantic RAG + layout-preserving PDF table parsing (`pypdf` layout mode). | Students can ask complex policy questions (e.g., *"Can a student with an active backlog in semester 5 sit for Tier-1 companies?"*) and receive exact answers with cited source pages. |
| **Hands-Free Multimodal Interaction** | Voice Input (Windows Dictation `Win+H` trigger) + Web Speech Audio Playback. | Provides accessibility for visually impaired students and allows rapid voice queries without manual typing. |
| **Academic Grading System Awareness** | Pre-prompt system instructions explicitly define university grade scales (`O=10`, `A+=9`, `F=0`). | Prevents LLMs from confusing letter grades like `'O'` with zero or treating `'F'` as a passing grade. |
| **Auditable Answer Transparency** | Citation Cards with real-time relevance percentage and exact extracted context snippets. | Prevents confusion: a student can see the exact row or policy clause the AI used to determine their eligibility or venue allotment. |
| **Direct Model Tuning & Top-K Control** | Configurable Top-K (2, 4, 6, 8 passages) and model selection dropdown in `templates/index.html`. | Advanced students can adjust retrieval depth if their question requires wider document context. |

---

### ❌ Disabilities (Student User Experience Drawbacks)

1. **Severe Student Privacy Exposure (Data Leakage)**:
   - Because all ingested files reside in a shared vector/SQL space, any student can query private details of their peers:
     - *"What is Rohan Gupta's CGPA and how many backlogs does he have?"*
     - *"Which students were rejected in the technical interview round?"*
   - There is no student-level data masking or profile isolation.
2. **Stateless Querying (No Follow-Up / Conversation Memory)**:
   - The chat interface is strictly single-turn. If a student asks *"Which companies are hiring CSE students tomorrow?"* and follows up with *"What is their package?"*, the system forgets the prior question and fails or gives a generic response.
3. **Colloquial & Informal Language Fragility**:
   - Students frequently use campus slang: *"Am I eligible for Cognizant if I cleared my standing arrears last month?"*
   - If the query does not match the strict regex patterns in `is_aggregate_query()`, the system routes to semantic vector search rather than structured query execution. This can lead to partial or ungrounded answers.
4. **Desktop/OS-Bound Voice Features**:
   - The microphone trigger in `templates/index.html` relies on invoking Windows-native OS events via Win32 ctypes (`user32.keybd_event` for `Win+H`).
   - If students access the system from **smartphones (Android/iOS)**, **MacBooks**, or **Linux laptops**, the voice button will fail to trigger dictation.
5. **No Personalized Notification or Push Alerting**:
   - The system is passive pull-only. It cannot notify a student via Email, SMS, or Telegram when a new company matching their specific CGPA is uploaded.

---

## 4. Comprehensive Abilities vs. Disabilities Matrix

| Evaluation Dimension | Abilities (What Works Exceptionally Well) | Disabilities (What Fails or Is Missing) |
| :--- | :--- | :--- |
| **Security & Privacy** | Complete on-premise execution; no telemetry or data leakage to cloud providers. | Lack of authentication, authorization, RBAC, session management, and rate-limiting. Shared visibility of private student metrics. |
| **Tabular / Excel QA** | Hybrid SQL router overcomes standard RAG hallucination on counts, sums, averages, and extremes. Automatic header offset detection. | No multi-table relational foreign-key joins across independent workbooks; cannot perform data writes/edits. |
| **Text & Policy QA** | Header-preserving chunking; grade scale awareness; grounded zero-temperature inference. | Single-turn prompt context only; loses conversational continuity during interactive research. |
| **Trust & Verification** | Secondary NLI DeBERTa fact-checking flags false claims and calculates reliability scores. | Trust check adds latency (runs an extra local Cross-Encoder model); long sentences can yield neutral false-negatives. |
| **Voice & Accessibility** | Integrated STT triggering and browser-native TTS synthesis. | STT trigger relies on Windows Win32 API calls on the host machine; fails on mobile devices and non-Windows client browsers. |
| **Deployment & Scale** | Easy local launch via `run.bat` and lightweight Flask architecture. | Not production-ready for multi-user campus networks (Flask debug server, synchronous bottlenecks, no Redis task queue). |

---

## 5. Strategic Recommendations for Campus Deployment

To advance this project from an internal demonstration to an enterprise-grade University Placement Portal, the following phases are recommended:

### Phase 1: Security & Access Control (Immediate Priority)
- **Implement Role-Based Access Control (RBAC)**: Create two distinct portals:
  - *Admin/TPO Portal*: Document upload, schema inspection, database management, unrestricted queries.
  - *Student Portal*: Restricted queries scoped to public notices, general criteria, and their own individual student ID via session authentication.
- **Data Anonymization / Masking**: Strip or hash sensitive identifiers (phone numbers, full names, personal emails) before indexing tabular files for general search.
- **Secure Dangerous Endpoints**: Protect `/api/reset_db`, `/api/upload`, and `/api/delete_doc` behind admin session middleware.

### Phase 2: Conversational Memory & NLP Robustness
- **Add Multi-Turn Chat History**: Store conversation state per session ID and pass the last 3–5 dialogue turns into `build_rag_prompt()` so users can ask natural follow-up questions.
- **Broaden Intent Detection**: Supplement the regex router with a lightweight local zero-shot classification model to better capture informal student phrasing and campus vernacular.

### Phase 3: Cross-Platform & Infrastructure Upgrades
- **Standardize Web Speech API**: Replace the Windows-specific ctypes `Win+H` trigger with the browser-native `webkitSpeechRecognition` API, ensuring voice input functions smoothly across Chrome/Edge on Windows, macOS, Android, and iOS.
- **Production Server Deployment**: Wrap the Flask app in `Gunicorn` / `Waitress` behind an `Nginx` reverse proxy to allow concurrent student queries across the campus Wi-Fi network without crashing.
