"""
Enhanced Terminal Tools.
Interactive sessions, history, process management.
"""

import os
import signal
import subprocess
from typing import Dict, List

import psutil

from tools.base import Tool, ToolResult


class TerminalSessionTool(Tool):
    name = "terminal_session"
    description = "Execute shell command in working directory"
    parameters_schema = {
        "command": "Shell command to execute",
        "cwd": "(optional) Working directory. Default current dir.",
        "timeout": "(optional) Timeout in seconds. Default 30.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        command = args.get("command", "")
        cwd = os.path.expanduser(args.get("cwd", "."))
        timeout = int(args.get("timeout", 30))

        if not command:
            return ToolResult(success=False, message="Command required")

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return ToolResult(
                success=result.returncode == 0,
                data={
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                    "command": command,
                },
                message=f"Exit code: {result.returncode}",
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False, message=f"Command timed out after {timeout}s"
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Execution failed: {str(e)}")


class TerminalHistoryTool(Tool):
    name = "terminal_history"
    description = "View shell command history"
    parameters_schema = {
        "limit": "(optional) Number of commands. Default 20.",
        "filter": "(optional) Filter by keyword",
    }

    async def execute(self, args: Dict) -> ToolResult:
        limit = int(args.get("limit", 20))
        filter_keyword = args.get("filter", "")

        # Try to read bash/zsh history
        history_files = [
            os.path.expanduser("~/.bash_history"),
            os.path.expanduser("~/.zsh_history"),
        ]

        history = []
        for hfile in history_files:
            if os.path.exists(hfile):
                try:
                    with open(hfile, "r", errors="ignore") as f:
                        lines = f.readlines()
                        history.extend([l.strip() for l in lines if l.strip()])
                    break
                except:
                    continue

        if not history:
            return ToolResult(
                success=True, data={"commands": []}, message="No history found"
            )

        # Filter if keyword provided
        if filter_keyword:
            history = [h for h in history if filter_keyword.lower() in h.lower()]

        # Get last N commands
        recent = history[-limit:] if len(history) > limit else history

        return ToolResult(
            success=True,
            data={"commands": recent, "total": len(history)},
            message=f"{len(recent)} command(s) in history",
        )


class ProcessListTool(Tool):
    name = "process_list"
    description = "List running processes"
    parameters_schema = {
        "filter": "(optional) Filter by name/command",
        "user": "(optional) Filter by username",
        "limit": "(optional) Max results. Default 50.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        filter_name = args.get("filter", "").lower()
        user_filter = args.get("user", "")
        limit = int(args.get("limit", 50))

        try:
            processes = []

            for proc in psutil.process_iter(
                ["pid", "name", "username", "cpu_percent", "memory_percent"]
            ):
                try:
                    pinfo = proc.info

                    # Apply filters
                    if user_filter and pinfo["username"] != user_filter:
                        continue
                    if filter_name and filter_name not in pinfo["name"].lower():
                        continue

                    processes.append(
                        {
                            "pid": pinfo["pid"],
                            "name": pinfo["name"],
                            "user": pinfo["username"],
                            "cpu": round(pinfo["cpu_percent"] or 0, 1),
                            "memory": round(pinfo["memory_percent"] or 0, 1),
                        }
                    )

                    if len(processes) >= limit:
                        break

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Sort by CPU usage
            processes.sort(key=lambda x: x["cpu"], reverse=True)

            return ToolResult(
                success=True,
                data={"processes": processes, "count": len(processes)},
                message=f"Found {len(processes)} process(es)",
            )

        except Exception as e:
            return ToolResult(
                success=False, message=f"Failed to list processes: {str(e)}"
            )


class KillProcessTool(Tool):
    name = "kill_process"
    description = "Terminate a process by PID. REQUIRES CONFIRMATION."
    parameters_schema = {
        "pid": "Process ID to terminate",
        "force": "(optional) Force kill (SIGKILL). Default false (SIGTERM).",
    }

    async def execute(self, args: Dict) -> ToolResult:
        try:
            pid = int(args.get("pid", 0))
            force = args.get("force", False)
        except ValueError:
            return ToolResult(success=False, message="Invalid PID")

        if pid <= 0:
            return ToolResult(success=False, message="PID required")

        try:
            proc = psutil.Process(pid)
            proc_name = proc.name()

            # Send signal
            sig = signal.SIGKILL if force else signal.SIGTERM
            proc.send_signal(sig)

            # Wait a bit and check if terminated
            try:
                proc.wait(timeout=3)
                terminated = True
            except psutil.TimeoutExpired:
                terminated = proc.status() == psutil.STATUS_ZOMBIE

            return ToolResult(
                success=True,
                data={
                    "pid": pid,
                    "name": proc_name,
                    "signal": "SIGKILL" if force else "SIGTERM",
                    "terminated": terminated,
                },
                message=f"Sent {'SIGKILL' if force else 'SIGTERM'} to {proc_name} ({pid})",
            )

        except psutil.NoSuchProcess:
            return ToolResult(success=False, message=f"Process {pid} not found")
        except psutil.AccessDenied:
            return ToolResult(success=False, message=f"Permission denied to kill {pid}")
        except Exception as e:
            return ToolResult(
                success=False, message=f"Failed to kill process: {str(e)}"
            )


class EnvVarsTool(Tool):
    name = "env_vars"
    description = "List or get environment variables"
    parameters_schema = {
        "var": "(optional) Specific variable name. If omitted, lists all.",
        "filter": "(optional) Filter by keyword",
    }

    async def execute(self, args: Dict) -> ToolResult:
        var_name = args.get("var", "")
        filter_keyword = args.get("filter", "").lower()

        if var_name:
            # Get specific variable
            value = os.environ.get(var_name)
            if value is None:
                return ToolResult(
                    success=False, message=f"Variable '{var_name}' not found"
                )

            return ToolResult(
                success=True,
                data={"variable": var_name, "value": value},
                message=f"{var_name}={value}",
            )

        # List all or filtered
        env_vars = {}
        for key, value in os.environ.items():
            if filter_keyword and filter_keyword not in key.lower():
                continue
            env_vars[key] = value

        return ToolResult(
            success=True,
            data={"variables": env_vars, "count": len(env_vars)},
            message=f"{len(env_vars)} variable(s)",
        )


ALL_TERMINAL_TOOLS = [
    TerminalSessionTool(),
    TerminalHistoryTool(),
    ProcessListTool(),
    KillProcessTool(),
    EnvVarsTool(),
]
