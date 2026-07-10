"""
API routes for the Local Filesystem Agent.
"""
import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
from pydantic import BaseModel

from agent.planner import Planner
from agent.executor import Executor
from agent.synthesizer import Synthesizer
from tools.base import registry
from permissions.policy import PolicyEngine
from llm.client import LLMClient
from memory.memory_store import MemoryStore
from database.models import get_db
from scheduler.scheduler import scheduler_service
from knowledge.kb import kb
from cache.cache import metadata_cache, search_cache


# ─── Pydantic models ───────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    task_id: Optional[str] = None


class ApproveRequest(BaseModel):
    task_id: str


class LLMConfigUpdate(BaseModel):
    provider: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class PermissionUpdate(BaseModel):
    allowed_paths: Optional[list] = None
    denied_paths: Optional[list] = None


class MemoryUpdate(BaseModel):
    key: str
    value: dict


# ─── Router ─────────────────────────────────────────────
router = APIRouter()

# These get injected by main.py
llm_client: LLMClient = None
policy_engine: PolicyEngine = None
memory_store: MemoryStore = None
planner: Planner = None
executor: Executor = None
synthesizer: Synthesizer = None


def init_dependencies(llm: LLMClient, policy: PolicyEngine, memory: MemoryStore):
    """Initialize route dependencies. Called from main.py."""
    global llm_client, policy_engine, memory_store, planner, executor, synthesizer
    llm_client = llm
    policy_engine = policy
    memory_store = memory
    planner = Planner(llm, registry)
    executor = Executor(registry, policy)
    synthesizer = Synthesizer(llm)


# ─── Chat / Task endpoints ─────────────────────────────
@router.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Main chat endpoint.
    Takes natural language → creates plan → returns plan for approval.
    """
    task_id = request.task_id or str(uuid.uuid4())

    # Get memory context
    context = {}
    try:
        memories = await memory_store.get_all()
        if memories:
            context["user_preferences"] = memories
    except Exception:
        pass

    # Create plan
    plan_result = await planner.create_plan(request.message, context=context or None)

    if not plan_result["success"]:
        raise HTTPException(status_code=500, detail=plan_result.get("error", "Planning failed"))

    plan = plan_result["plan"]

    # Store task in DB
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO tasks (id, user_input, goal, status, plan_json, created_at, updated_at)
               VALUES (?, ?, ?, 'awaiting_approval', ?, ?, ?)""",
            (
                task_id,
                request.message,
                plan.get("goal", ""),
                json.dumps(plan),
                datetime.now().isoformat(),
                datetime.now().isoformat(),
            ),
        )
        await db.commit()
    finally:
        await db.close()

    return {
        "task_id": task_id,
        "status": "awaiting_approval",
        "plan": plan,
        "usage": plan_result.get("usage", {}),
    }


@router.post("/api/approve")
async def approve_task(request: ApproveRequest):
    """Approve, execute, and synthesize a planned task."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE id = ?", (request.task_id,)
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        task = dict(row)
        if task["status"] != "awaiting_approval":
            raise HTTPException(
                status_code=400,
                detail=f"Task is not awaiting approval (status: {task['status']})",
            )

        plan = json.loads(task["plan_json"])
        user_input = task["user_input"]

        # Update status to executing
        await db.execute(
            "UPDATE tasks SET status='executing', updated_at=? WHERE id=?",
            (datetime.now().isoformat(), request.task_id),
        )
        await db.commit()
    finally:
        await db.close()

    # Execute tools
    report = await executor.execute_plan(request.task_id, plan)

    # Post-process through LLM synthesizer
    synthesis_result = await synthesizer.process(user_input, plan, report)
    synthesis = synthesis_result.get("synthesis", {})

    # Attach synthesis to the report
    report["synthesis"] = synthesis

    return {
        "task_id": request.task_id,
        "status": report["status"],
        "report": report,
    }


@router.post("/api/reject/{task_id}")
async def reject_task(task_id: str):
    """Reject a planned task."""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE tasks SET status='rejected', updated_at=? WHERE id=?",
            (datetime.now().isoformat(), task_id),
        )
        await db.commit()
    finally:
        await db.close()

    return {"task_id": task_id, "status": "rejected"}


# ─── Task History ───────────────────────────────────────
@router.get("/api/tasks")
async def list_tasks(limit: int = 50, offset: int = 0):
    """Get task history."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        tasks = []
        for row in rows:
            task = dict(row)
            task["plan_json"] = json.loads(task["plan_json"]) if task["plan_json"] else None
            task["result_json"] = json.loads(task["result_json"]) if task["result_json"] else None
            tasks.append(task)
        return {"tasks": tasks, "total": len(tasks)}
    finally:
        await db.close()


