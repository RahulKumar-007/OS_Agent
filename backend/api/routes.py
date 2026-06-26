"""
API routes for the Local Filesystem Agent.
"""
import json
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from agent.planner import Planner
from agent.executor import Executor
from agent.synthesizer import Synthesizer
from tools.base import registry
from permissions.policy import PolicyEngine
from llm.client import LLMClient
from memory.memory_store import MemoryStore
from database.models import get_db


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
