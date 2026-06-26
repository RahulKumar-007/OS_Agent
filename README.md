# 🗂️ FileAgent — Local Filesystem Agent

Natural language → Plan → Safe execution on your files.  
Powered by **any local LLM** (LM Studio, Ollama, or any OpenAI-compatible API).

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

---

## Available Tools

### File Operations
- `list_directory` — List files/folders with metadata
- `read_file_metadata` — Get file size, dates, permissions
- `search_files` — Glob pattern search
- `move_file` — Move file/directory
- `copy_file` — Copy file/directory
- `rename_file` — Rename file/directory
- `delete_file` — Delete (requires approval)
- `create_directory` — Create directories

### Duplicate Detection
- `hash_file` — SHA-256 hash
- `find_duplicates` — Find duplicate files by hash

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