@router.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    """Get a specific task with its execution details."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        task = dict(row)
        task["plan_json"] = json.loads(task["plan_json"]) if task["plan_json"] else None
        task["result_json"] = json.loads(task["result_json"]) if task["result_json"] else None

        # Get executions
        cursor = await db.execute(
            "SELECT * FROM executions WHERE task_id = ? ORDER BY step_index",
            (task_id,),
        )
        exec_rows = await cursor.fetchall()
        task["executions"] = [dict(r) for r in exec_rows]

        return task
    finally:
        await db.close()


# ─── LLM Settings ──────────────────────────────────────
@router.get("/api/settings/llm")
async def get_llm_settings():
    """Get current LLM configuration."""
    return llm_client.get_config()


@router.put("/api/settings/llm")
async def update_llm_settings(config: LLMConfigUpdate):
    """Update LLM configuration at runtime."""
    updates = {k: v for k, v in config.model_dump().items() if v is not None}
    llm_client.update_config(**updates)
    return llm_client.get_config()


@router.get("/api/settings/llm/health")
async def llm_health():
    """Check LLM connection status."""
    return await llm_client.health_check()


# ─── Permissions ────────────────────────────────────────
@router.get("/api/permissions")
async def get_permissions():
    """Get current permission configuration."""
    return policy_engine.get_config()


@router.put("/api/permissions")
async def update_permissions(config: PermissionUpdate):
    """Update permission configuration."""
    if config.allowed_paths is not None:
        policy_engine.allowed_paths = [
            __import__("os").path.expanduser(p) for p in config.allowed_paths
        ]
    if config.denied_paths is not None:
        policy_engine.denied_paths = [
            __import__("os").path.expanduser(p) for p in config.denied_paths
        ]
    return policy_engine.get_config()


# ─── Memory ────────────────────────────────────────────
@router.get("/api/memory")
async def get_memories():
    """Get all stored memories."""
    return await memory_store.get_all()


@router.post("/api/memory")
async def set_memory(data: MemoryUpdate):
    """Set a memory value."""
    await memory_store.set(data.key, data.value)
    return {"key": data.key, "status": "saved"}


@router.delete("/api/memory/{key}")
async def delete_memory(key: str):
    """Delete a memory."""
    await memory_store.delete(key)
    return {"key": key, "status": "deleted"}


# ─── Tools ──────────────────────────────────────────────
@router.get("/api/tools")
async def list_tools():
    """List all available tools."""
    return {"tools": registry.list_tools()}


# ─── System Monitoring ──────────────────────────────────
@router.get("/api/system/metrics")
async def system_metrics():
    """Real-time CPU, RAM, disk, network, and GPU telemetry."""
    tool = registry.get("system_metrics")
    if not tool:
        raise HTTPException(status_code=503, detail="system_metrics tool not available")
    result = await tool.execute({})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


@router.get("/api/system/processes")
async def system_processes(tree: bool = False, limit: int = 200):
    """List running processes, optionally as a parent-child tree."""
    tool_name = "process_tree" if tree else "process_list"
    tool = registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=503, detail=f"{tool_name} tool not available")
    result = await tool.execute({"limit": limit})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


@router.post("/api/system/kill")
async def system_kill_process(pid: int, force: bool = False):
    """Terminate a process by PID."""
    tool = registry.get("kill_process")
    if not tool:
        raise HTTPException(status_code=503, detail="kill_process tool not available")
    result = await tool.execute({"pid": pid, "force": force})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


@router.get("/api/system/connections")
async def system_connections(kind: str = "inet", limit: int = 100):
    """List active network connections and listening ports."""
    tool = registry.get("network_connections")
    if not tool:
        raise HTTPException(status_code=503, detail="network_connections tool not available")
    result = await tool.execute({"kind": kind, "limit": limit})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


# ─── Filesystem Search Index ────────────────────────────
@router.get("/api/index/status")
async def index_status():
    """Status of the background filesystem search index."""
    tool = registry.get("index_status")
    if not tool:
        raise HTTPException(status_code=503, detail="index_status tool not available")
    result = await tool.execute({})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


@router.post("/api/index/rebuild")
async def index_rebuild():
    """Trigger a full background rebuild of the search index."""
    tool = registry.get("rebuild_index")
    if not tool:
        raise HTTPException(status_code=503, detail="rebuild_index tool not available")
    result = await tool.execute({})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


@router.get("/api/index/search")
async def index_search(q: str, limit: int = 50):
    """Instant filename search against the pre-built index."""
    tool = registry.get("indexed_search")
    if not tool:
        raise HTTPException(status_code=503, detail="indexed_search tool not available")
    result = await tool.execute({"query": q, "limit": limit})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


# ─── Web / Browser Integration ──────────────────────────
class WebSearchRequest(BaseModel):
    query: str
    max_results: int = 5


@router.post("/api/web/search")
async def web_search(request: WebSearchRequest):
    """Search the web (requires internet access)."""
    tool = registry.get("web_search")
    if not tool:
        raise HTTPException(status_code=503, detail="web_search tool not available")
    result = await tool.execute(request.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


class WebScrapeRequest(BaseModel):
    url: str
    max_length: int = 5000


@router.post("/api/web/scrape")
async def web_scrape(request: WebScrapeRequest):
    """Fetch and extract readable content from a web page (requires internet access)."""
    tool = registry.get("web_scrape")
    if not tool:
        raise HTTPException(status_code=503, detail="web_scrape tool not available")
    result = await tool.execute(request.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


# ─── File Browser (Navigation MVP) ──────────────────────
class SearchRequest(BaseModel):
    path: str
    query: Optional[str] = ""
    fuzzy: Optional[bool] = False
    regex: Optional[bool] = False
    extensions: Optional[str] = ""
    min_size: Optional[str] = ""
    max_size: Optional[str] = ""
    modified_after: Optional[str] = ""
    modified_before: Optional[str] = ""
    created_after: Optional[str] = ""
    created_before: Optional[str] = ""
    owner: Optional[str] = ""
    include_hidden: Optional[bool] = False
    include_dirs: Optional[bool] = False
    recursive: Optional[bool] = True
    max_results: Optional[int] = 200


class ContentSearchRequest(BaseModel):
    path: str
    content_query: str
    extensions: Optional[str] = ""
    case_sensitive: Optional[bool] = False
    regex: Optional[bool] = False
    max_results: Optional[int] = 50
    recursive: Optional[bool] = True


@router.get("/api/browse")
async def browse_directory(
    path: str = "~",
    show_hidden: bool = False,
    sort_by: str = "type",
    sort_desc: bool = False,
):
    """Browse a directory — returns full entry list with metadata."""
    tool = registry.get("browse_directory")
    if not tool:
        raise HTTPException(status_code=503, detail="browse_directory tool not available")
    result = await tool.execute({
        "path": path,
        "show_hidden": show_hidden,
        "sort_by": sort_by,
        "sort_desc": sort_desc,
    })
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


@router.get("/api/browse/info")
async def directory_info(path: str, max_depth: int = 3):
    """Get summary info for a directory."""
    tool = registry.get("get_directory_info")
    if not tool:
        raise HTTPException(status_code=503, detail="get_directory_info tool not available")
    result = await tool.execute({"path": path, "max_depth": max_depth})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


@router.get("/api/browse/common-folders")
async def common_folders():
    """Get paths to common user directories."""
    tool = registry.get("get_common_folders")
    if not tool:
        raise HTTPException(status_code=503, detail="get_common_folders tool not available")
    result = await tool.execute({})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


@router.post("/api/search")
async def search_files(request: SearchRequest):
    """Advanced file search with filters."""
    tool = registry.get("advanced_search")
    if not tool:
        raise HTTPException(status_code=503, detail="advanced_search tool not available")
    result = await tool.execute(request.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


@router.post("/api/search/content")
async def search_content(request: ContentSearchRequest):
    """Search for text content inside files."""
    tool = registry.get("search_by_content")
    if not tool:
        raise HTTPException(status_code=503, detail="search_by_content tool not available")
    result = await tool.execute(request.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


# ─── Document Search ──────────────────────────────────────
class DocumentSearchRequest(BaseModel):
    path: str
    query: str
    extensions: Optional[str] = ""
    case_sensitive: Optional[bool] = False
    max_files: Optional[int] = 50
    max_results: Optional[int] = 30
    recursive: Optional[bool] = True
    context_chars: Optional[int] = 100
    max_pages: Optional[int] = 20
    ocr_language: Optional[str] = "eng"


@router.post("/api/search/documents")
async def search_documents(request: DocumentSearchRequest):
    """Search for text content inside documents (PDF, Office, images via OCR, code/text files)."""
    tool = registry.get("search_documents")
    if not tool:
        raise HTTPException(status_code=503, detail="search_documents tool not available")
    result = await tool.execute(request.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


# ─── Semantic Search ──────────────────────────────────────
class SemanticSearchRequest(BaseModel):
    path: str
    query: str
    extensions: Optional[str] = ""
    max_files: Optional[int] = 50
    max_results: Optional[int] = 30
    recursive: Optional[bool] = True


@router.post("/api/search/semantic")
async def search_semantic(request: SemanticSearchRequest):
    """Natural language semantic search across files and document content."""
    tool = registry.get("semantic_search")
    if not tool:
        raise HTTPException(status_code=503, detail="semantic_search tool not available")
    result = await tool.execute(request.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


# ─── Code Search ──────────────────────────────────────────
class CodeSearchRequest(BaseModel):
    path: str
    query: str
    language: Optional[str] = ""
    search_in: Optional[str] = "all"
    max_results: Optional[int] = 30
    recursive: Optional[bool] = True
    include_tests: Optional[bool] = True


@router.post("/api/search/code")
async def search_code(request: CodeSearchRequest):
    """Search inside code repositories by function/class names and patterns."""
    tool = registry.get("search_code")
    if not tool:
        raise HTTPException(status_code=503, detail="search_code tool not available")
    result = await tool.execute(request.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


# ─── Document Text Extraction ─────────────────────────────
class ExtractTextRequest(BaseModel):
    path: str
    max_pages: Optional[int] = 20
    ocr_language: Optional[str] = "eng"


@router.post("/api/extract/text")
async def extract_text(request: ExtractTextRequest):
    """Extract text from a single document (PDF, Office, image via OCR, code/text)."""
    tool = registry.get("extract_document_text")
    if not tool:
        raise HTTPException(status_code=503, detail="extract_document_text tool not available")
    result = await tool.execute(request.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


class BatchExtractRequest(BaseModel):
    path: str
    recursive: Optional[bool] = True
    extensions: Optional[str] = ""
    max_files: Optional[int] = 50
    max_pages: Optional[int] = 20
    ocr_language: Optional[str] = "eng"


@router.post("/api/extract/batch")
async def extract_batch(request: BatchExtractRequest):
    """Extract text from all supported documents in a directory."""
    tool = registry.get("batch_extract_text")
    if not tool:
        raise HTTPException(status_code=503, detail="batch_extract_text tool not available")
    result = await tool.execute(request.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


@router.get("/api/bookmarks")
async def get_bookmarks():
    """Get bookmarked folders."""
    data = await memory_store.get_all()
    return data.get("bookmarks", [])


@router.post("/api/bookmarks")
async def add_bookmark(path: str):
    """Bookmark a folder."""
    data = await memory_store.get_all()
    bookmarks = data.get("bookmarks", [])
    import os as _os
    expanded = _os.path.expanduser(path)
    if expanded not in bookmarks:
        bookmarks.append(expanded)
        await memory_store.set("bookmarks", bookmarks)
    return bookmarks


@router.delete("/api/bookmarks")
async def remove_bookmark(path: str):
    """Remove a bookmarked folder."""
    data = await memory_store.get_all()
    bookmarks = data.get("bookmarks", [])
    import os as _os
    expanded = _os.path.expanduser(path)
    bookmarks = [b for b in bookmarks if b != expanded]
    await memory_store.set("bookmarks", bookmarks)
    return bookmarks


@router.get("/api/recent-folders")
async def get_recent_folders():
    """Get recently visited folders."""
    data = await memory_store.get_all()
    return data.get("recent_folders", [])


@router.post("/api/recent-folders")
async def add_recent_folder(path: str):
    """Record a recently visited folder."""
    data = await memory_store.get_all()
    recent = data.get("recent_folders", [])
    import os as _os
    expanded = _os.path.expanduser(path)
    recent = [r for r in recent if r != expanded]
    recent.insert(0, expanded)
    recent = recent[:20]
    await memory_store.set("recent_folders", recent)
    return recent


# ─── File Open & Preview ───────────────────────────────
@router.post("/api/open")
async def open_file(path: str):
    """Open a file with the system's default application."""
    tool = registry.get("open_file")
    if not tool:
        raise HTTPException(status_code=503, detail="open_file tool not available")
    result = await tool.execute({"path": path})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "opened", "path": path, "message": result.message}


