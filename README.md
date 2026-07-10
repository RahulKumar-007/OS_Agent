# 🤖 AEGIS — Autonomous OS Intelligence Agent

Natural language → Plan → Safe execution on your entire desktop.  
Powered by **any local LLM** (LM Studio, Ollama, or any OpenAI-compatible API).  
**100% offline. No data leaves your machine.**

## UI

<img width="1920" alt="AEGIS UI" src="https://github.com/user-attachments/assets/9a0ced59-d3f4-4111-9f69-527591a50f4e" />

---

## ✨ Feature Overview

### Phase 1 — Core Intelligence
| Feature | Description |
|---------|-------------|
| 🧠 **AI Chat Agent** | Natural language → structured plan → user approval → safe execution |
| 🗂️ **File Explorer** | Full file manager: browse, search, create, move, copy, rename, trash, restore |
| 📄 **Document Understanding** | Summarize, explain, compare, extract tables (PDF, DOCX, XLSX, PPTX, images) |
| 🖼️ **Image Intelligence** | Describe, OCR, find similar, search by description |
| 🔐 **Security & Privacy** | Sensitive data detection, AES-256 encryption, secure delete, permission management |
| 🔍 **Advanced Search** | Full-text, semantic, code-aware, document-internal, FTS5-indexed instant search |
| 🌿 **Git Integration** | status, add, commit, diff, log, branch, checkout, push, pull |
| 💻 **Interactive Terminal** | Full PTY shell via xterm.js — nano, htop, git — all work |
| 🌐 **Web Intelligence** | DuckDuckGo search + BeautifulSoup scraper |
| 📊 **System Monitor** | CPU/core, RAM, Disk I/O, Network, GPU (nvidia-smi), process tree |
| 🔢 **Multi-Step Reasoning** | Auto-chains: search → filter → act. No file paths needed |

### Phase 2 — OS Assistant
- Desktop Automation (WindowManager, Clipboard, Notify)
- App Integrations (VS Code, Docker, HTTP, SQLite, apt/pip)
- Local Scheduler (cron-like SQLite backend)
- Personal Knowledge Base (Markdown-based local wiki)

### Phase 3 — Voice & Audio Intelligence
- 100% Offline Speech-to-Text (`faster-whisper` / `openai-whisper`)
- Offline Text-to-Speech (`pyttsx3` / `espeak`)
- Audio Metadata Extraction (`ffprobe` / `mutagen`)
- Batch transcription and audio library management
| Feature | Description |
|---------|-------------|
| 🖥️ **Desktop Control** | Clipboard R/W + history, screenshots (full/window/region), native notifications, window management (list/focus/minimize/maximize/close), monitor detection |
| 🔌 **App Plugins** | VS Code open/jump-to-line, Docker (list/start/stop/exec/logs), Package managers (apt/pip/npm/snap/flatpak), HTTP API tester, SQLite query interface |
| ⏰ **Task Scheduler** | SQLite-persisted cron-like jobs: interval, one-shot datetime, or manual. Actions: shell, agent task, desktop notification. Full run history |
| 📚 **Knowledge Base** | Personal markdown wiki with FTS5 search, tag/project organization, backlinks, YAML frontmatter, import arbitrary text |
| ⚡ **Performance Layer** | TTL+LRU metadata cache (5000 entries), parallel async directory scanner (8 workers) |
| ⚙️ **Config Management** | Dotfile enumeration, installed package export, safe env var inspection |

---

## 🚀 Quick Start

### 1. Run Setup
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
- **Ollama**: `ollama serve` → `ollama pull gemma3:4b`

### 5. (Optional) Desktop Tools
For clipboard, screenshots, notifications, and window management:
```bash
sudo apt install xclip scrot wmctrl xdotool libnotify-bin x11-xserver-utils
```

---

## 🏗️ Architecture

```
User (Browser)
    │
    ▼
Frontend (HTML/CSS/JS)   ←──── WebSocket for real-time updates
    │
    ▼
FastAPI Backend (port 8000)
    ├── Agent Planner   →  Local LLM  →  Structured JSON plan
    ├── Agent Executor  →  Policy Engine  →  Tool Runtime
    ├── Synthesizer     →  LLM post-processor for results
    │
    ├── Tools (20 modules, 100+ tools)
    │     ├── file_tools, fileops_tools, navigation_tools
    │     ├── search_tools, index_tools, extraction_tools
    │     ├── document_understanding_tools, image_understanding_tools
    │     ├── security_tools, git_tools, terminal_tools
    │     ├── system_tools, web_tools, exif_tools
    │     ├── desktop_tools   ← Phase 2
    │     └── plugin_tools    ← Phase 2
    │
    ├── Services
    │     ├── scheduler/   ← SQLite-backed task scheduler
    │     ├── knowledge/   ← Markdown wiki + FTS5
    │     ├── cache/       ← TTL+LRU in-memory caches
    │     ├── indexing/    ← Background FTS filesystem index
    │     └── memory/      ← User preferences store
    │
    └── Permissions (policy.py) — deny rules always win
```

