"""
Application Integration Plugin Tools.

Makes the agent useful every day with integrations for:
  - VS Code (open files, run extensions)
  - Docker (containers, images, logs)
  - Git (status, log, branch, commit, diff)
  - Package managers (apt, pip, npm, snap)
  - HTTP/API testing (GET, POST, PUT, DELETE)
"""

import asyncio
import json
import os
import shutil
import subprocess
import time
from typing import Dict, List, Optional

import httpx

from tools.base import Tool, ToolResult


# ── VS Code ───────────────────────────────────────────────────────────────────

class VSCodeOpenTool(Tool):
    name = "vscode_open"
    description = "Open a file or folder in VS Code (or code-server / codium)."
    parameters_schema = {
        "path":       "File or directory path to open.",
        "line":       "(optional) Line number to jump to.",
        "new_window": "(optional) Open in a new VS Code window. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        line = args.get("line")
        new_window = args.get("new_window", False)

        editor = _has_editor()
        if not editor:
            return ToolResult(success=False, message="VS Code not found. Install code, codium, or code-server.")

        target = f"{path}:{line}" if line else path
        cmd = [editor, target]
        if new_window:
            cmd.insert(1, "--new-window")

        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=10)
        return ToolResult(
            success=r.returncode == 0,
            message=f"Opened {path} in {editor}" if r.returncode == 0 else r.stderr.decode(errors="replace"),
        )


class VSCodeRunCommandTool(Tool):
    name = "vscode_run_command"
    description = "Execute a task or run tests via VS Code CLI (code --command)."
    parameters_schema = {
        "command": "VS Code command to execute (e.g., 'workbench.action.tasks.runTask').",
    }

    async def execute(self, args: Dict) -> ToolResult:
        cmd_name = args.get("command", "")
        editor = _has_editor()
        if not editor:
            return ToolResult(success=False, message="VS Code not found.")
        r = await asyncio.to_thread(
            subprocess.run, [editor, "--command", cmd_name], capture_output=True, timeout=15
        )
        return ToolResult(
            success=r.returncode == 0,
            message=r.stdout.decode(errors="replace") or r.stderr.decode(errors="replace") or f"Command sent: {cmd_name}",
        )


def _has_editor() -> Optional[str]:
    for e in ["code", "codium", "code-insiders", "code-server"]:
        if shutil.which(e):
            return e
    return None


# ── Docker ────────────────────────────────────────────────────────────────────

class DockerListTool(Tool):
    name = "docker_list"
    description = "List Docker containers or images."
    parameters_schema = {
        "type": "'containers' | 'images'. Default 'containers'.",
        "all":  "(optional) Include stopped containers. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        if not shutil.which("docker"):
            return ToolResult(success=False, message="Docker not found in PATH.")

        list_type = args.get("type", "containers")
        include_all = args.get("all", False)

        if list_type == "images":
            cmd = ["docker", "images", "--format", "json"]
        else:
            cmd = ["docker", "ps", "--format", "json"]
            if include_all:
                cmd.insert(2, "-a")

        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=15)
        if r.returncode != 0:
            return ToolResult(success=False, message=r.stderr.decode(errors="replace"))

        items = []
        for line in r.stdout.decode(errors="replace").strip().splitlines():
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                pass

        return ToolResult(
            success=True,
            data={"items": items, "count": len(items), "type": list_type},
            message=f"{len(items)} Docker {list_type}",
        )


class DockerActionTool(Tool):
    name = "docker_action"
    description = "Start, stop, restart, remove a Docker container."
    parameters_schema = {
        "action":       "'start' | 'stop' | 'restart' | 'rm' | 'pull'",
        "container":    "Container name or ID (for start/stop/restart/rm).",
        "image":        "(optional) Image name for 'pull'.",
        "force":        "(optional) Force remove. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        if not shutil.which("docker"):
            return ToolResult(success=False, message="Docker not found in PATH.")

        action    = args.get("action", "")
        container = args.get("container", "")
        image     = args.get("image", "")
        force     = args.get("force", False)

        if action == "pull":
            cmd = ["docker", "pull", image or container]
        elif action == "rm":
            cmd = ["docker", "rm", "--force" if force else "", container]
            cmd = [c for c in cmd if c]
        elif action in ("start", "stop", "restart"):
            cmd = ["docker", action, container]
        else:
            return ToolResult(success=False, message=f"Unknown action: {action}")

        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=60)
        return ToolResult(
            success=r.returncode == 0,
            data={"stdout": r.stdout.decode(errors="replace")},
            message=r.stderr.decode(errors="replace") or f"docker {action} completed",
        )