@router.get("/api/preview")
async def preview_file(path: str, max_lines: int = 200):
    """Read text file content for in-browser preview."""
    tool = registry.get("read_file_content")
    if not tool:
        raise HTTPException(status_code=503, detail="read_file_content tool not available")
    result = await tool.execute({"path": path, "max_lines": max_lines})
    if not result.success:
        return {"success": False, "message": result.message, "data": result.data}
    return {"success": True, "data": result.data}


# ─── File Operations (Direct API) ──────────────────────
class FileOpRequest(BaseModel):
    path: str
    new_name: Optional[str] = None
    target: Optional[str] = None
    content: Optional[str] = ""
    sources: Optional[list] = None
    output: Optional[str] = None
    format: Optional[str] = ""
    action: Optional[str] = ""
    original_path: Optional[str] = ""
    dry_run: Optional[bool] = False


@router.post("/api/fileop/create-file")
async def fileop_create_file(req: FileOpRequest):
    """Create a new file."""
    tool = registry.get("create_file")
    result = await tool.execute({"path": req.path, "content": req.content or ""})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message}


@router.post("/api/fileop/create-folder")
async def fileop_create_folder(req: FileOpRequest):
    """Create a new directory."""
    tool = registry.get("create_directory")
    result = await tool.execute({"path": req.path})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message}


