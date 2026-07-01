"""
Filesystem tools for the agent.
Handles: list_directory, read_file_metadata, search_files,
         move_file, copy_file, rename_file, delete_file, create_directory
"""

import glob
import os
import shutil
import stat
from datetime import datetime
from typing import Dict

from tools.base import Tool, ToolResult


class ListDirectoryTool(Tool):
    name = "list_directory"
    description = "List all files and folders in a directory. Returns names, types, sizes, and modification dates."
    parameters_schema = {
        "path": "Absolute path to the directory to list",
        "recursive": "(optional) If true, list recursively. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        recursive = args.get("recursive", False)

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")
        if not os.path.isdir(path):
            return ToolResult(success=False, message=f"Not a directory: {path}")

        entries = []
        try:
            if recursive:
                for root, dirs, files in os.walk(path):
                    for name in dirs + files:
                        full_path = os.path.join(root, name)
                        try:
                            st = os.stat(full_path)
                            entries.append(
                                {
                                    "name": name,
                                    "path": full_path,
                                    "is_dir": os.path.isdir(full_path),
                                    "size": st.st_size,
                                    "modified": datetime.fromtimestamp(
                                        st.st_mtime
                                    ).isoformat(),
                                }
                            )
                        except (PermissionError, OSError):
                            continue
            else:
                for name in os.listdir(path):
                    full_path = os.path.join(path, name)
                    try:
                        st = os.stat(full_path)
                        entries.append(
                            {
                                "name": name,
                                "path": full_path,
                                "is_dir": os.path.isdir(full_path),
                                "size": st.st_size,
                                "modified": datetime.fromtimestamp(
                                    st.st_mtime
                                ).isoformat(),
                            }
                        )
                    except (PermissionError, OSError):
                        continue

            return ToolResult(
                success=True,
                data=entries,
                message=f"Found {len(entries)} items in {path}",
            )
        except PermissionError:
            return ToolResult(success=False, message=f"Permission denied: {path}")


class ReadFileMetadataTool(Tool):
    name = "read_file_metadata"
    description = "Read metadata (size, type, permissions, dates) of a file without reading its content."
    parameters_schema = {
        "path": "Absolute path to the file",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")

        try:
            st = os.stat(path)
            metadata = {
                "path": path,
                "name": os.path.basename(path),
                "extension": os.path.splitext(path)[1],
                "size": st.st_size,
                "is_dir": os.path.isdir(path),
                "permissions": stat.filemode(st.st_mode),
                "created": datetime.fromtimestamp(st.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                "accessed": datetime.fromtimestamp(st.st_atime).isoformat(),
            }
            return ToolResult(
                success=True, data=metadata, message=f"Metadata for {path}"
            )
        except PermissionError:
            return ToolResult(success=False, message=f"Permission denied: {path}")


class SearchFilesTool(Tool):
    name = "search_files"
    description = "Search for files matching a glob pattern. Use '**/' prefix for recursive search across subdirectories."
    parameters_schema = {
        "path": "Directory to search in",
        "pattern": "Glob pattern. Use '**/' for recursive: '*.pdf' (current dir only), '**/*.pdf' (recursive), '**/*keyword*.pdf' (recursive with keyword)",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        pattern = args.get("pattern", "*")

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")

        try:
            search_pattern = os.path.join(path, pattern)
            matches = glob.glob(search_pattern, recursive=True)
            results = []
            for match in matches:
                try:
                    st = os.stat(match)
                    results.append(
                        {
                            "path": match,
                            "name": os.path.basename(match),
                            "size": st.st_size,
                            "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                        }
                    )
                except (PermissionError, OSError):
                    continue

            return ToolResult(
                success=True,
                data=results,
                message=f"Found {len(results)} files matching '{pattern}' in {path}",
            )
        except Exception as e:
            return ToolResult(success=False, message=str(e))


class MoveFileTool(Tool):
    name = "move_file"
    description = "Move a file or directory from source to target path."
    parameters_schema = {
        "source": "Source path (file or directory)",
        "target": "Target path",
    }

    async def execute(self, args: Dict) -> ToolResult:
        source = os.path.expanduser(args.get("source", ""))
        target = os.path.expanduser(args.get("target", ""))

        if not os.path.exists(source):
            return ToolResult(success=False, message=f"Source does not exist: {source}")

        try:
            # Create target directory if needed
            target_dir = (
                os.path.dirname(target) if not os.path.isdir(target) else target
            )
            os.makedirs(target_dir, exist_ok=True)

            shutil.move(source, target)
            return ToolResult(
                success=True,
                message=f"Moved {source} → {target}",
                files_affected=[source, target],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Move failed: {e}")


class CopyFileTool(Tool):
    name = "copy_file"
    description = "Copy a file or directory from source to target path."
    parameters_schema = {
        "source": "Source path",
        "target": "Target path",
    }

    async def execute(self, args: Dict) -> ToolResult:
        source = os.path.expanduser(args.get("source", ""))
        target = os.path.expanduser(args.get("target", ""))

        if not os.path.exists(source):
            return ToolResult(success=False, message=f"Source does not exist: {source}")

        try:
            target_dir = os.path.dirname(target)
            os.makedirs(target_dir, exist_ok=True)

            if os.path.isdir(source):
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                shutil.copy2(source, target)

            return ToolResult(
                success=True,
                message=f"Copied {source} → {target}",
                files_affected=[target],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Copy failed: {e}")


class RenameFileTool(Tool):
    name = "rename_file"
    description = "Rename a file or directory."
    parameters_schema = {
        "path": "Path to the file/directory to rename",
        "new_name": "New name (just the filename, not full path)",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        new_name = args.get("new_name", "")

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")
        if not new_name:
            return ToolResult(success=False, message="new_name is required")

        try:
            parent = os.path.dirname(path)
            new_path = os.path.join(parent, new_name)
            os.rename(path, new_path)
            return ToolResult(
                success=True,
                message=f"Renamed {os.path.basename(path)} → {new_name}",
                files_affected=[path, new_path],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Rename failed: {e}")


class DeleteFileTool(Tool):
    name = "delete_file"
    description = (
        "Delete a file or empty directory. DESTRUCTIVE - requires explicit approval."
    )
    parameters_schema = {
        "path": "Path to the file/directory to delete",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")

        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return ToolResult(
                success=True,
                message=f"Deleted {path}",
                files_affected=[path],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Delete failed: {e}")


class CreateDirectoryTool(Tool):
    name = "create_directory"
    description = "Create a new directory (and parent directories if needed)."
    parameters_schema = {
        "path": "Path of the directory to create",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))

        try:
            os.makedirs(path, exist_ok=True)
            return ToolResult(
                success=True,
                message=f"Created directory: {path}",
                files_affected=[path],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Create directory failed: {e}")


class OpenFileTool(Tool):
    name = "open_file"
    description = "Open a file or directory with the system's default application (e.g., xdg-open on Linux)."
    parameters_schema = {
        "path": "Absolute path to the file or directory to open",
    }

    async def execute(self, args: Dict) -> ToolResult:
        import subprocess

        path = os.path.expanduser(args.get("path", ""))

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")

        try:
            subprocess.Popen(
                ["xdg-open", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return ToolResult(
                success=True,
                message=f"Opened {path} with default application",
                files_affected=[path],
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                message="xdg-open not found. Cannot open files on this system.",
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Open failed: {e}")


class ReadFileContentTool(Tool):
    name = "read_file_content"
    description = "Read the text content of a file for preview. Returns the first N lines. Refuses binary files."
    parameters_schema = {
        "path": "Absolute path to the file to read",
        "max_lines": "(optional) Maximum number of lines to return. Default 200.",
        "max_size": "(optional) Maximum file size in bytes to attempt reading. Default 1MB.",
    }

    BINARY_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".webp",
        ".svg",
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".mp3",
        ".wav",
        ".flac",
        ".ogg",
        ".aac",
        ".wma",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".exe",
        ".bin",
        ".so",
        ".dll",
        ".o",
        ".a",
        ".dylib",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".pyc",
        ".class",
        ".wasm",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        max_lines = int(args.get("max_lines", 200))
        max_size = int(args.get("max_size", 1_048_576))  # 1MB

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")
        if os.path.isdir(path):
            return ToolResult(
                success=False, message=f"Cannot read directory as file: {path}"
            )

        ext = os.path.splitext(path)[1].lower()
        if ext in self.BINARY_EXTENSIONS:
            return ToolResult(
                success=False,
                message=f"Binary file ({ext}) — cannot preview as text",
                data={"binary": True, "extension": ext},
            )

        try:
            file_size = os.path.getsize(path)
            if file_size > max_size:
                return ToolResult(
                    success=False,
                    message=f"File too large for preview ({file_size} bytes, limit {max_size})",
                    data={"too_large": True, "size": file_size},
                )

            with open(path, "r", errors="replace") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    lines.append(line.rstrip("\n"))

            total_lines = len(lines)
            truncated = total_lines >= max_lines

            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "content": "\n".join(lines),
                    "lines": total_lines,
                    "truncated": truncated,
                    "size": file_size,
                    "extension": ext,
                },
                message=f"Read {total_lines} lines from {path}"
                + (" (truncated)" if truncated else ""),
            )
        except UnicodeDecodeError:
            return ToolResult(
                success=False,
                message="File appears to be binary — cannot preview as text",
                data={"binary": True},
            )
        except PermissionError:
            return ToolResult(success=False, message=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(success=False, message=f"Read failed: {e}")


# Register all file tools
ALL_FILE_TOOLS = [
    ListDirectoryTool(),
    ReadFileMetadataTool(),
    SearchFilesTool(),
    MoveFileTool(),
    CopyFileTool(),
    RenameFileTool(),
    DeleteFileTool(),
    CreateDirectoryTool(),
    OpenFileTool(),
    ReadFileContentTool(),
]
