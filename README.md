# 🗂️ FileAgent — Local Filesystem Agent

Natural language → Plan → Safe execution on your files.  
Powered by **any local LLM** (LM Studio, Ollama, or any OpenAI-compatible API).

# UI
<img width="1920" height="962" alt="image" src="https://github.com/user-attachments/assets/9a0ced59-d3f4-4111-9f69-527591a50f4e" />


## ✨ New Features

### 🧠 Multi-Step Reasoning & Intelligent Path Resolution
- **No need to know file paths!** Just say "rename myfile.txt" and the agent:
  1. Searches for the file across your system
  2. Finds the exact path
  3. Performs the operation
- **Complex workflows**: "Move screenshots from last week into Images" → auto-plans multiple steps
- **Result chaining**: Steps automatically pass data to subsequent steps
- **Safe operations**: Always confirms file existence before destructive actions

### Document Understanding (AI)
- 📝 **Summarize** any document (PDF, Office, images via OCR)
- 🧠 **Explain** document content with detailed analysis
- 📊 **Extract tables** in markdown, JSON, or CSV format
- 🔄 **Compare documents** to find similarities and differences
- 🔍 **Find similar documents** using AI content analysis

### Image Understanding (AI)
- 🖼️ **Describe images** with AI-generated descriptions
- 🔤 **OCR** text extraction from images with preprocessing
- 🔍 **Find similar images** using perceptual hashing
- 🔎 **Search images** by natural language description

### Security & Privacy
- 🔐 **View/edit permissions** - Manage file access control
- 🔍 **Detect sensitive data** - Scan for passwords, API keys, secrets
- 🔒 **Encrypt files** - AES-256 encryption with password
- 🗑️ **Secure delete** - Military-grade file wiping (DoD 5220.22-M)
- 📊 **Audit logging** - Complete operation history

---

## Quick Start

### 1. Setup
```bash
chmod +x setup.sh && ./setup.sh
```

### 2. Start Backend
```bash
source backend/venv/bin/activate
cd backend && python main.py
```
Backend runs at `http://localhost:8000`

### 3. Start Frontend
```bash
python3 -m http.server 3000 --directory frontend
```
Open `http://localhost:3000`

### 4. Start Your LLM
- **LM Studio**: Load a model → Start server (default port 1234)
- **Ollama**: `ollama serve` (default port 11434)

---

## Architecture

```
Frontend (HTML/CSS/JS)  →  Agent API (FastAPI)  →  Planner (LLM)  →  Policy Engine  →  Tool Runtime  →  Filesystem
```

### Core Flow
1. **User types** natural language request
2. **Planner** sends to local LLM → gets structured JSON plan
3. **User reviews** plan with full step details
4. **User approves** (or rejects)
5. **Executor** runs each step through Policy Engine first
6. **Report** generated with full audit trail

---

## Project Structure

```
├── backend/
│   ├── agent/
│   │   ├── planner.py      # NL → JSON plan via LLM
│   │   └── executor.py     # Runs approved plans step-by-step
│   ├── api/
│   │   └── routes.py       # REST + WebSocket endpoints
│   ├── tools/
│   │   ├── base.py         # Tool interface & registry
│   │   ├── file_tools.py   # Filesystem operations
│   │   └── duplicate_tools.py  # Hash & dedup
│   ├── permissions/
│   │   └── policy.py       # Allow/deny path validation
│   ├── llm/
│   │   └── client.py       # OpenAI-compatible LLM client
│   ├── memory/
│   │   └── memory_store.py # Persistent user preferences
│   ├── database/
│   │   └── models.py       # SQLite schema & init
│   ├── config.yaml         # All configuration
│   ├── main.py             # FastAPI app entry point
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── setup.sh
└── README.md
```

---

## LLM Configuration

Edit `backend/config.yaml` or use the Settings page in the UI:

```yaml
llm:
  provider: "lmstudio"           # lmstudio | ollama | openai_compatible
  base_url: "http://localhost:1234/v1"
  model: "gemma-3-4b-it"         # Your loaded model name
  temperature: 0.3
  max_tokens: 4096
```