@router.post("/api/fileop/rename")
async def fileop_rename(req: FileOpRequest):
    """Rename a file or directory."""
    tool = registry.get("rename_file")
    result = await tool.execute({"path": req.path, "new_name": req.new_name})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message}


@router.post("/api/fileop/copy")
async def fileop_copy(req: FileOpRequest):
    """Copy a file or directory."""
    tool = registry.get("copy_file")
    result = await tool.execute({"source": req.path, "target": req.target})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message}


@router.post("/api/fileop/move")
async def fileop_move(req: FileOpRequest):
    """Move a file or directory."""
    tool = registry.get("move_file")
    result = await tool.execute({"source": req.path, "target": req.target})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message}


@router.post("/api/fileop/trash")
async def fileop_trash(req: FileOpRequest):
    """Move to Trash (recoverable)."""
    tool = registry.get("trash_file")
    result = await tool.execute({"path": req.path})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message}


@router.post("/api/fileop/delete")
async def fileop_delete(req: FileOpRequest):
    """Permanently delete a file or directory."""
    tool = registry.get("delete_file")
    result = await tool.execute({"path": req.path})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message}


@router.post("/api/fileop/compress")
async def fileop_compress(req: FileOpRequest):
    """Compress files into an archive."""
    tool = registry.get("compress_files")
    result = await tool.execute({
        "sources": req.sources or [req.path],
        "output": req.output or (req.path + ".zip"),
        "format": req.format,
    })
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message, "data": result.data}


@router.post("/api/fileop/extract")
async def fileop_extract(req: FileOpRequest):
    """Extract an archive."""
    tool = registry.get("extract_archive")
    result = await tool.execute({
        "path": req.path,
        "output_dir": req.target or "",
    })
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message, "data": result.data}


@router.get("/api/fileop/trash-list")
async def fileop_trash_list():
    """List items in Trash."""
    tool = registry.get("restore_from_trash")
    result = await tool.execute({"action": "list"})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"items": result.data, "message": result.message}


@router.post("/api/fileop/restore")
async def fileop_restore(req: FileOpRequest):
    """Restore a file from Trash."""
    tool = registry.get("restore_from_trash")
    result = await tool.execute({"action": "restore", "original_path": req.original_path or req.path})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message}


@router.post("/api/fileop/organize-by-extension")
async def fileop_organize_ext(req: FileOpRequest):
    """Organize files by extension into category folders."""
    tool = registry.get("organize_by_extension")
    result = await tool.execute({"path": req.path, "dry_run": req.dry_run})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message, "data": result.data}


@router.post("/api/fileop/organize-by-date")
async def fileop_organize_date(req: FileOpRequest):
    """Organize files by modification date into date folders."""
    tool = registry.get("organize_by_date")
    result = await tool.execute({"path": req.path, "format": req.format or "month", "dry_run": req.dry_run})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message, "data": result.data}


@router.post("/api/fileop/batch-move")
async def fileop_batch_move(req: FileOpRequest):
    """Move multiple files matching a pattern to a target directory."""
    tool = registry.get("batch_move")
    result = await tool.execute({
        "source_dir": req.path,
        "target_dir": req.target or "",
        "pattern": req.action or "",
        "extensions": req.format or "",
        "recursive": False,
        "dry_run": req.dry_run,
    })
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message, "data": result.data}


class DeleteDupRequest(BaseModel):
    path: str
    extension: Optional[str] = None
    dry_run: Optional[bool] = True
    keep_newest: Optional[bool] = False


@router.post("/api/fileop/delete-duplicates")
async def fileop_delete_duplicates(req: DeleteDupRequest):
    """Find and delete duplicate files, keeping one copy."""
    tool = registry.get("delete_duplicates")
    result = await tool.execute(req.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message, "data": result.data}


class OrganizeAIRequest(BaseModel):
    path: str
    categories: Optional[str] = ""
    dry_run: Optional[bool] = False
    prompt: Optional[str] = ""


@router.post("/api/fileop/organize-by-ai")
async def fileop_organize_ai(req: OrganizeAIRequest):
    """Organize files using LLM-powered AI categorization."""
    tool = registry.get("organize_by_ai")
    result = await tool.execute(req.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "ok", "message": result.message, "data": result.data}


