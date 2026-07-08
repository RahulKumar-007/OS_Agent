"""
Task Scheduler — SQLite-backed cron-like automation engine.

Features:
  - Schedule tasks at intervals, cron expressions, or specific datetime
  - File-change triggers (via polling or watchdog)
  - Folder watchers
  - Persistent storage of all scheduled jobs
  - Background worker loop
"""

import asyncio
import fnmatch
import json
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import aiosqlite

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "scheduler.db")


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_scheduler_db():
    """Create scheduler tables if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                description TEXT,
                trigger_type TEXT NOT NULL,
                trigger_data TEXT NOT NULL,
                action_type  TEXT NOT NULL,
                action_data  TEXT NOT NULL,
                enabled      INTEGER DEFAULT 1,
                last_run     TEXT,
                next_run     TEXT,
                run_count    INTEGER DEFAULT 0,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_runs (
                id          TEXT PRIMARY KEY,
                job_id      TEXT NOT NULL,
                started_at  TEXT NOT NULL,
                finished_at TEXT,
                status      TEXT,
                output      TEXT,
                error       TEXT,
                FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id)
            );
        """)
        await db.commit()


# ── Cron-like next-run calculation ────────────────────────────────────────────

def _next_run_from_interval(interval_seconds: float, last_run: Optional[str]) -> datetime:
    if last_run:
        lr = datetime.fromisoformat(last_run)
        nxt = lr + timedelta(seconds=interval_seconds)
        if nxt < datetime.now():
            nxt = datetime.now() + timedelta(seconds=interval_seconds)
        return nxt
    return datetime.now() + timedelta(seconds=interval_seconds)


def _parse_interval(spec: str) -> float:
    """Parse human-readable intervals like '5m', '2h', '1d', '30s'."""
    spec = spec.strip().lower()
    if spec.endswith("s"):
        return float(spec[:-1])
    if spec.endswith("m"):
        return float(spec[:-1]) * 60
    if spec.endswith("h"):
        return float(spec[:-1]) * 3600
    if spec.endswith("d"):
        return float(spec[:-1]) * 86400
    try:
        return float(spec)
    except ValueError:
        return 3600.0


# ── Scheduler Service ─────────────────────────────────────────────────────────