---

## 📁 Project Structure

```
OS_Agent/
├── backend/
│   ├── agent/
│   │   ├── planner.py          # NL → JSON plan via LLM
│   │   ├── executor.py         # Runs approved plans step-by-step
│   │   └── synthesizer.py      # LLM post-processes raw results
│   ├── api/
│   │   └── routes.py           # All REST + WebSocket endpoints
│   ├── tools/
│   │   ├── base.py             # Tool interface & registry
│   │   ├── file_tools.py       # Core filesystem operations
│   │   ├── fileops_tools.py    # Batch ops, compress, organize
│   │   ├── navigation_tools.py # Browse, common folders
│   │   ├── search_tools.py     # FTS, semantic, code, document search
│   │   ├── extraction_tools.py # PDF/Office/OCR text extraction
│   │   ├── document_understanding_tools.py  # AI doc analysis
│   │   ├── image_understanding_tools.py     # AI image analysis
│   │   ├── security_tools.py   # Encryption, audit, sensitive data
│   │   ├── git_tools.py        # Git integration
│   │   ├── terminal_tools.py   # Shell command execution
│   │   ├── system_tools.py     # CPU/RAM/disk/network/GPU/processes
│   │   ├── web_tools.py        # Web search & scrape
│   │   ├── exif_tools.py       # Photo EXIF metadata
│   │   ├── index_tools.py      # FTS5 index management
│   │   ├── duplicate_tools.py  # Hash & dedup
│   │   ├── desktop_tools.py    # ← Phase 2: clipboard/screenshot/windows
│   │   ├── plugin_tools.py     # ← Phase 2: VS Code/Docker/packages/HTTP/SQLite
│   │   └── voice_tools.py      # ← Phase 3: Offline STT/TTS (Whisper/pyttsx3)
│   ├── scheduler/
│   │   └── scheduler.py        # ← Phase 2: SQLite-backed task scheduler
│   ├── knowledge/
│   │   └── kb.py               # ← Phase 2: Personal markdown wiki
│   ├── cache/
│   │   └── cache.py            # ← Phase 2: TTL+LRU cache layer
│   ├── indexing/
│   │   ├── indexer.py          # Background filesystem indexer
│   │   └── index_store.py      # FTS5 SQLite store
│   ├── permissions/
│   │   └── policy.py           # Allow/deny path validation
│   ├── llm/
│   │   └── client.py           # OpenAI-compatible LLM client
│   ├── memory/
│   │   └── memory_store.py     # Persistent user preferences
│   ├── database/
│   │   └── models.py           # SQLite schema & init
│   ├── config.yaml             # All configuration
│   ├── main.py                 # FastAPI app entry point
│   └── requirements.txt
├── frontend/
│   ├── index.html              # All pages (chat, explorer, monitor, terminal…)
│   ├── styles.css              # Full design system
│   └── app.js                  # All frontend logic
├── setup.sh
└── README.md
```

---

## ⚙️ LLM Configuration

Edit `backend/config.yaml` or use the **Settings** page in the UI:

```yaml
llm:
  provider: "lmstudio"           # lmstudio | ollama | openai_compatible
  base_url: "http://localhost:1234/v1"
  model: "gemma-3-4b-it"         # Your loaded model name
  temperature: 0.3
  max_tokens: 4096
```

| Provider | Default URL | Notes |
|----------|-------------|-------|
| LM Studio | `http://localhost:1234/v1` | Load any GGUF model |
| Ollama | `http://localhost:11434/v1` | `ollama pull <model>` first |
| OpenAI-compatible | Varies | vLLM, text-generation-webui, etc. |

---

## 🔌 API Reference

### Core Agent
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Natural language → plan |
| POST | `/api/approve` | Approve & execute plan |
| POST | `/api/reject/{id}` | Reject plan |
| GET | `/api/tasks` | Task history |
| GET | `/api/tasks/{id}` | Task detail + executions |
| GET/PUT | `/api/settings/llm` | LLM config |
| GET | `/api/settings/llm/health` | LLM health check |
| GET/PUT | `/api/permissions` | Path allow/deny rules |
| GET/POST/DELETE | `/api/memory` | Agent memory store |
| GET | `/api/tools` | List all registered tools |
| WS | `/ws` | Real-time plan/execution updates |
| WS | `/ws/terminal` | Interactive PTY shell |