# ─── WebSocket for real-time updates ───────────────────
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time task execution updates."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "chat":
                # Create plan
                context = {}
                try:
                    memories = await memory_store.get_all()
                    if memories:
                        context["user_preferences"] = memories
                except Exception:
                    pass

                plan_result = await planner.create_plan(msg["message"], context=context or None)
                
                if plan_result["success"]:
                    task_id = str(uuid.uuid4())
                    plan = plan_result["plan"]

                    db = await get_db()
                    try:
                        await db.execute(
                            """INSERT INTO tasks (id, user_input, goal, status, plan_json, created_at, updated_at)
                               VALUES (?, ?, ?, 'awaiting_approval', ?, ?, ?)""",
                            (task_id, msg["message"], plan.get("goal", ""),
                             json.dumps(plan), datetime.now().isoformat(), datetime.now().isoformat()),
                        )
                        await db.commit()
                    finally:
                        await db.close()

                    await websocket.send_json({
                        "type": "plan",
                        "task_id": task_id,
                        "plan": plan,
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": plan_result.get("error", "Planning failed"),
                    })

            elif msg.get("type") == "approve":
                task_id = msg["task_id"]
                db = await get_db()
                try:
                    cursor = await db.execute("SELECT plan_json FROM tasks WHERE id = ?", (task_id,))
                    row = await cursor.fetchone()
                    if row:
                        plan = json.loads(row[0])
                        await db.execute(
                            "UPDATE tasks SET status='executing', updated_at=? WHERE id=?",
                            (datetime.now().isoformat(), task_id),
                        )
                        await db.commit()
                    else:
                        await websocket.send_json({"type": "error", "message": "Task not found"})
                        continue
                finally:
                    await db.close()

                async def on_step(index, result):
                    await websocket.send_json({
                        "type": "step_complete",
                        "task_id": task_id,
                        "step_index": index,
                        "result": result,
                    })

                report = await executor.execute_plan(task_id, plan, on_step_complete=on_step)
                await websocket.send_json({
                    "type": "execution_complete",
                    "task_id": task_id,
                    "report": report,
                })

            elif msg.get("type") == "reject":
                task_id = msg["task_id"]
                db = await get_db()
                try:
                    await db.execute(
                        "UPDATE tasks SET status='rejected', updated_at=? WHERE id=?",
                        (datetime.now().isoformat(), task_id),
                    )
                    await db.commit()
                finally:
                    await db.close()
                await websocket.send_json({"type": "rejected", "task_id": task_id})

    except WebSocketDisconnect:
        pass


# ─── Interactive Terminal (PTY) ───────────────────────
@router.websocket("/ws/terminal")
async def terminal_websocket(websocket: WebSocket):
    """Real interactive shell over WebSocket, backed by a pseudo-terminal (PTY).

    Protocol (JSON frames both ways):
      client -> server: {"type": "input", "data": "<keystrokes>"}
                         {"type": "resize", "rows": 24, "cols": 80}
      server -> client: {"type": "output", "data": "<raw terminal bytes as text>"}
                         {"type": "exit"}
                         {"type": "error", "message": "..."}
    """
    await websocket.accept()

    try:
        from terminal.pty_session import PtySession
    except ImportError:
        await websocket.send_json(
            {"type": "error", "message": "Interactive terminal is not supported on this platform"}
        )
        await websocket.close()
        return

    session = PtySession(cwd=os.path.expanduser("~"))
    try:
        session.spawn()
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Failed to start shell: {e}"})
        await websocket.close()
        return

    loop = asyncio.get_event_loop()
    output_queue: asyncio.Queue = asyncio.Queue()

    def on_readable():
        try:
            data = os.read(session.fd, 65536)
        except OSError:
            data = b""
        if data:
            output_queue.put_nowait(data)
        else:
            try:
                loop.remove_reader(session.fd)
            except Exception:
                pass
            output_queue.put_nowait(None)

    loop.add_reader(session.fd, on_readable)

    async def sender_loop():
        while True:
            data = await output_queue.get()
            if data is None:
                await websocket.send_json({"type": "exit"})
                break
            await websocket.send_json({"type": "output", "data": data.decode(errors="replace")})

    sender_task = asyncio.create_task(sender_loop())

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            mtype = payload.get("type")
            if mtype == "input":
                session.write(payload.get("data", "").encode())
            elif mtype == "resize":
                session.resize(int(payload.get("rows", 24)), int(payload.get("cols", 80)))
    except WebSocketDisconnect:
        pass
    finally:
        try:
            loop.remove_reader(session.fd)
        except Exception:
            pass
        sender_task.cancel()
        session.close()


# ══════════════════════════════════════════════════════
# PHASE 2 ROUTES
# ══════════════════════════════════════════════════════

# ─── Desktop: Clipboard ─────────────────────────────────────────────────────

@router.get("/api/desktop/clipboard")
async def desktop_clipboard_read():
    """Read the current system clipboard content."""
    tool = registry.get("clipboard_read")
    if not tool:
        raise HTTPException(status_code=503, detail="clipboard_read not available")
    result = await tool.execute({})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


class ClipboardWriteRequest(BaseModel):
    text: str


@router.post("/api/desktop/clipboard")
async def desktop_clipboard_write(req: ClipboardWriteRequest):
    """Write text to the system clipboard."""
    tool = registry.get("clipboard_write")
    if not tool:
        raise HTTPException(status_code=503, detail="clipboard_write not available")
    result = await tool.execute({"text": req.text})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


@router.get("/api/desktop/clipboard/history")
async def desktop_clipboard_history(limit: int = 20):
    """Get clipboard history (in-session)."""
    tool = registry.get("clipboard_history")
    if not tool:
        raise HTTPException(status_code=503, detail="clipboard_history not available")
    result = await tool.execute({"limit": limit})
    return result.data


# ─── Desktop: Screenshot ────────────────────────────────────────────────────

class ScreenshotRequest(BaseModel):
    mode: Optional[str] = "full"
    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    output: Optional[str] = None
    delay: Optional[int] = 0


@router.post("/api/desktop/screenshot")
async def desktop_screenshot(req: ScreenshotRequest):
    """Take a screenshot (full/window/region)."""
    tool = registry.get("take_screenshot")
    if not tool:
        raise HTTPException(status_code=503, detail="take_screenshot not available")
    args = {k: v for k, v in req.model_dump().items() if v is not None}
    result = await tool.execute(args)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    data = dict(result.data)
    data.pop("image_base64", None)
    return {"message": result.message, **data}


# ─── Desktop: Notifications ─────────────────────────────────────────────────

class NotifyRequest(BaseModel):
    title: str
    body: Optional[str] = ""
    urgency: Optional[str] = "normal"
    icon: Optional[str] = "dialog-information"
    timeout: Optional[int] = 5000