class DockerLogsTool(Tool):
    name = "docker_logs"
    description = "Get logs from a running or stopped Docker container."
    parameters_schema = {
        "container": "Container name or ID.",
        "tail":      "(optional) Number of lines from end. Default 50.",
        "since":     "(optional) Timestamp or relative time, e.g. '10m'.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        if not shutil.which("docker"):
            return ToolResult(success=False, message="Docker not found in PATH.")

        container = args.get("container", "")
        tail      = str(args.get("tail", 50))
        since     = args.get("since", "")

        cmd = ["docker", "logs", "--tail", tail, container]
        if since:
            cmd = ["docker", "logs", "--tail", tail, "--since", since, container]

        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=15)
        output = r.stdout.decode(errors="replace") + r.stderr.decode(errors="replace")
        return ToolResult(
            success=r.returncode == 0,
            data={"logs": output, "container": container},
            message=f"Logs from {container}",
        )


class DockerExecTool(Tool):
    name = "docker_exec"
    description = "Execute a command inside a running Docker container."
    parameters_schema = {
        "container": "Container name or ID.",
        "command":   "Shell command to run (passed to sh -c).",
    }

    async def execute(self, args: Dict) -> ToolResult:
        if not shutil.which("docker"):
            return ToolResult(success=False, message="Docker not found in PATH.")

        container = args.get("container", "")
        command   = args.get("command", "")

        cmd = ["docker", "exec", container, "sh", "-c", command]
        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=30)
        return ToolResult(
            success=r.returncode == 0,
            data={
                "stdout": r.stdout.decode(errors="replace"),
                "stderr": r.stderr.decode(errors="replace"),
                "exit_code": r.returncode,
            },
            message=f"Executed in {container}: {command[:60]}",
        )


# ── Package Managers ──────────────────────────────────────────────────────────

class PackageManagerTool(Tool):
    name = "package_manager"
    description = (
        "Interact with system package managers: apt, pip, npm, snap, flatpak. "
        "Supports: list, install, remove, update, search."
    )
    parameters_schema = {
        "manager":  "'apt' | 'pip' | 'npm' | 'snap' | 'flatpak'",
        "action":   "'list' | 'install' | 'remove' | 'update' | 'search'",
        "package":  "(optional) Package name for install/remove/search.",
        "global":   "(optional) npm global flag. Default false.",
        "dry_run":  "(optional) Print command without running (for install/remove). Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        manager  = args.get("manager", "apt")
        action   = args.get("action", "list")
        package  = args.get("package", "")
        npm_global = args.get("global", False)
        dry_run  = args.get("dry_run", False)

        cmd, confirm_needed = self._build_cmd(manager, action, package, npm_global, dry_run)
        if cmd is None:
            return ToolResult(success=False, message=confirm_needed)

        if dry_run:
            return ToolResult(success=True, data={"command": " ".join(cmd)}, message=f"[dry_run] Would run: {' '.join(cmd)}")

        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=120)
        out = r.stdout.decode(errors="replace")
        err = r.stderr.decode(errors="replace")
        return ToolResult(
            success=r.returncode == 0,
            data={"stdout": out, "stderr": err},
            message=err or out or f"{manager} {action} completed",
        )

    @staticmethod
    def _build_cmd(manager, action, package, npm_global, dry_run):
        if not shutil.which(manager if manager != "pip" else "pip3"):
            if manager == "pip" and not shutil.which("pip"):
                return None, f"{manager} not found in PATH"

        if manager == "apt":
            if action == "list":        return ["apt", "list", "--installed"], ""
            if action == "search":      return ["apt", "search", package], ""
            if action == "install":     return ["sudo", "apt", "install", "-y", package], ""
            if action == "remove":      return ["sudo", "apt", "remove", "-y", package], ""
            if action == "update":      return ["sudo", "apt", "update"], ""

        elif manager == "pip":
            pip = shutil.which("pip3") or "pip"
            if action == "list":        return [pip, "list"], ""
            if action == "search":      return [pip, "index", "versions", package], ""
            if action == "install":     return [pip, "install", package], ""
            if action == "remove":      return [pip, "uninstall", "-y", package], ""
            if action == "update":      return [pip, "install", "--upgrade", package or "pip"], ""

        elif manager == "npm":
            flags = ["-g"] if npm_global else []
            if action == "list":        return ["npm", "list"] + flags, ""
            if action == "search":      return ["npm", "search", package], ""
            if action == "install":     return ["npm", "install"] + flags + [package], ""
            if action == "remove":      return ["npm", "uninstall"] + flags + [package], ""
            if action == "update":      return ["npm", "update"] + flags, ""

        elif manager == "snap":
            if action == "list":        return ["snap", "list"], ""
            if action == "search":      return ["snap", "find", package], ""
            if action == "install":     return ["sudo", "snap", "install", package], ""
            if action == "remove":      return ["sudo", "snap", "remove", package], ""
            if action == "update":      return ["sudo", "snap", "refresh"], ""

        elif manager == "flatpak":
            if action == "list":        return ["flatpak", "list"], ""
            if action == "search":      return ["flatpak", "search", package], ""
            if action == "install":     return ["flatpak", "install", "-y", package], ""
            if action == "remove":      return ["flatpak", "uninstall", "-y", package], ""
            if action == "update":      return ["flatpak", "update", "-y"], ""

        return None, f"Unknown manager/action: {manager}/{action}"