### File Explorer
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/browse` | List directory contents |
| GET | `/api/browse/info` | Directory summary |
| GET | `/api/browse/common-folders` | Home, Documents, Downloads… |
| GET/POST/DELETE | `/api/bookmarks` | Folder bookmarks |
| GET/POST | `/api/recent-folders` | Recent navigation history |
| POST | `/api/open` | Open file with default app |
| GET | `/api/preview` | Preview text file content |
| POST | `/api/fileop/*` | create-file, create-folder, rename, copy, move, trash, delete, compress, extract, restore, organize-by-extension, organize-by-date, organize-by-ai, batch-move, delete-duplicates |

### Search & Indexing
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/search` | Advanced metadata search |
| POST | `/api/search/content` | Grep inside file content |
| POST | `/api/search/documents` | Search inside PDFs/Office/OCR |
| POST | `/api/search/semantic` | LLM-powered semantic search |
| POST | `/api/search/code` | Code-aware repo search |
| POST | `/api/extract/text` | Extract text from document |
| POST | `/api/extract/batch` | Batch extract from directory |
| GET | `/api/index/status` | FTS index status |
| POST | `/api/index/rebuild` | Rebuild filesystem index |
| GET | `/api/index/search` | Instant indexed filename search |

### System Monitoring
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/system/metrics` | CPU/RAM/disk/network/GPU |
| GET | `/api/system/processes` | Process list or tree |
| POST | `/api/system/kill` | Kill process by PID |
| GET | `/api/system/connections` | Active network connections |

### Web Intelligence
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/web/search` | DuckDuckGo search |
| POST | `/api/web/scrape` | Fetch & extract page content |

### 🖥️ Desktop Control (Phase 2)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/desktop/clipboard` | Read clipboard content |
| POST | `/api/desktop/clipboard` | Write text to clipboard |
| GET | `/api/desktop/clipboard/history` | In-session copy history |
| POST | `/api/desktop/screenshot` | Full/window/region screenshot |
| POST | `/api/desktop/notify` | Native desktop notification |
| GET | `/api/desktop/windows` | List all open windows |
| GET | `/api/desktop/windows/active` | Active window info |
| POST | `/api/desktop/windows/action` | Focus/minimize/maximize/close |
| GET | `/api/desktop/displays` | Monitor detection & resolution |

### 🔌 Plugins (Phase 2)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/plugin/vscode/open` | Open file/folder in VS Code |
| GET | `/api/plugin/docker/list` | List containers or images |
| POST | `/api/plugin/docker/action` | Start/stop/restart/remove/pull |
| GET | `/api/plugin/docker/logs` | Container logs |
| POST | `/api/plugin/docker/exec` | Exec command in container |
| POST | `/api/plugin/packages` | apt/pip/npm/snap/flatpak actions |
| POST | `/api/plugin/http` | HTTP API request tester |
| POST | `/api/plugin/sqlite/query` | Execute SQLite query |
| GET | `/api/plugin/sqlite/tables` | List tables & schemas |

### ⏰ Scheduler (Phase 2)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scheduler/jobs` | List all scheduled jobs |
| POST | `/api/scheduler/jobs` | Create a new job |
| GET | `/api/scheduler/jobs/{id}` | Get job details |
| PUT | `/api/scheduler/jobs/{id}` | Update job |
| DELETE | `/api/scheduler/jobs/{id}` | Delete job |
| POST | `/api/scheduler/jobs/{id}/run` | Trigger job immediately |
| GET | `/api/scheduler/jobs/{id}/runs` | Execution history |

### 📚 Knowledge Base (Phase 2)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/kb/notes` | List notes (filter by project/tag) |
| POST | `/api/kb/notes` | Create markdown note |
| GET | `/api/kb/notes/{id}` | Get note with content |
| PUT | `/api/kb/notes/{id}` | Update note |
| DELETE | `/api/kb/notes/{id}` | Delete note |
| GET | `/api/kb/notes/{id}/backlinks` | Find notes linking here |
| GET | `/api/kb/search` | Full-text search notes |
| GET | `/api/kb/projects` | List projects with counts |
| POST | `/api/kb/import` | Import arbitrary text as note |

### ⚡ Cache & Config (Phase 2)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/cache/stats` | Cache hit rates & sizes |
| DELETE | `/api/cache/clear` | Clear all caches |
| GET | `/api/config/dotfiles` | List dotfiles & config dirs |
| GET | `/api/config/installed-packages` | Export package list |
| GET | `/api/config/env` | Safe environment variables |

---

## 🛠️ Available Tools (100+)

### Desktop Environment
- `clipboard_read` — Read system clipboard
- `clipboard_write` — Write to clipboard, record history
- `clipboard_history` — In-session clipboard history
- `take_screenshot` — Full/window/region capture (scrot/gnome-screenshot/PIL)
- `desktop_notify` — Native `notify-send` notifications with urgency
- `list_windows` — All open windows via wmctrl/xdotool
- `focus_window` — Focus a window by title or ID
- `window_action` — Minimize/maximize/restore/close
- `get_active_window` — Currently focused window
- `display_info` — Monitor detection via xrandr

### Application Plugins
- `vscode_open` — Open file/folder in VS Code (code/codium/code-insiders)
- `vscode_run_command` — Send command via VS Code CLI
- `docker_list` — List containers or images (JSON formatted)
- `docker_action` — start/stop/restart/rm/pull
- `docker_logs` — Tail container logs
- `docker_exec` — Execute command inside container
- `package_manager` — apt/pip/npm/snap/flatpak: list/search/install/remove/update
- `http_request` — Full HTTP client (GET/POST/PUT/PATCH/DELETE + headers/body/auth)
- `sqlite_query` — Execute parameterized SQL on any .db file
- `sqlite_list_tables` — List tables + schemas

### Voice & Audio Intelligence (Phase 3)
- `transcribe_audio` — STT via local Whisper model (audio/video files)
- `batch_transcribe` — Directory-level mass transcription
- `text_to_speech` — Speak text aloud via pyttsx3 or espeak
- `save_speech_to_file` — Render TTS to a .wav audio file
- `audio_info` — Retrieve ID3 tags, codecs, duration via ffprobe/mutagen
- `list_audio_files` — Find all media files in a directory

### File Operations
- `list_directory`, `read_file_metadata`, `search_files`
- `advanced_search` — Multi-filter (name, ext, size, date, owner, fuzzy, regex)
- `move_file`, `copy_file`, `rename_file`, `delete_file`, `create_directory`
- `create_file`, `read_file_content`, `open_file`
- `compress_files`, `extract_archive`
- `trash_file`, `restore_from_trash`

### Batch Operations
- `batch_rename`, `batch_move`, `delete_duplicates`
- `organize_by_extension`, `organize_by_date`, `organize_by_ai`

### Search & Indexing
- `search_by_content` — Grep inside files
- `search_documents` — Inside PDFs/Office/OCR
- `semantic_search` — LLM-powered intent search
- `search_code` — Code-aware (skips node_modules, .git, etc.)
- `indexed_search` — Instant FTS5 filename search
- `rebuild_index`, `index_status`

### Document & Image AI
- `summarize_document`, `explain_document`, `compare_documents`
- `extract_tables`, `find_similar_documents`, `summarize_folder`
- `describe_image`, `ocr_image`, `find_similar_images`, `search_images_by_description`

### Security
- `view_permissions`, `edit_permissions`
- `detect_sensitive_files`, `encrypt_file`, `decrypt_file`, `secure_delete`
- `view_audit_log`

### System & Terminal
- `system_metrics` — CPU/RAM/Disk/Network/GPU
- `process_tree`, `network_connections`
- `terminal_session`, `terminal_history`
- `env_vars`, `kill_process`

### Git & Extraction
- `git_status`, `git_add`, `git_commit`, `git_diff`, `git_log`
- `git_branch`, `git_checkout`, `git_push`, `git_pull`
- `extract_document_text`, `batch_extract_text`
- `extract_exif`, `batch_rename_by_exif`
- `hash_file`, `find_duplicates`
- `web_search`, `web_scrape`

---

## 🔒 Permission System

The agent **cannot bypass** the policy engine. Configure in `config.yaml`:

```yaml
filesystem:
  allowed_paths:
    - "~/Downloads"
    - "~/Documents"
    - "~/Projects"
  denied_paths:
    - "~/.ssh"
    - "/etc"
    - "~/.gnupg"
```

- **Deny rules always win** over allow rules
- Destructive actions (`delete`, `move`, `encrypt`) require explicit user approval
- Every action is logged to SQLite for audit

---

## 🧠 Multi-Step Reasoning

The agent chains operations intelligently. You never need to know file paths.

```
You: "Run backend tests, open failing files in VS Code"

Agent plan:
  Step 1: terminal_session(command="cd ~/Projects/myapp && pytest --tb=short")
  Step 2: semantic_search(query="failed test file")
  Step 3: vscode_open(path=<result from step 2>)
```

```
You: "Every Friday, backup Documents and notify me"

Scheduler job:
  Trigger: interval (7d)
  Action:  shell("tar -czf ~/backups/docs-$(date +%F).tar.gz ~/Documents")
  + notify: "Backup complete"
```

```
You: "Remember our authentication architecture"

KB note created → next month →
You: "Explain our auth flow"
Agent: searches KB → finds note → explains it
```

See [MULTI_STEP_REASONING.md](MULTI_STEP_REASONING.md) for technical details.

---

## License

MIT