@router.post("/api/desktop/notify")
async def desktop_notify(req: NotifyRequest):
    """Send a native desktop notification."""
    tool = registry.get("desktop_notify")
    if not tool:
        raise HTTPException(status_code=503, detail="desktop_notify not available")
    result = await tool.execute(req.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"message": result.message}


# ─── Desktop: Window Management ─────────────────────────────────────────────

@router.get("/api/desktop/windows")
async def desktop_list_windows():
    """List all open windows."""
    tool = registry.get("list_windows")
    if not tool:
        raise HTTPException(status_code=503, detail="list_windows not available")
    result = await tool.execute({})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


@router.get("/api/desktop/windows/active")
async def desktop_active_window():
    """Get the currently active/focused window."""
    tool = registry.get("get_active_window")
    if not tool:
        raise HTTPException(status_code=503, detail="get_active_window not available")
    result = await tool.execute({})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


class WindowActionRequest(BaseModel):
    action: str
    title: Optional[str] = ""
    window_id: Optional[str] = ""


@router.post("/api/desktop/windows/action")
async def desktop_window_action(req: WindowActionRequest):
    """Minimize, maximize, restore, close, or focus a window."""
    if req.action == "focus":
        tool = registry.get("focus_window")
    else:
        tool = registry.get("window_action")
    if not tool:
        raise HTTPException(status_code=503, detail="Window tool not available")
    result = await tool.execute(req.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"message": result.message}


# ─── Desktop: Display Info ──────────────────────────────────────────────────

@router.get("/api/desktop/displays")
async def desktop_display_info():
    """Get connected monitor/display information."""
    tool = registry.get("display_info")
    if not tool:
        raise HTTPException(status_code=503, detail="display_info not available")
    result = await tool.execute({})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


# ─── Plugin: VS Code ────────────────────────────────────────────────────────

class VSCodeOpenRequest(BaseModel):
    path: str
    line: Optional[int] = None
    new_window: Optional[bool] = False


@router.post("/api/plugin/vscode/open")
async def plugin_vscode_open(req: VSCodeOpenRequest):
    """Open a file or directory in VS Code."""
    tool = registry.get("vscode_open")
    if not tool:
        raise HTTPException(status_code=503, detail="vscode_open not available")
    result = await tool.execute(req.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"message": result.message}


# ─── Plugin: Docker ─────────────────────────────────────────────────────────

@router.get("/api/plugin/docker/list")
async def plugin_docker_list(list_type: str = "containers", all: bool = False):
    """List Docker containers or images."""
    tool = registry.get("docker_list")
    if not tool:
        raise HTTPException(status_code=503, detail="docker_list not available")
    result = await tool.execute({"type": list_type, "all": all})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


class DockerActionRequest(BaseModel):
    action: str
    container: Optional[str] = ""
    image: Optional[str] = ""
    force: Optional[bool] = False


@router.post("/api/plugin/docker/action")
async def plugin_docker_action(req: DockerActionRequest):
    """Start, stop, restart, remove a Docker container."""
    tool = registry.get("docker_action")
    if not tool:
        raise HTTPException(status_code=503, detail="docker_action not available")
    result = await tool.execute(req.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"message": result.message, "data": result.data}


@router.get("/api/plugin/docker/logs")
async def plugin_docker_logs(container: str, tail: int = 50, since: str = ""):
    """Get logs from a Docker container."""
    tool = registry.get("docker_logs")
    if not tool:
        raise HTTPException(status_code=503, detail="docker_logs not available")
    result = await tool.execute({"container": container, "tail": tail, "since": since})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


class DockerExecRequest(BaseModel):
    container: str
    command: str


