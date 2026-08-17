# Local Database Question-Answering System 🤖🎙️

> **100% Offline, Privacy-Preserving Enterprise RAG System for Multi-Format Databases, Spreadsheets, & Official Documents.**  
> Powered by **Local Ollama LLMs**, **ChromaDB**, **Sentence Transformers**, and **Browser Web Speech API**.

Repository URL: `https://github.com/VRK1106/Local_Database_QA`

---

## 📌 Project Overview

The **Local Database QA System** is an enterprise-grade Retrieval-Augmented Generation (RAG) platform designed to operate **entirely offline** without sending sensitive corporate data or official documentation to third-party cloud APIs.

It provides **voice-enabled query input and text-to-speech answer readout**, allowing users to interact with heterogeneous database formats (PDFs, Excel spreadsheets, SQL databases, NoSQL JSON collections, and policy documents) via a modern Web Dashboard.

---

## ✨ Key Features

- 🔒 **100% Offline & Private**: Zero external cloud API calls or tracking. Powered by local Ollama models (`qwen2.5-coder`, `llama3`, `qwen2.5`).
- 🎙️ **Voice Query & Readout (STT & TTS)**:
  - **Speech-to-Text**: Real-time microphone audio input with a live Web Audio API volume level visualizer.
  - **Text-to-Speech**: Automated voice readout for generated answers.
- 📊 **Universal Multi-Format Ingestion Engine**:
  - **PDF Documents (`.pdf`)**: Layout preservation for multi-column tables, academic marksheets, and policy documents.
  - **Excel Spreadsheets (`.xlsx`, `.xls`)**: Hybrid CSV Preprocessing + Categorical Overview Summaries for 100% count accuracy on classroom/venue distributions.
  - **Relational SQL Databases (`.db`, `.sqlite`, `.sql`)**: Automated schema inspection and table row extraction.
  - **NoSQL & Structured JSON (`.json`, `.jsonl`, `.md`, `.txt`)**: Document collection and policy parsing.
- ⚙️ **Anti-Hallucination & Grounded Prompting**:
  - Enforces `temperature = 0.0` for deterministic outputs.
  - Injects academic grading scale definitions (`O`, `A+`, `A`, `B+`, `B`, `C`, `F`).
  - Enforces distinct location/venue separation (preventing accidental merging of `Classroom A` and `Classroom B`).

---

## 🛠️ System Prerequisites

1. **Operating System**: Windows 10/11, Linux, or macOS.
2. **Python**: Python 3.10 or higher.
3. **Local LLM Engine**: [Ollama Server](https://ollama.ai/) installed and running locally.
4. **Browser**: Google Chrome or Microsoft Edge (required for Web Speech API microphone access).

---

## 🚀 Quick Setup & Installation Guide

### Step 1: Clone the Repository
```bash
git clone https://github.com/VRK1106/Local_Database_QA.git
cd Local_Database_QA
```

### Step 2: Create & Activate Python Virtual Environment
**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\activate
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Required Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Install & Pull Local Ollama LLM Model
Ensure the Ollama service is running, then pull your model of choice:
```bash
# Recommended default model
ollama pull qwen2.5-coder

# Alternative compact model
ollama pull qwen2.5:1.5b
```

---

## 🖥️ Running the Application

### Option A: Using the Launcher Script (Windows)
Double-click `run.bat` or run:
```powershell
.\run.bat
```

### Option B: Running Directly via Python
```bash
python app.py
```

After starting the server, open your web browser and navigate to:
👉 **`http://127.0.0.1:5000`**

---

## 📁 Repository Structure

```
Local_Database_QA/
├── app.py                      # Flask Server & REST API endpoints
├── run.bat                     # Windows automatic environment & server launcher
├── requirements.txt            # Dependencies list (Flask, ChromaDB, SentenceTransformers, Pandas, OpenPyXL)
├── .gitignore                  # Git exclusion rules for venv, cache, and vector databases
├── README.md                   # System documentation & setup guide
├── create_sample_pilot_files.py# Generator script for sample pilot test suite
├── prepare_pilot_documents.py  # Pilot test suite document indexer
├── test_sql_nosql_demo.py      # Automated SQL, NoSQL & Excel verification suite
├── benchmark_excel_formats.py  # Excel embedding benchmark evaluation script
├── sample_pilot_documents/     # 📂 Sample Files for Pilot Testing
│   ├── Official_Enterprise_Policy.md  # Policy document (.md)
│   ├── Training_Venue_Schedule.xlsx   # Training schedule spreadsheet (.xlsx)
│   ├── company_records.db             # SQL Relational Database (.db)
│   └── users_nosql.json               # NoSQL Document Collection (.json)
├── src/                        # Core Application Modules
│   ├── ingest.py               # Multi-Format Extractor & Header-Preserving Chunker
│   ├── embeddings.py           # SentenceTransformer vector embedding generator
│   ├── vectorstore.py          # Local ChromaDB vector storage & similarity search engine
│   └── ollama_client.py        # Local Ollama HTTP API client & prompt constructor
├── templates/                  # Web Dashboard Interfaces
│   ├── base.html               # Base HTML layout with offline marked.js integration
│   └── index.html              # Main Chat Interface, Voice STT/TTS controls & QA parameters
├── static/                     # Offline Static Assets
│   └── js/marked.min.js        # 100% offline markdown renderer library
└── documents/                  # Default indexed document repository
```

---

## 🧪 Testing & Verification Suite

The repository includes automated scripts to verify system performance and ingestion accuracy:

### 1. Index Pilot Test Documents
Generates official policy documents, SQLite company records, and NoSQL JSON datasets:
```bash
python prepare_pilot_documents.py
```

### 2. Run Database & Excel Query Test Suite
Tests SQL database queries, NoSQL user profile queries, and PDF policy answers:
```bash
python test_sql_nosql_demo.py
```

### 3. Run Excel Format Benchmark
Evaluates CSV conversion, Markdown tables, JSON Lines, and Key-Value extraction efficiency:
```bash
python benchmark_excel_formats.py
```

---

## 📤 Pushing Changes to GitHub

If you are setting up the repository for the first time:

```bash
git init
git remote add origin https://github.com/VRK1106/Local_Database_QA.git
git add .
git commit -m "Initial commit of 100% Offline Local Database QA System"
git branch -M main
git push -u origin main
```

---

## 📝 License & Acknowledgments

- **Developed for**: Local Database QA Project Pitch & Official Demonstration.
- **Built with**: Flask, Ollama, ChromaDB, Sentence-Transformers, Pandas, PyPDF, OpenPyXL.
