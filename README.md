# Local Database Question-Answering & Issue Resolution System 🤖🎙️

> **100% Offline, Privacy-Preserving Enterprise RAG & Multi-Role Placement QA System.**  
> Powered by **Local Ollama LLMs**, **ChromaDB Vector Store**, **Sentence-Transformers**, **Dual-Path Structured SQL Engine**, and **Zero-Trust Role-Based Access Control (RBAC)**.

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/framework-Flask-black.svg)](https://flask.palletsprojects.com/)
[![ChromaDB](https://img.shields.io/badge/vector_db-ChromaDB-orange.svg)](https://www.trychroma.com/)
[![Ollama](https://img.shields.io/badge/LLM-Local_Ollama-darkgreen.svg)](https://ollama.ai/)
[![Tests](https://img.shields.io/badge/tests-32%2F32%20passing-brightgreen.svg)](test_resources/verify_all_features.py)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

---

## 📑 Table of Contents

- [Overview & Architecture](#-overview--architecture)
- [Key Features](#-key-features)
- [Pre-Configured Demo Accounts](#-pre-configured-demo-accounts)
- [Prerequisites for Beginners](#-prerequisites-for-beginners)
- [Quick Start Guide (Zero to Running in 3 Minutes)](#-quick-start-guide-zero-to-running-in-3-minutes)
  - [Option A: One-Click Automated Setup (Recommended)](#option-a-one-click-automated-setup-recommended)
  - [Option B: Step-by-Step Manual Setup](#option-b-step-by-step-manual-setup)
- [Running the Application](#-running-the-application)
  - [Development Mode (Flask)](#1-development-mode-flask)
  - [Production Mode (Multithreaded Waitress WSGI)](#2-production-mode-multithreaded-waitress-wsgi)
- [Testing & Quality Assurance](#-testing--quality-assurance)
- [Repository Structure](#-repository-structure)
- [Troubleshooting & Frequently Asked Questions (FAQ)](#-troubleshooting--frequently-asked-questions-faq)

---

## 🏛️ Overview & Architecture

The **Local Database QA System** is an air-gapped, privacy-first Retrieval-Augmented Generation (RAG) platform. It allows educational institutions and enterprises to query institutional databases, multi-sheet spreadsheets, PDFs, circulars, and student records **100% locally**—guaranteeing zero data leakage to external cloud APIs.

```
                           +------------------------------------------+
                           |           WEB BROWSER CLIENT             |
                           |   (Inter & Outfit Fonts, Dark Glass UI)  |
                           +--------------------+---------------------+
                                                |
                                      HTTP / SSE Stream
                                                |
                                                v
                           +------------------------------------------+
                           |          FLASK APPLICATION SERVER        |
                           |       (RBAC, Scopes & Audit Guards)      |
                           +---+--------------------+-------------+---+
                               |                    |             |
           +-------------------+                    |             +--------------------+
           |                                        |                                  |
           v                                        v                                  v
+----------------------+         +-----------------------+         +-----------------------+
|  STUDENT ROW-LEVEL   |         |    CHROMA VECTOR DB   |         |   LOCAL OLLAMA ENGINE |
|  ISOLATION (SQLITE)  |         | (all-MiniLM-L6-v2)    |         | (qwen2.5-coder / etc) |
| - Verified USN Scope |         | - Public Circulars    |         | - Temperature 0.0     |
| - Aggregate Blocker  |         | - Internal Policy     |         | - SSE Token Streaming |
+----------------------+         +-----------------------+         +-----------------------+
```

---

## ✨ Key Features

### 1. Three-Tier Zero-Trust Role-Based Access Control (RBAC)
- 🎓 **Student Persona (`stu001`)**:
  - **Zero-Trust Row-Level Isolation**: Automatically parameterizes all queries to the student's bound Student ID (`STU001`).
  - **Cross-Student Attack Guard**: Aggregate queries across peers (*"Show me everyone with CGPA > 8.0"*) are blocked with an institutional privacy notice.
  - **Document Masking**: Strictly restricted to documents tagged as `Public`. Internal staff memos are inaccessible.
  - **Personal Profile Drawer**: Displays student's live CGPA, branch, and placement status from official spreadsheets.
- 📋 **Placement Coordinator Persona (`admin`)**:
  - **User-Friendly Preset Controls**: Simplified Q&A parameters (*Response Style: Concise / Balanced / Detailed*, *Search Depth: Standard / Deep*).
  - **Document Manager**: Upload, inspect vector chunks, and toggle document visibility (`Public` vs. `Internal`).
  - **Audit Log Segregation**: Developer operations are strictly hidden from placement officer audit trails.
  - **Student Account Controls**: Reset student passwords and manage access. Developer accounts are shielded from view.
- 💻 **Engineering Developer Persona (`dev_admin`)**:
  - **Full Control Center**: Real-time telemetry, vector chunk counts, Ollama connectivity, and raw engineering sliders (*Temperature, Top-P, Top-K, System Prompt Override*).
  - **Developer View-As (Impersonation)**: Test the exact student or coordinator experience with automatic **Safe Permission Drop** and an exit banner.
  - **Danger Zone with Triple Confirmation**: Purge and re-index vector collections protected by password re-auth, exact uppercase `RESET` confirmation token, and mandatory 10+ character audit reason.
  - **Immutability Safeguard**: Backend rules prevent accidental demotion or disabling of the last developer account.

### 2. Multi-Role Ticket-Based Issue Resolution System
- Connects **Students $\leftrightarrow$ Placement Coordinators $\leftrightarrow$ Developers**.
- **Issue Categories**: Academic Record / CGPA Discrepancies, Placement Drive Eligibility, Vector DB Sync, Hallucination Reports, Portal Login Issues.
- **Privacy Guard**: Coordinators and Developers can post **Staff Internal Notes** (`is_internal_note=1`) which are strictly invisible to students.
- **Verified Student Roster Drawer**: Automatically attaches verified academic records to tickets matching a student ID.
- **Lifecycle Management**: `Open` $\rightarrow$ `In Progress` $\rightarrow$ `Resolved` (with official resolution notes) $\rightarrow$ `Closed`. Reopens automatically if student replies to a resolved ticket.

### 3. Voice Typing & Modern UI Aesthetics
- **Windows Dictation Integration**: Native `Win+H` trigger via microphone button for speech typing.
- **Modern Glassmorphic Interface**: Custom dark-mode UI with smooth micro-animations and typography (`Outfit` and `Inter`).
- **Auto-Hiding Sidebar**: Collapses off-screen to preserve screen space; slides out on hovering over the hamburger button (☰).
- **Navigation Controls**: In-app **🏠 Home**, **◀ Back**, and **▶ Forward** history buttons.
- **Browser Tab Favicon**: High-resolution vector icon (`favicon.svg`, `favicon.png`, `favicon.ico`).

---

## 👥 Pre-Configured Demo Accounts

The application automatically seeds three demo accounts upon first startup:

| Role | Username | Password | Student ID | Intended Access Level |
| :--- | :--- | :--- | :--- | :--- |
| **Student** | `stu001` | `Password@123` | `STU001` | Personal placement profile, public circulars, personal support tickets. |
| **Placement Coordinator** | `admin` | `admin123` | *None* | Institutional analytics, document uploads, student account management, issue triage. |
| **Developer** | `dev_admin` | `DeveloperPass@1234` | *None* | Full telemetry, raw parameters, Danger Zone, View-As impersonation, technical ticket resolution. |

---

## 🛠️ Prerequisites for Beginners

Before installing, make sure your computer has the following tools installed:

1. **Python 3.10 or higher**:
   - Download from [python.org](https://www.python.org/downloads/).
   - ⚠️ **Important (Windows)**: During Python installation, make sure to check the box:  
     ☑️ **"Add Python to PATH"**.
2. **Git**:
   - Download from [git-scm.com](https://git-scm.com/).
3. **Ollama (Local LLM Server)**:
   - Download and install from [ollama.ai](https://ollama.ai/).
   - Start Ollama and pull the recommended model checkpoint:
     ```bash
     ollama pull qwen2.5-coder:latest
     ```

---

## 🚀 Quick Start Guide (Zero to Running in 3 Minutes)

### Option A: One-Click Automated Setup (Recommended)

#### On Windows:
1. Open PowerShell or Command Prompt.
2. Clone the repository and navigate into the folder:
   ```cmd
   git clone https://github.com/VRK1106/Local_Database_QA.git
   cd Local_Database_QA
   ```
3. Run the automated setup wizard:
   ```cmd
   setup.bat
   ```
   *(This automatically creates `.venv`, installs all dependencies, initializes the database, and verifies default accounts.)*
4. Start the application:
   ```cmd
   run.bat
   ```
5. Open your web browser and navigate to:  
   👉 **`http://127.0.0.1:5000`**

#### On Linux / macOS:
```bash
git clone https://github.com/VRK1106/Local_Database_QA.git
cd Local_Database_QA
chmod +x setup.sh run.sh
./setup.sh
./run.sh
```

---

### Option B: Step-by-Step Manual Setup

If you prefer to configure everything manually step-by-step:

#### 1. Clone the Repository
```bash
git clone https://github.com/VRK1106/Local_Database_QA.git
cd Local_Database_QA
```

#### 2. Create and Activate a Python Virtual Environment
- **Windows (PowerShell):**
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\activate
  ```
- **Linux / macOS:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

#### 3. Install Production Dependencies
```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

#### 4. Configure Environment Variables (Optional)
Copy the template `.env.example` to `.env`:
```bash
# On Windows
copy .env.example .env

# On Linux/macOS
cp .env.example .env
```

#### 5. Verify Database Initialization
Run the initialization check:
```bash
python -c "from src.auth import init_auth_db; init_auth_db()"
```

#### 6. Ensure Ollama Model is Downloaded
```bash
ollama pull qwen2.5-coder:latest
```

---

## 🖥️ Running the Application

### 1. Development Mode (Flask)
Ideal for debugging, local testing, and template hot-reloading:
```bash
python app.py
```
*(Or simply double-click `run.bat` on Windows).*

### 2. Production Mode (Multithreaded Waitress WSGI)
For a robust, production-grade deployment with multithreading and no development server warnings:
```bash
python run_production.py
```
- Listens on `http://127.0.0.1:5000` (and `http://0.0.0.0:5000` across your local network).
- Configurable worker thread count (Default: `WAITRESS_THREADS=8`).

---

## 🧪 Testing & Quality Assurance

The repository includes a comprehensive testing and verification suite in [`test_resources/`](test_resources):

### 1. Live Integration Test Suite (All 32 Features)
Verify every feature end-to-end against the running server in ~5 seconds:
```bash
python test_resources/verify_all_features.py
```
**Verification Scope:**
- Module 1: Authentication & unauthenticated redirect gates
- Module 2: Student portal, profile drawer, personal Q&A & Zero-Trust aggregate blocking
- Module 3: Placement Coordinator document upload, audit log segregation & user management
- Module 4: Developer control center, View-As impersonation & Danger Zone triple confirmation
- Module 5: Ticket-based issue resolution, staff internal notes & resolution lifecycle
- Module 6: Voice typing API & custom 404 error handling

### 2. Penetration & Security Suite (All 30 Tests)
To run the automated penetration and role immutability suite:
```bash
python test_rbac_security.py
```

### 3. Manual Testing Resources
Inspect the dedicated testing folder [`test_resources/`](test_resources):
- [`test_resources/FEATURE_VERIFICATION_GUIDE.md`](test_resources/FEATURE_VERIFICATION_GUIDE.md): Step-by-step manual testing instructions with expected screenshots and behaviors.
- [`test_resources/test_documents/`](test_resources/test_documents):
  - `sample_public_placement_circular_2026.txt` (Public circular testing)
  - `sample_internal_placement_strategy_memo.txt` (Confidential staff memo testing)
  - `sample_batch_2026_roster_update.csv` (Student roster batch import testing)
- [`test_resources/test_queries.json`](test_resources/test_queries.json): Standard testing queries categorized by persona.

---

## 📁 Repository Structure

```
Local_Database_QA/
├── app.py                          # Main Flask Application & Route Controllers
├── run_production.py               # Production Multithreaded WSGI Server (Waitress)
├── run.bat                         # Windows 1-Click Application Launcher
├── run.sh                          # Linux/macOS Application Launcher
├── setup.bat                       # Windows Automated Beginner Setup Script
├── setup.sh                        # Linux/macOS Automated Beginner Setup Script
├── requirements.txt                # Pinned Production Python Dependencies
├── .env.example                    # Configuration Environment Template
├── .gitignore                      # Git Exclusion Rules
├── test_rbac_security.py           # 30-Test Penetration & Security Suite
│
├── src/                            # Core Backend Modules
│   ├── auth.py                     # Authentication, Permissions Registry, Passwords & Audit
│   ├── tickets.py                  # Issue Resolution Engine & Lifecycle Management
│   ├── scopes.py                   # Zero-Trust QueryScope Abstractions
│   ├── structured_query.py         # Dual-Path SQL Extractor & Multi-Sheet Excel Engine
│   ├── vectorstore.py              # ChromaDB Vector Store & Visibility Tagging
│   ├── embeddings.py               # Sentence-Transformers Embedding Pipeline
│   ├── ingest.py                   # Multi-Format File Parser (PDF, DOCX, XLSX, CSV, TXT)
│   ├── ollama_client.py            # Local Ollama Streaming Client & Anti-Hallucination
│   ├── trust_layer.py              # Hallucination Claim Verification Layer
│   ├── config.py                   # Path and Environment Configuration
│   └── cli.py                      # Administrative CLI Commands (create-developer)
│
├── templates/                      # Modern Dark Glassmorphic Jinja2 Templates
│   ├── base.html                   # Global Shell, Navigation Panel & Sticky Impersonation Banner
│   ├── index.html                  # Main Q&A Studio (Dual persona parameters, Voice, Streaming)
│   ├── login.html                  # Secure Sign-In Interface
│   ├── profile.html                # User Profile & Verified Student Roster Snapshot
│   ├── settings.html               # Accessibility & UI Preferences
│   ├── documents.html              # Document Ingestion, Visibility Tagging & Vector Inspector
│   ├── admin_users.html            # Placement Coordinator Student Management & CSV Batch Import
│   ├── audit_logs.html             # Role-Segregated Immutable Security Audit Trail
│   ├── system_info.html            # Model Diagnostics & Hardware Status
│   ├── dev/                        # Developer Portal Views
│   │   ├── dashboard.html          # Engineering Telemetry & Vector Chunk Counts
│   │   ├── danger.html             # Protected Danger Zone (Triple Confirmation DB Wipe)
│   │   ├── users.html              # Global User & Developer Role Management
│   │   └── config.html             # Runtime Model Parameters & System Constants
│   ├── tickets/                    # Issue Resolution Views
│   │   ├── list.html               # Filterable Issue Dashboard with 4 KPI Summary Cards
│   │   └── view.html               # Threaded Discussion, Internal Notes & Student Snapshot
│   └── errors/                     # Custom Error Pages
│       ├── 403.html                # Access Denied / Safe Permission Drop Screen
│       ├── 404.html                # Not Found Screen
│       └── 500.html                # Internal Server Error Screen
│
├── static/                         # Static Assets
│   ├── favicon.svg                 # High-Res Modern Vector Favicon
│   ├── favicon.ico                 # Fallback Browser Favicon
│   ├── favicon.png                 # Retina PNG Favicon
│   └── js/marked.min.js            # 100% Offline Markdown Renderer
│
├── documents/                      # Uploaded & Ingested Document Storage
│   └── Mock_Placement.xlsx         # Official Student Benchmark Dataset
│
├── test_resources/                 # Systematic QA & Verification Suite
│   ├── verify_all_features.py      # Automated 32-Feature Verification Script
│   ├── CREDENTIALS_AND_ACCOUNTS.md # Demo Credentials Reference Sheet
│   ├── FEATURE_VERIFICATION_GUIDE.md # Manual QA Testing Guide
│   ├── test_queries.json           # Categorized Persona Test Prompts
│   └── test_documents/             # Sample Verification Documents (Public, Internal, CSV)
│
└── docs/                           # Architecture Specifications & Implementation Reports
    ├── Developer_Role_and_Portal_Abstraction.md
    ├── Flawless_RBAC_Execution_Plan.md
    ├── Placement_QA_System_Evaluation_Report.md
    ├── RBAC_Implementation_Plan.md
    └── Walkthrough_Student_Portal_and_Features.md
```

---

## ❓ Troubleshooting & Frequently Asked Questions (FAQ)

### Q1: The server starts, but queries say "Ollama Offline" or fail to answer.
- **Cause**: The Ollama background process is not running, or the model hasn't been pulled.
- **Solution**:
  1. Open a new terminal and start Ollama:
     ```bash
     ollama serve
     ```
  2. Verify that your model is downloaded:
     ```bash
     ollama list
     ```
  3. If missing, download it:
     ```bash
     ollama pull qwen2.5-coder:latest
     ```

### Q2: Port 5000 is already in use (`Address already in use` error).
- **Cause**: Another service (or an earlier instance of Python) is running on port 5000.
- **Solution**: Change the port by setting the `PORT` environment variable:
  - **Windows (PowerShell):**
    ```powershell
    $env:PORT="5050"; python run_production.py
    ```
  - **Linux / macOS:**
    ```bash
    PORT=5050 python3 run_production.py
    ```

### Q3: When I click the microphone button, voice typing does not start.
- **Cause**: Windows Dictation requires Windows 10/11 with speech typing enabled.
- **Solution**: Press **`Win + H`** on your keyboard once to allow Windows to download the speech typing language pack if prompted. The web microphone button triggers this same shortcut automatically.

### Q4: How do I create a new Developer account from the terminal?
- **Solution**: Use the built-in Flask CLI command:
  ```bash
  flask create-developer
  ```
  Follow the interactive prompts to enter the new username and secure password.

### Q5: Can I reset the database back to clean demo state?
- **Solution**: Log in as `dev_admin`, navigate to **Control Center** $\rightarrow$ **Danger Zone** (`/dev/danger`), enter your developer password, type `RESET` in capital letters, provide a reason (*e.g. "Clean demo reset"*), and confirm.

---

## 📄 License & Attribution

- **Project Pitch**: Infosys Springboard Local Database Question-Answering Project.
- **Built With**: Python, Flask, ChromaDB, Sentence-Transformers, Pandas, PyPDF, Waitress, Ollama.
- **License**: MIT Open Source License.