class SchedulerService:
    """Background task scheduler."""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._on_execute: Optional[Callable] = None  # callback(job, run_result)

    def set_executor(self, callback: Callable):
        self._on_execute = callback

    async def start(self):
        await init_scheduler_db()
        self._running = True
        self._task = asyncio.create_task(self._loop())

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        """Main scheduler loop — runs every 10 seconds."""
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                print(f"⚠️  Scheduler error: {e}")
            await asyncio.sleep(10)

    async def _tick(self):
        """Check and execute due jobs."""
        now = datetime.now()
        db = await _get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM scheduled_jobs WHERE enabled=1 AND (next_run IS NULL OR next_run <= ?)",
                (now.isoformat(),),
            )
            jobs = [dict(r) for r in await cursor.fetchall()]
        finally:
            await db.close()

        for job in jobs:
            asyncio.create_task(self._run_job(job))

    async def _run_job(self, job: dict):
        run_id = _uuid()
        started = datetime.now().isoformat()
        action_data = json.loads(job["action_data"])
        trigger_data = json.loads(job["trigger_data"])

        output, error, status = "", "", "success"
        try:
            result = await self._execute_action(job["action_type"], action_data)
            output = str(result)
        except Exception as e:
            error = str(e)
            status = "error"

        finished = datetime.now().isoformat()

        # Calculate next run
        next_run = None
        if job["trigger_type"] == "interval":
            interval = _parse_interval(trigger_data.get("interval", "1h"))
            next_run = (datetime.now() + timedelta(seconds=interval)).isoformat()
        elif job["trigger_type"] == "datetime":
            next_run = None  # one-shot

        db = await _get_db()
        try:
            await db.execute(
                """INSERT INTO job_runs (id, job_id, started_at, finished_at, status, output, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, job["id"], started, finished, status, output[:4096], error[:2048]),
            )
            await db.execute(
                """UPDATE scheduled_jobs SET last_run=?, next_run=?, run_count=run_count+1,
                   updated_at=? WHERE id=?""",
                (finished, next_run, finished, job["id"]),
            )
            await db.commit()
        finally:
            await db.close()

        # Fire callback if set
        if self._on_execute:
            try:
                await self._on_execute(job, {"status": status, "output": output, "error": error})
            except Exception:
                pass

    async def _execute_action(self, action_type: str, action_data: dict) -> str:
        if action_type == "shell":
            cmd = action_data.get("command", "")
            r = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(r.communicate(), timeout=300)
            return stdout.decode(errors="replace") or stderr.decode(errors="replace")

        elif action_type == "agent_task":
            # Will be wired to the agent planner/executor
            return f"Agent task scheduled: {action_data.get('message', '')}"

        elif action_type == "notify":
            import shutil as _sh
            import subprocess as _sp
            if _sh.which("notify-send"):
                _sp.run(
                    ["notify-send", action_data.get("title", "JARVIS"), action_data.get("body", "")],
                    timeout=3,
                )
            return "Notification sent"

        return f"Unknown action type: {action_type}"

    # ── CRUD API ────────────────────────────────────────────────────────

    async def create_job(self, job_data: dict) -> dict:
        """Create and persist a new scheduled job."""
        import uuid
        job_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        trigger_data = job_data.get("trigger_data", {})
        trigger_type = job_data.get("trigger_type", "interval")

        # Calculate initial next_run
        next_run = None
        if trigger_type == "interval":
            interval = _parse_interval(trigger_data.get("interval", "1h"))
            next_run = (datetime.now() + timedelta(seconds=interval)).isoformat()
        elif trigger_type == "datetime":
            next_run = trigger_data.get("datetime", now)

        db = await _get_db()
        try:
            await db.execute(
                """INSERT INTO scheduled_jobs
                   (id, name, description, trigger_type, trigger_data, action_type, action_data,
                    enabled, next_run, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
                (
                    job_id,
                    job_data.get("name", "Unnamed Job"),
                    job_data.get("description", ""),
                    trigger_type,
                    json.dumps(trigger_data),
                    job_data.get("action_type", "shell"),
                    json.dumps(job_data.get("action_data", {})),
                    next_run,
                    now,
                    now,
                ),
            )
            await db.commit()
        finally:
            await db.close()

        return await self.get_job(job_id)

    async def get_job(self, job_id: str) -> Optional[dict]:
        db = await _get_db()
        try:
            cursor = await db.execute("SELECT * FROM scheduled_jobs WHERE id=?", (job_id,))
            row = await cursor.fetchone()
            return _deserialize_job(dict(row)) if row else None
        finally:
            await db.close()

    async def list_jobs(self) -> list:
        db = await _get_db()
        try:
            cursor = await db.execute("SELECT * FROM scheduled_jobs ORDER BY created_at DESC")
            return [_deserialize_job(dict(r)) for r in await cursor.fetchall()]
        finally:
            await db.close()

    async def update_job(self, job_id: str, updates: dict) -> Optional[dict]:
        db = await _get_db()
        now = datetime.now().isoformat()
        try:
            allowed = {"name", "description", "enabled", "trigger_data", "action_data"}
            for key, val in updates.items():
                if key in allowed:
                    v = json.dumps(val) if isinstance(val, dict) else val
                    await db.execute(
                        f"UPDATE scheduled_jobs SET {key}=?, updated_at=? WHERE id=?",
                        (v, now, job_id),
                    )
            await db.commit()
        finally:
            await db.close()
        return await self.get_job(job_id)

    async def delete_job(self, job_id: str):
        db = await _get_db()
        try:
            await db.execute("DELETE FROM scheduled_jobs WHERE id=?", (job_id,))
            await db.execute("DELETE FROM job_runs WHERE job_id=?", (job_id,))
            await db.commit()
        finally:
            await db.close()

    async def get_job_runs(self, job_id: str, limit: int = 20) -> list:
        db = await _get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM job_runs WHERE job_id=? ORDER BY started_at DESC LIMIT ?",
                (job_id, limit),
            )
            return [dict(r) for r in await cursor.fetchall()]
        finally:
            await db.close()

    async def run_now(self, job_id: str):
        """Trigger a job immediately (regardless of schedule)."""
        job = await self.get_job(job_id)
        if job:
            asyncio.create_task(self._run_job(job))


def _deserialize_job(row: dict) -> dict:
    for field in ("trigger_data", "action_data"):
        if isinstance(row.get(field), str):
            try:
                row[field] = json.loads(row[field])
            except Exception:
                pass
    return row


def _uuid() -> str:
    import uuid
    return str(uuid.uuid4())


# Global instance
scheduler_service = SchedulerService()