# ── HTTP / API Testing ────────────────────────────────────────────────────────

class HTTPRequestTool(Tool):
    name = "http_request"
    description = (
        "Make HTTP requests (GET, POST, PUT, PATCH, DELETE). "
        "Supports headers, query params, JSON body, form data. "
        "Returns status, headers, and parsed response."
    )
    parameters_schema = {
        "url":         "Full URL to request.",
        "method":      "(optional) HTTP method. Default 'GET'.",
        "headers":     "(optional) Dict of request headers.",
        "params":      "(optional) Dict of URL query parameters.",
        "json_body":   "(optional) Dict to send as JSON body.",
        "form_data":   "(optional) Dict to send as form data.",
        "text_body":   "(optional) Raw string body.",
        "timeout":     "(optional) Timeout seconds. Default 30.",
        "follow_redirects": "(optional) Follow redirects. Default true.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        url     = args.get("url", "")
        method  = args.get("method", "GET").upper()
        headers = args.get("headers") or {}
        params  = args.get("params") or {}
        timeout = float(args.get("timeout", 30))
        follow  = args.get("follow_redirects", True)

        json_body  = args.get("json_body")
        form_data  = args.get("form_data")
        text_body  = args.get("text_body")

        try:
            async with httpx.AsyncClient(follow_redirects=follow, timeout=timeout) as client:
                req_kwargs: dict = {"headers": headers, "params": params}
                if json_body is not None:
                    req_kwargs["json"] = json_body
                elif form_data:
                    req_kwargs["data"] = form_data
                elif text_body:
                    req_kwargs["content"] = text_body.encode()

                r = await client.request(method, url, **req_kwargs)

                # Try to parse JSON response
                try:
                    body = r.json()
                except Exception:
                    body = r.text

                return ToolResult(
                    success=True,
                    data={
                        "status_code": r.status_code,
                        "headers": dict(r.headers),
                        "body": body,
                        "elapsed_ms": round(r.elapsed.total_seconds() * 1000, 1) if r.elapsed else None,
                        "url": str(r.url),
                    },
                    message=f"{method} {url} → {r.status_code}",
                )
        except Exception as e:
            return ToolResult(success=False, message=f"HTTP request failed: {e}")


# ── SQLite Query ──────────────────────────────────────────────────────────────

class SQLiteQueryTool(Tool):
    name = "sqlite_query"
    description = "Execute a SQL query against a local SQLite database file."
    parameters_schema = {
        "database": "Absolute path to the .db / .sqlite file.",
        "sql":      "SQL statement to execute.",
        "params":   "(optional) List of parameter values for ? placeholders.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        db_path = os.path.expanduser(args.get("database", ""))
        sql     = args.get("sql", "")
        params  = args.get("params") or []

        if not db_path or not os.path.exists(db_path):
            return ToolResult(success=False, message=f"Database not found: {db_path}")

        return await asyncio.to_thread(self._run_query, db_path, sql, params)

    @staticmethod
    def _run_query(db_path: str, sql: str, params: list) -> ToolResult:
        import sqlite3
        try:
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute(sql, params)
            con.commit()

            rows = []
            if cur.description:
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]

            con.close()
            return ToolResult(
                success=True,
                data={"rows": rows, "row_count": len(rows), "affected": cur.rowcount},
                message=f"Query executed: {len(rows)} row(s) returned, {cur.rowcount} affected",
            )
        except Exception as e:
            return ToolResult(success=False, message=f"SQLite error: {e}")


class SQLiteListTablesTool(Tool):
    name = "sqlite_list_tables"
    description = "List all tables and their schemas in a SQLite database."
    parameters_schema = {
        "database": "Absolute path to the .db / .sqlite file.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        db_path = os.path.expanduser(args.get("database", ""))
        if not db_path or not os.path.exists(db_path):
            return ToolResult(success=False, message=f"Database not found: {db_path}")
        return await asyncio.to_thread(self._list, db_path)

    @staticmethod
    def _list(db_path: str) -> ToolResult:
        import sqlite3
        try:
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [r[0] for r in cur.fetchall()]
            schemas = {}
            for t in tables:
                cur.execute(f"PRAGMA table_info({t})")
                schemas[t] = [{"cid": r[0], "name": r[1], "type": r[2]} for r in cur.fetchall()]
            con.close()
            return ToolResult(
                success=True,
                data={"tables": tables, "schemas": schemas},
                message=f"{len(tables)} table(s) found",
            )
        except Exception as e:
            return ToolResult(success=False, message=f"SQLite error: {e}")


# ── Registry ─────────────────────────────────────────────────────────────────

ALL_PLUGIN_TOOLS = [
    VSCodeOpenTool(),
    VSCodeRunCommandTool(),
    DockerListTool(),
    DockerActionTool(),
    DockerLogsTool(),
    DockerExecTool(),
    PackageManagerTool(),
    HTTPRequestTool(),
    SQLiteQueryTool(),
    SQLiteListTablesTool(),
]