**Supported providers:**
| Provider | Default URL | Notes |
|----------|------------|-------|
| LM Studio | `http://localhost:1234/v1` | Load any GGUF model |
| Ollama | `http://localhost:11434/v1` | `ollama pull <model>` first |
| Any OpenAI-compatible | Varies | vLLM, text-generation-webui, etc. |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Send message → get plan |
| POST | `/api/approve` | Approve & execute plan |
| POST | `/api/reject/{id}` | Reject a plan |
| GET | `/api/tasks` | Task history |
| GET | `/api/tasks/{id}` | Task details |
| GET/PUT | `/api/settings/llm` | LLM configuration |
| GET | `/api/settings/llm/health` | LLM health check |
| GET/PUT | `/api/permissions` | Path permissions |
| GET/POST/DELETE | `/api/memory` | Agent memory |
| GET | `/api/tools` | Available tools |
| WS | `/ws` | Real-time updates |
| POST | `/api/search` | Advanced filename/metadata search |
| POST | `/api/search/content` | Grep-based content search |
| POST | `/api/search/documents` | Search inside document text (PDF, Office, OCR) |
| POST | `/api/search/semantic` | Natural language semantic search |
| POST | `/api/search/code` | Code repository search |
| POST | `/api/extract/text` | Extract text from a single document |
| POST | `/api/extract/batch` | Batch extract text from a directory |
| POST | `/api/fileop/batch-move` | Move multiple files matching a pattern |
| POST | `/api/fileop/delete-duplicates` | Find and delete duplicate files |
| POST | `/api/fileop/organize-by-ai` | Organize files using AI categorization |

---

## Available Tools

### File Operations
- `list_directory` — List files/folders with metadata
- `read_file_metadata` — Get file size, dates, permissions
- `search_files` — Glob pattern search
- `advanced_search` — Multi-filter search (name, extension, size, date, owner, hidden, fuzzy, regex, recursive)
- `search_by_content` — Search text inside files using grep
- `move_file` — Move file/directory
- `copy_file` — Copy file/directory
- `rename_file` — Rename file/directory
- `delete_file` — Delete (requires approval)
- `create_directory` — Create directories

### Document Extraction & Search
- `extract_document_text` — Extract text from PDFs, Office docs (DOCX, XLSX, PPTX), images (OCR), and code/text files
- `batch_extract_text` — Batch extract text from all supported documents in a directory
- `search_documents` — Search for text inside documents (PDFs, Office files, images via OCR, source code)

### Semantic Search
- `semantic_search` — Natural language search using LLM-powered query understanding and relevance ranking. Understands intent, not just keywords (e.g., "find invoices from last quarter")

### Code Repository Search
- `search_code` — Code-aware search across repositories. Filters by language, searches function/class names, comments, and code patterns. Automatically skips `node_modules`, `.git`, `build/`, etc.

### Advanced File Operations
- `create_file` — Create a new file with optional content
- `compress_files` — Compress files/directories into .zip or .tar.gz
- `extract_archive` — Extract .zip, .tar, .tar.gz archives
- `trash_file` — Move to system Trash (recoverable)
- `restore_from_trash` — List or restore files from Trash
- `open_file` — Open file with system default application
- `read_file_content` — Preview text file content

### Batch Operations
- `batch_rename` — Rename multiple files (sequential numbering, find-replace, prefix/suffix)
- `batch_move` — Move multiple files matching a pattern/extension to a target directory
- `delete_duplicates` — Find and delete duplicate files keeping one copy (dry-run by default)
- `organize_by_extension` — Organize files into subfolders by file extension category
- `organize_by_date` — Organize files into subfolders by modification date
- `organize_by_ai` — Organize files using LLM-powered AI categorization into smart folders

### Duplicate Detection
- `hash_file` — SHA-256 hash
- `find_duplicates` — Find duplicate files by hash

