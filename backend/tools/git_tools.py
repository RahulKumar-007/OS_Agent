"""
Git Integration Tools.
Version control operations: status, commit, diff, branch, push, pull.
"""

import os
import subprocess
from typing import Dict, List

from tools.base import Tool, ToolResult


def _run_git(args: List[str], cwd: str) -> tuple:
    """Run git command and return (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=30
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Git command timed out", 1
    except Exception as e:
        return "", str(e), 1


class GitStatusTool(Tool):
    name = "git_status"
    description = "Show git working tree status (modified, staged, untracked files)"
    parameters_schema = {
        "path": "Repository path (default: current directory)",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", "."))

        stdout, stderr, code = _run_git(["status", "--porcelain"], path)

        if code != 0:
            return ToolResult(success=False, message=f"Git error: {stderr}")

        # Parse porcelain output
        changes = {
            "modified": [],
            "staged": [],
            "untracked": [],
            "deleted": [],
        }

        for line in stdout.strip().split("\n"):
            if not line:
                continue
            status = line[:2]
            filepath = line[3:]

            if status[0] in ["M", "A"]:
                changes["staged"].append(filepath)
            if status[1] == "M":
                changes["modified"].append(filepath)
            elif status == "??":
                changes["untracked"].append(filepath)
            elif status[1] == "D":
                changes["deleted"].append(filepath)

        total = sum(len(v) for v in changes.values())

        return ToolResult(
            success=True,
            data={
                "changes": changes,
                "total": total,
                "clean": total == 0,
            },
            message=f"{total} file(s) changed" if total else "Working tree clean",
        )


class GitAddTool(Tool):
    name = "git_add"
    description = "Stage files for commit"
    parameters_schema = {
        "path": "Repository path",
        "files": "Files to stage (comma-separated) or '.' for all",
    }

    async def execute(self, args: Dict) -> ToolResult:
        repo_path = os.path.expanduser(args.get("path", "."))
        files = args.get("files", ".")

        file_list = [f.strip() for f in files.split(",")] if files != "." else ["."]

        stdout, stderr, code = _run_git(["add"] + file_list, repo_path)

        if code != 0:
            return ToolResult(success=False, message=f"Git add failed: {stderr}")

        return ToolResult(
            success=True,
            data={"staged": file_list},
            message=f"Staged {len(file_list)} file(s)",
        )


class GitCommitTool(Tool):
    name = "git_commit"
    description = "Commit staged changes with message"
    parameters_schema = {
        "path": "Repository path",
        "message": "Commit message (required)",
        "add_all": "(optional) Stage all changes before commit. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        repo_path = os.path.expanduser(args.get("path", "."))
        message = args.get("message", "")
        add_all = args.get("add_all", False)

        if not message:
            return ToolResult(success=False, message="Commit message required")

        # Optionally add all
        if add_all:
            _run_git(["add", "-A"], repo_path)

        stdout, stderr, code = _run_git(["commit", "-m", message], repo_path)

        if code != 0:
            return ToolResult(success=False, message=f"Commit failed: {stderr}")

        # Extract commit hash
        commit_hash = ""
        for line in stdout.split("\n"):
            if "branch" in line.lower() or "main" in line.lower():
                parts = line.split()
                if len(parts) > 1:
                    commit_hash = parts[1].strip("[]")
                    break

        return ToolResult(
            success=True,
            data={"commit": commit_hash, "message": message},
            message=f"Committed: {commit_hash[:7]}",
        )


class GitDiffTool(Tool):
    name = "git_diff"
    description = "Show changes between commits, working tree, etc"
    parameters_schema = {
        "path": "Repository path",
        "file": "(optional) Specific file to diff",
        "staged": "(optional) Show staged changes. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        repo_path = os.path.expanduser(args.get("path", "."))
        file = args.get("file", "")
        staged = args.get("staged", False)

        cmd = ["diff"]
        if staged:
            cmd.append("--cached")
        if file:
            cmd.append(file)

        stdout, stderr, code = _run_git(cmd, repo_path)

        if code != 0:
            return ToolResult(success=False, message=f"Diff failed: {stderr}")

        if not stdout.strip():
            return ToolResult(success=True, data={"diff": ""}, message="No changes")

        return ToolResult(
            success=True,
            data={"diff": stdout, "length": len(stdout)},
            message=f"Diff: {len(stdout)} chars",
        )


class GitLogTool(Tool):
    name = "git_log"
    description = "Show commit history"
    parameters_schema = {
        "path": "Repository path",
        "limit": "(optional) Number of commits. Default 10.",
        "oneline": "(optional) One line per commit. Default true.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        repo_path = os.path.expanduser(args.get("path", "."))
        limit = int(args.get("limit", 10))
        oneline = args.get("oneline", True)

        cmd = ["log", f"-{limit}"]
        if oneline:
            cmd.append("--oneline")

        stdout, stderr, code = _run_git(cmd, repo_path)

        if code != 0:
            return ToolResult(success=False, message=f"Log failed: {stderr}")

        commits = []
        for line in stdout.strip().split("\n"):
            if line:
                commits.append(line)

        return ToolResult(
            success=True,
            data={"commits": commits, "count": len(commits)},
            message=f"Last {len(commits)} commit(s)",
        )


class GitBranchTool(Tool):
    name = "git_branch"
    description = "List, create, or delete branches"
    parameters_schema = {
        "path": "Repository path",
        "action": "(optional) 'list', 'create', 'delete'. Default 'list'.",
        "branch_name": "(optional) Branch name for create/delete",
    }

    async def execute(self, args: Dict) -> ToolResult:
        repo_path = os.path.expanduser(args.get("path", "."))
        action = args.get("action", "list").lower()
        branch_name = args.get("branch_name", "")

        if action == "list":
            stdout, stderr, code = _run_git(["branch", "-a"], repo_path)
            if code != 0:
                return ToolResult(
                    success=False, message=f"Branch list failed: {stderr}"
                )

            branches = []
            current = ""
            for line in stdout.strip().split("\n"):
                if line.startswith("*"):
                    current = line[2:].strip()
                    branches.append({"name": current, "current": True})
                else:
                    branches.append({"name": line.strip(), "current": False})

            return ToolResult(
                success=True,
                data={"branches": branches, "current": current},
                message=f"{len(branches)} branch(es), current: {current}",
            )

        elif action == "create":
            if not branch_name:
                return ToolResult(success=False, message="Branch name required")

            stdout, stderr, code = _run_git(["branch", branch_name], repo_path)
            if code != 0:
                return ToolResult(success=False, message=f"Create failed: {stderr}")

            return ToolResult(
                success=True,
                data={"branch": branch_name},
                message=f"Created branch: {branch_name}",
            )

        elif action == "delete":
            if not branch_name:
                return ToolResult(success=False, message="Branch name required")

            stdout, stderr, code = _run_git(["branch", "-d", branch_name], repo_path)
            if code != 0:
                return ToolResult(success=False, message=f"Delete failed: {stderr}")

            return ToolResult(
                success=True,
                data={"branch": branch_name},
                message=f"Deleted branch: {branch_name}",
            )

        return ToolResult(success=False, message=f"Invalid action: {action}")


class GitCheckoutTool(Tool):
    name = "git_checkout"
    description = "Switch branches or restore files"
    parameters_schema = {
        "path": "Repository path",
        "branch": "Branch name to checkout",
        "create": "(optional) Create new branch. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        repo_path = os.path.expanduser(args.get("path", "."))
        branch = args.get("branch", "")
        create = args.get("create", False)

        if not branch:
            return ToolResult(success=False, message="Branch name required")

        cmd = ["checkout"]
        if create:
            cmd.append("-b")
        cmd.append(branch)

        stdout, stderr, code = _run_git(cmd, repo_path)

        if code != 0:
            return ToolResult(success=False, message=f"Checkout failed: {stderr}")

        action = "Created and switched to" if create else "Switched to"
        return ToolResult(
            success=True,
            data={"branch": branch, "created": create},
            message=f"{action} branch: {branch}",
        )


class GitPushTool(Tool):
    name = "git_push"
    description = "Push commits to remote repository"
    parameters_schema = {
        "path": "Repository path",
        "remote": "(optional) Remote name. Default 'origin'.",
        "branch": "(optional) Branch to push. Default current branch.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        repo_path = os.path.expanduser(args.get("path", "."))
        remote = args.get("remote", "origin")
        branch = args.get("branch", "")

        cmd = ["push", remote]
        if branch:
            cmd.append(branch)

        stdout, stderr, code = _run_git(cmd, repo_path)

        # Git push often writes to stderr even on success
        if code != 0 and "error" in stderr.lower():
            return ToolResult(success=False, message=f"Push failed: {stderr}")

        return ToolResult(
            success=True,
            data={"remote": remote, "branch": branch or "current"},
            message=f"Pushed to {remote}",
        )


class GitPullTool(Tool):
    name = "git_pull"
    description = "Fetch and merge from remote repository"
    parameters_schema = {
        "path": "Repository path",
        "remote": "(optional) Remote name. Default 'origin'.",
        "branch": "(optional) Branch to pull. Default current branch.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        repo_path = os.path.expanduser(args.get("path", "."))
        remote = args.get("remote", "origin")
        branch = args.get("branch", "")

        cmd = ["pull", remote]
        if branch:
            cmd.append(branch)

        stdout, stderr, code = _run_git(cmd, repo_path)

        if code != 0:
            return ToolResult(success=False, message=f"Pull failed: {stderr}")

        # Check if up to date
        if "Already up to date" in stdout:
            return ToolResult(
                success=True,
                data={"status": "up-to-date"},
                message="Already up to date",
            )

        return ToolResult(
            success=True,
            data={"remote": remote, "output": stdout[:200]},
            message="Pulled changes",
        )


ALL_GIT_TOOLS = [
    GitStatusTool(),
    GitAddTool(),
    GitCommitTool(),
    GitDiffTool(),
    GitLogTool(),
    GitBranchTool(),
    GitCheckoutTool(),
    GitPushTool(),
    GitPullTool(),
]