@router.post("/api/plugin/docker/exec")
async def plugin_docker_exec(req: DockerExecRequest):
    """Execute a command inside a Docker container."""
    tool = registry.get("docker_exec")
    if not tool:
        raise HTTPException(status_code=503, detail="docker_exec not available")
    result = await tool.execute(req.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


# ─── Plugin: Package Manager ────────────────────────────────────────────────

class PackageRequest(BaseModel):
    manager: str
    action: str
    package: Optional[str] = ""
    global_flag: Optional[bool] = False
    dry_run: Optional[bool] = False


@router.post("/api/plugin/packages")
async def plugin_packages(req: PackageRequest):
    """Interact with apt, pip, npm, snap, or flatpak."""
    tool = registry.get("package_manager")
    if not tool:
        raise HTTPException(status_code=503, detail="package_manager not available")
    data = req.model_dump()
    data["global"] = data.pop("global_flag", False)
    result = await tool.execute(data)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


# ─── Plugin: HTTP / API Testing ─────────────────────────────────────────────

class HTTPReqModel(BaseModel):
    url: str
    method: Optional[str] = "GET"
    headers: Optional[dict] = None
    params: Optional[dict] = None
    json_body: Optional[dict] = None
    form_data: Optional[dict] = None
    text_body: Optional[str] = None
    timeout: Optional[float] = 30
    follow_redirects: Optional[bool] = True


@router.post("/api/plugin/http")
async def plugin_http_request(req: HTTPReqModel):
    """Make an HTTP request and return the response."""
    tool = registry.get("http_request")
    if not tool:
        raise HTTPException(status_code=503, detail="http_request not available")
    result = await tool.execute(req.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


# ─── Plugin: SQLite ─────────────────────────────────────────────────────────

class SQLiteQueryModel(BaseModel):
    database: str
    sql: str
    params: Optional[list] = None


@router.post("/api/plugin/sqlite/query")
async def plugin_sqlite_query(req: SQLiteQueryModel):
    """Execute a SQL query against a local SQLite database."""
    tool = registry.get("sqlite_query")
    if not tool:
        raise HTTPException(status_code=503, detail="sqlite_query not available")
    result = await tool.execute(req.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


@router.get("/api/plugin/sqlite/tables")
async def plugin_sqlite_tables(database: str):
    """List tables in a SQLite database."""
    tool = registry.get("sqlite_list_tables")
    if not tool:
        raise HTTPException(status_code=503, detail="sqlite_list_tables not available")
    result = await tool.execute({"database": database})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


# ─── Scheduler ──────────────────────────────────────────────────────────────

class JobCreateRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    trigger_type: str
    trigger_data: dict
    action_type: str
    action_data: dict


class JobUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    trigger_data: Optional[dict] = None
    action_data: Optional[dict] = None


@router.get("/api/scheduler/jobs")
async def scheduler_list_jobs():
    """List all scheduled jobs."""
    jobs = await scheduler_service.list_jobs()
    return {"jobs": jobs, "count": len(jobs)}


@router.post("/api/scheduler/jobs")
async def scheduler_create_job(req: JobCreateRequest):
    """Create a new scheduled job."""
    job = await scheduler_service.create_job(req.model_dump())
    return job


@router.get("/api/scheduler/jobs/{job_id}")
async def scheduler_get_job(job_id: str):
    """Get a specific scheduled job."""
    job = await scheduler_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.put("/api/scheduler/jobs/{job_id}")
async def scheduler_update_job(job_id: str, req: JobUpdateRequest):
    """Update a scheduled job."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    job = await scheduler_service.update_job(job_id, updates)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/api/scheduler/jobs/{job_id}")
async def scheduler_delete_job(job_id: str):
    """Delete a scheduled job."""
    await scheduler_service.delete_job(job_id)
    return {"status": "deleted", "id": job_id}


@router.post("/api/scheduler/jobs/{job_id}/run")
async def scheduler_run_now(job_id: str):
    """Trigger a scheduled job immediately."""
    job = await scheduler_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await scheduler_service.run_now(job_id)
    return {"status": "triggered", "id": job_id}


@router.get("/api/scheduler/jobs/{job_id}/runs")
async def scheduler_job_runs(job_id: str, limit: int = 20):
    """Get execution history for a job."""
    runs = await scheduler_service.get_job_runs(job_id, limit)
    return {"runs": runs, "count": len(runs)}


# ─── Knowledge Base ─────────────────────────────────────────────────────────

class NoteCreateRequest(BaseModel):
    title: str
    content: str
    tags: Optional[List[str]] = None
    project: Optional[str] = ""


class NoteUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    project: Optional[str] = None


@router.get("/api/kb/notes")
async def kb_list_notes(project: str = "", tag: str = "", limit: int = 100):
    """List all notes."""
    notes = await kb.list_notes(project=project, tag=tag, limit=limit)
    return {"notes": notes, "count": len(notes)}


@router.post("/api/kb/notes")
async def kb_create_note(req: NoteCreateRequest):
    """Create a new markdown note."""
    note = await kb.create_note(
        title=req.title,
        content=req.content,
        tags=req.tags,
        project=req.project,
    )
    return note


@router.get("/api/kb/search")
async def kb_search(q: str, limit: int = 20):
    """Full-text search across all notes."""
    results = await kb.search_notes(q, limit=limit)
    return {"results": results, "count": len(results)}


@router.get("/api/kb/projects")
async def kb_projects():
    """List all projects with note counts."""
    projects = await kb.list_projects()
    return {"projects": projects}


@router.get("/api/kb/notes/{note_id}")
async def kb_get_note(note_id: str):
    """Get a note by ID."""
    note = await kb.get_note(note_id=note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.put("/api/kb/notes/{note_id}")
async def kb_update_note(note_id: str, req: NoteUpdateRequest):
    """Update an existing note."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    note = await kb.update_note(note_id, **updates)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.delete("/api/kb/notes/{note_id}")
async def kb_delete_note(note_id: str):
    """Delete a note."""
    ok = await kb.delete_note(note_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"status": "deleted", "id": note_id}


@router.get("/api/kb/notes/{note_id}/backlinks")
async def kb_backlinks(note_id: str):
    """Get all notes linking back to this note."""
    note = await kb.get_note(note_id=note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    links = await kb.get_backlinks(note["slug"])
    return {"backlinks": links, "count": len(links)}


class ImportTextRequest(BaseModel):
    title: str
    text: str
    tags: Optional[List[str]] = None
    project: Optional[str] = ""


@router.post("/api/kb/import")
async def kb_import(req: ImportTextRequest):
    """Import arbitrary text as a knowledge base note."""
    note = await kb.import_text(req.title, req.text, req.tags, req.project)
    return note


# ─── Cache / Performance ─────────────────────────────────────────────────────

@router.get("/api/cache/stats")
async def cache_stats():
    """Get cache statistics."""
    return {
        "metadata_cache": await metadata_cache.stats(),
        "search_cache":   await search_cache.stats(),
    }


@router.delete("/api/cache/clear")
async def cache_clear():
    """Clear all caches."""
    await metadata_cache.clear()
    await search_cache.clear()
    return {"status": "cleared"}


# ─── Config / Settings Management ────────────────────────────────────────────

@router.get("/api/config/dotfiles")
async def config_list_dotfiles():
    """List important dotfiles and config directories."""
    home = os.path.expanduser("~")
    common = [
        ".bashrc", ".zshrc", ".profile", ".bash_profile", ".bash_aliases",
        ".vimrc", ".gitconfig", ".gitignore_global",
        ".tmux.conf", ".ssh/config", ".npmrc",
        ".config/git/config",
    ]
    result = []
    for f in common:
        full = os.path.join(home, f)
        if os.path.exists(full):
            stat = os.stat(full)
            result.append({
                "path": full,
                "name": f,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    config_dir = os.path.join(home, ".config")
    if os.path.isdir(config_dir):
        for item in sorted(os.listdir(config_dir))[:30]:
            full = os.path.join(config_dir, item)
            if os.path.isdir(full):
                result.append({"path": full, "name": f".config/{item}", "is_dir": True})
    return {"dotfiles": result, "count": len(result)}


@router.get("/api/config/installed-packages")
async def config_installed_packages(manager: str = "pip"):
    """Export installed packages list."""
    tool = registry.get("package_manager")
    if not tool:
        raise HTTPException(status_code=503, detail="package_manager not available")
    result = await tool.execute({"manager": manager, "action": "list"})
    return {"manager": manager, "packages": result.data.get("stdout", "") if result.success else result.message}


@router.get("/api/config/env")
async def config_env_vars():
    """Get safe environment variables (no secrets)."""
    safe_prefixes = ("PATH", "HOME", "USER", "SHELL", "LANG", "TERM",
                     "XDG", "DISPLAY", "WAYLAND", "GTK", "QT", "DBUS",
                     "PYTHON", "NODE", "NPM", "JAVA")
    env = {k: v for k, v in os.environ.items()
           if any(k.startswith(p) for p in safe_prefixes)}
    return {"env": env, "count": len(env)}


# ─── Voice & Audio Intelligence (Phase 3) ───────────────────────────────────

@router.get("/api/voice/status")
async def voice_status():
    """Check availability of STT (Whisper) and TTS engines."""
    import shutil as _shutil

    # STT check
    stt = {"available": False, "faster_whisper": False, "openai_whisper": False}
    try:
        import faster_whisper  # noqa: F401
        stt["available"] = True
        stt["faster_whisper"] = True
    except ImportError:
        pass
    if not stt["available"]:
        try:
            import whisper  # noqa: F401
            stt["available"] = True
            stt["openai_whisper"] = True
        except ImportError:
            pass

    # TTS check
    tts = {
        "available": False,
        "pyttsx3": False,
        "espeak": bool(_shutil.which("espeak") or _shutil.which("espeak-ng")),
        "festival": bool(_shutil.which("festival")),
    }
    try:
        import pyttsx3  # noqa: F401
        tts["pyttsx3"] = True
    except ImportError:
        pass
    tts["available"] = tts["pyttsx3"] or tts["espeak"] or tts["festival"]

    return {"stt": stt, "tts": tts}


class VoiceTranscribeRequest(BaseModel):
    path: str
    model: Optional[str] = "base"
    language: Optional[str] = None
    save_to: Optional[str] = None


@router.post("/api/voice/transcribe")
async def voice_transcribe(request: VoiceTranscribeRequest):
    """Transcribe a local audio/video file using Whisper."""
    tool = registry.get("transcribe_audio")
    if not tool:
        raise HTTPException(status_code=503, detail="transcribe_audio tool not available")
    result = await tool.execute({
        "path": request.path,
        "model": request.model or "base",
        "language": request.language,
        "save_to": request.save_to,
    })
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


@router.post("/api/voice/transcribe-upload")
async def voice_transcribe_upload(
    file: UploadFile = File(...),
    model: str = "base",
    language: Optional[str] = None,
):
    """Upload an audio/video file and transcribe it via Whisper."""
    import tempfile as _tempfile

    tool = registry.get("transcribe_audio")
    if not tool:
        raise HTTPException(status_code=503, detail="transcribe_audio tool not available")

    # Save upload to a temp file
    suffix = os.path.splitext(file.filename or "audio")[1] or ".tmp"
    with _tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = await tool.execute({
            "path": tmp_path,
            "model": model,
            "language": language or None,
        })
        if not result.success:
            raise HTTPException(status_code=400, detail=result.message)
        return result.data
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


class VoiceBatchRequest(BaseModel):
    path: str
    model: Optional[str] = "base"
    language: Optional[str] = None
    recursive: Optional[bool] = False
    output_dir: Optional[str] = None


@router.post("/api/voice/batch-transcribe")
async def voice_batch_transcribe(request: VoiceBatchRequest):
    """Batch-transcribe all audio/video files in a directory."""
    tool = registry.get("batch_transcribe")
    if not tool:
        raise HTTPException(status_code=503, detail="batch_transcribe tool not available")
    result = await tool.execute({
        "path": request.path,
        "model": request.model or "base",
        "language": request.language,
        "recursive": request.recursive,
        "output_dir": request.output_dir,
    })
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


class TTSSpeakRequest(BaseModel):
    text: str
    rate: Optional[int] = 175
    volume: Optional[float] = 1.0
    voice: Optional[str] = ""


@router.post("/api/voice/speak")
async def voice_speak(request: TTSSpeakRequest):
    """Speak text aloud via local TTS engine."""
    tool = registry.get("text_to_speech")
    if not tool:
        raise HTTPException(status_code=503, detail="text_to_speech tool not available")
    result = await tool.execute({
        "text": request.text,
        "rate": request.rate or 175,
        "volume": request.volume if request.volume is not None else 1.0,
        "voice": request.voice or "",
    })
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


class TTSSaveRequest(BaseModel):
    text: str
    output: Optional[str] = None
    rate: Optional[int] = 175
    voice: Optional[str] = ""


@router.post("/api/voice/save-speech")
async def voice_save_speech(request: TTSSaveRequest):
    """Render TTS to a .wav file without playing it."""
    tool = registry.get("save_speech_to_file")
    if not tool:
        raise HTTPException(status_code=503, detail="save_speech_to_file tool not available")
    result = await tool.execute({
        "text": request.text,
        "output": request.output or "",
        "rate": request.rate or 175,
        "voice": request.voice or "",
    })
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


class AudioLibRequest(BaseModel):
    path: str
    recursive: Optional[bool] = False
    include_video: Optional[bool] = True
    include_audio: Optional[bool] = True
    max_results: Optional[int] = 200


@router.post("/api/voice/list-audio")
async def voice_list_audio(request: AudioLibRequest):
    """List audio/video files in a directory."""
    tool = registry.get("list_audio_files")
    if not tool:
        raise HTTPException(status_code=503, detail="list_audio_files tool not available")
    result = await tool.execute({
        "path": request.path,
        "recursive": request.recursive,
        "include_video": request.include_video,
        "include_audio": request.include_audio,
        "max_results": request.max_results,
    })
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data


class AudioInfoRequest(BaseModel):
    path: str


@router.post("/api/voice/audio-info")
async def voice_audio_info(request: AudioInfoRequest):
    """Get technical metadata for an audio/video file."""
    tool = registry.get("audio_info")
    if not tool:
        raise HTTPException(status_code=503, detail="audio_info tool not available")
    result = await tool.execute({"path": request.path})
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.data