### Document Understanding (AI-Powered)
- `summarize_document` — Generate AI summaries of documents (PDF, DOCX, XLSX, PPTX, images, text)
- `summarize_folder` — AI summary of entire folder contents in seconds
- `explain_document` — Get detailed AI explanations of document content, purpose, and key concepts
- `extract_tables` — Extract and structure tables from documents in markdown, JSON, or CSV format
- `compare_documents` — Compare two documents to identify similarities, differences, and changes
- `find_similar_documents` — Find documents similar to a reference document using content analysis

### Image Understanding (AI-Powered)
- `describe_image` — Generate AI descriptions of images (objects, scenes, activities, composition)
- `ocr_image` — Extract text from images using OCR with preprocessing options
- `detect_objects` — Detect and identify objects in images (requires vision model)
- `find_similar_images` — Find visually similar images using perceptual hashing
- `search_images_by_description` — Search for images matching natural language descriptions

### Security & Privacy
- `view_permissions` — View detailed file/directory permissions (owner, group, rwx mode)
- `edit_permissions` — Change permissions using numeric (755) or symbolic (u+x) modes
- `detect_sensitive_files` — Scan for passwords, API keys, private keys, secrets in files
- `encrypt_file` — Encrypt files with AES-256 using password
- `decrypt_file` — Decrypt encrypted files with password
- `secure_delete` — Securely delete files with multi-pass overwrite (DoD 5220.22-M)
- `view_audit_log` — View audit log of all agent operations with filtering

### Git Integration
- `git_status` — Show working tree status
- `git_add` — Stage files for commit
- `git_commit` — Commit changes with message
- `git_diff` — Show file differences
- `git_log` — View commit history
- `git_branch` — List/create/delete branches
- `git_checkout` — Switch branches
- `git_push` — Push to remote
- `git_pull` — Pull from remote

### Terminal & System
- `terminal_session` — Execute shell commands
- `terminal_history` — View command history
- `process_list` — List running processes
- `kill_process` — Terminate process by PID
- `env_vars` — View environment variables

### Photo Management
- `extract_exif` — Extract EXIF metadata (date, camera, GPS)
- `batch_rename_by_exif` — Rename photos by date taken

---

## 🧠 Multi-Step Reasoning

The agent can chain multiple operations together intelligently. When you don't provide exact file paths, the agent **automatically searches first**, then operates on the results.

### Examples

**Simple Rename (Search → Rename)**
```
You: "Rename Bodyweight Progression .pdf to Bodyweight_Progression.pdf"

Agent creates plan:
  Step 1: semantic_search(query="Bodyweight Progression .pdf")
  Step 2: rename_file(old_path=<result from step 1>, new_name="Bodyweight_Progression.pdf")
```

**Organize Downloads (Search → Filter → Move)**
```
You: "Move all screenshots from last week into Images folder"

Agent creates plan:
  Step 1: advanced_search(path="~/Downloads", extensions=".png,.jpg", modified_after="7d")
  Step 2: batch_move(files=<results from step 1>, destination="~/Images/")
```

**Clean Old Files (Search → Filter → Delete)**
```
You: "Delete installers older than 6 months"

Agent creates plan:
  Step 1: advanced_search(path="~/Downloads", extensions=".exe,.dmg,.pkg", modified_before="6m")
  Step 2: batch_delete(files=<results from step 1>)
```

### How It Works

1. **Planner** detects when file paths are missing → adds search step
2. **Executor** runs search → stores results with `result_key` extraction
3. **Placeholder replacement**: `{{step_0}}` in args is replaced with search result path
4. **Dependent step** executes with actual file paths

See [MULTI_STEP_REASONING.md](MULTI_STEP_REASONING.md) for technical details.

---

## Permission System

The agent **cannot bypass** the policy engine. Configure in `config.yaml`:

```yaml
filesystem:
  allowed_paths:
    - "~/Downloads"
    - "~/Documents"
  denied_paths:
    - "~/.ssh"
    - "/etc"
```

- **Deny rules always win** over allow rules
- Destructive actions (`delete`, `move`) require explicit user approval
- Every action is logged to SQLite for audit

---

## License

MIT
