"""
Extended file operations tools.
Handles: create_file, compress, extract, trash, restore, batch_rename, batch_move,
         organize_by_extension, organize_by_date
"""
import os
import shutil
import subprocess
import zipfile
import tarfile
import re
from datetime import datetime
from typing import Dict
from tools.base import Tool, ToolResult


def _format_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} B"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


# ═══════════════════════════════════════════════════
# FILE OPERATIONS
# ═══════════════════════════════════════════════════

class CreateFileTool(Tool):
    name = "create_file"
    description = "Create a new empty file or a file with given content."
    parameters_schema = {
        "path": "Absolute path for the new file",
        "content": "(optional) Text content to write. Default empty.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        content = args.get("content", "")

        if not path:
            return ToolResult(success=False, message="path is required")
        if os.path.exists(path):
            return ToolResult(success=False, message=f"File already exists: {path}")

        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return ToolResult(
                success=True,
                message=f"Created file: {path}",
                files_affected=[path],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Create file failed: {e}")


class CompressFilesTool(Tool):
    name = "compress_files"
    description = "Compress files or directories into a .zip or .tar.gz archive."
    parameters_schema = {
        "sources": "List of absolute paths to files/directories to compress",
        "output": "Output archive path (e.g., ~/archive.zip or ~/backup.tar.gz)",
        "format": "(optional) 'zip' or 'tar.gz'. Default auto-detected from output extension.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        sources = args.get("sources", [])
        output = os.path.expanduser(args.get("output", ""))
        fmt = args.get("format", "")

        if not sources:
            return ToolResult(success=False, message="sources list is required")
        if not output:
            return ToolResult(success=False, message="output path is required")

        # Auto-detect format
        if not fmt:
            if output.endswith(".tar.gz") or output.endswith(".tgz"):
                fmt = "tar.gz"
            elif output.endswith(".zip"):
                fmt = "zip"
            else:
                fmt = "zip"
                output += ".zip"

        # Expand and validate sources
        expanded = []
        for src in sources:
            src = os.path.expanduser(src)
            if not os.path.exists(src):
                return ToolResult(success=False, message=f"Source does not exist: {src}")
            expanded.append(src)

        try:
            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
            total_files = 0

            if fmt == "zip":
                with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
                    for src in expanded:
                        if os.path.isdir(src):
                            base = os.path.basename(src)
                            for root, dirs, files in os.walk(src):
                                for f in files:
                                    full = os.path.join(root, f)
                                    arcname = os.path.join(base, os.path.relpath(full, src))
                                    zf.write(full, arcname)
                                    total_files += 1
                        else:
                            zf.write(src, os.path.basename(src))
                            total_files += 1
            elif fmt == "tar.gz":
                with tarfile.open(output, "w:gz") as tf:
                    for src in expanded:
                        tf.add(src, arcname=os.path.basename(src))
                        if os.path.isdir(src):
                            for root, dirs, files in os.walk(src):
                                total_files += len(files)
                        else:
                            total_files += 1
            else:
                return ToolResult(success=False, message=f"Unsupported format: {fmt}")

            size = os.path.getsize(output)
            return ToolResult(
                success=True,
                data={"output": output, "format": fmt, "files_compressed": total_files, "size": size},
                message=f"Compressed {total_files} files → {output} ({_format_size(size)})",
                files_affected=[output],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Compression failed: {e}")


class ExtractArchiveTool(Tool):
    name = "extract_archive"
    description = "Extract a .zip, .tar, .tar.gz, .tar.bz2, or .tar.xz archive."
    parameters_schema = {
        "path": "Path to the archive file",
        "output_dir": "(optional) Directory to extract into. Default: same directory as archive.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        output_dir = os.path.expanduser(args.get("output_dir", ""))

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Archive does not exist: {path}")

        if not output_dir:
            # Create a folder with the archive name (sans extension)
            base = os.path.basename(path)
            name = base.split(".")[0]
            output_dir = os.path.join(os.path.dirname(path), name)

        try:
            os.makedirs(output_dir, exist_ok=True)
            total_files = 0

            if path.endswith(".zip"):
                with zipfile.ZipFile(path, "r") as zf:
                    zf.extractall(output_dir)
                    total_files = len(zf.namelist())
            elif any(path.endswith(ext) for ext in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
                with tarfile.open(path, "r:*") as tf:
                    tf.extractall(output_dir)
                    total_files = len(tf.getnames())
            else:
                return ToolResult(success=False, message=f"Unsupported archive format: {path}")

            return ToolResult(
                success=True,
                data={"output_dir": output_dir, "files_extracted": total_files},
                message=f"Extracted {total_files} items → {output_dir}",
                files_affected=[output_dir],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Extraction failed: {e}")


class TrashFileTool(Tool):
    name = "trash_file"
    description = "Move a file or directory to the system Trash (recoverable). Safer than delete."
    parameters_schema = {
        "path": "Absolute path to the file/directory to trash",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")

        try:
            # Use gio trash on Linux (standard freedesktop trash)
            result = subprocess.run(
                ["gio", "trash", path],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return ToolResult(
                    success=True,
                    message=f"Moved to Trash: {path}",
                    files_affected=[path],
                )
            else:
                return ToolResult(success=False, message=f"Trash failed: {result.stderr.strip()}")
        except FileNotFoundError:
            return ToolResult(success=False, message="gio not found. Cannot trash on this system.")
        except Exception as e:
            return ToolResult(success=False, message=f"Trash failed: {e}")


class RestoreFromTrashTool(Tool):
    name = "restore_from_trash"
    description = "List items in Trash, or restore a file from Trash by its original path."
    parameters_schema = {
        "action": "'list' to list trashed files, 'restore' to restore a file",
        "original_path": "(for restore) The original path of the file to restore",
    }

    async def execute(self, args: Dict) -> ToolResult:
        action = args.get("action", "list")

        trash_dir = os.path.expanduser("~/.local/share/Trash")
        files_dir = os.path.join(trash_dir, "files")
        info_dir = os.path.join(trash_dir, "info")

        if action == "list":
            if not os.path.exists(info_dir):
                return ToolResult(success=True, data=[], message="Trash is empty")

            items = []
            for info_file in os.listdir(info_dir):
                if not info_file.endswith(".trashinfo"):
                    continue
                try:
                    with open(os.path.join(info_dir, info_file), "r") as f:
                        lines = f.readlines()
                    original = ""
                    deletion_date = ""
                    for line in lines:
                        if line.startswith("Path="):
                            from urllib.parse import unquote
                            original = unquote(line.strip().split("=", 1)[1])
                        if line.startswith("DeletionDate="):
                            deletion_date = line.strip().split("=", 1)[1]

                    trash_name = info_file[:-len(".trashinfo")]
                    trash_path = os.path.join(files_dir, trash_name)
                    size = 0
                    if os.path.exists(trash_path):
                        if os.path.isdir(trash_path):
                            for root, dirs, fs in os.walk(trash_path):
                                for ff in fs:
                                    try:
                                        size += os.path.getsize(os.path.join(root, ff))
                                    except OSError:
                                        pass
                        else:
                            size = os.path.getsize(trash_path)

                    items.append({
                        "name": trash_name,
                        "original_path": original,
                        "deletion_date": deletion_date,
                        "size": size,
                        "size_formatted": _format_size(size),
                        "is_dir": os.path.isdir(trash_path) if os.path.exists(trash_path) else False,
                    })
                except Exception:
                    continue

            items.sort(key=lambda x: x.get("deletion_date", ""), reverse=True)
            return ToolResult(
                success=True,
                data=items,
                message=f"Found {len(items)} items in Trash",
            )

        elif action == "restore":
            original_path = os.path.expanduser(args.get("original_path", ""))
            if not original_path:
                return ToolResult(success=False, message="original_path is required for restore")

            if not os.path.exists(info_dir):
                return ToolResult(success=False, message="Trash is empty")

            for info_file in os.listdir(info_dir):
                if not info_file.endswith(".trashinfo"):
                    continue
                try:
                    with open(os.path.join(info_dir, info_file), "r") as f:
                        content = f.read()
                    from urllib.parse import unquote
                    for line in content.split("\n"):
                        if line.startswith("Path="):
                            path_in_trash = unquote(line.split("=", 1)[1])
                            if path_in_trash == original_path:
                                trash_name = info_file[:-len(".trashinfo")]
                                trash_path = os.path.join(files_dir, trash_name)
                                if os.path.exists(trash_path):
                                    os.makedirs(os.path.dirname(original_path), exist_ok=True)
                                    shutil.move(trash_path, original_path)
                                    os.remove(os.path.join(info_dir, info_file))
                                    return ToolResult(
                                        success=True,
                                        message=f"Restored: {original_path}",
                                        files_affected=[original_path],
                                    )
                except Exception:
                    continue

            return ToolResult(success=False, message=f"File not found in Trash: {original_path}")

        return ToolResult(success=False, message=f"Unknown action: {action}")


# ═══════════════════════════════════════════════════
# BATCH OPERATIONS
# ═══════════════════════════════════════════════════

class BatchRenameTool(Tool):
    name = "batch_rename"
    description = "Rename multiple files using a pattern. Supports: sequential numbering, find-replace, prefix/suffix."
    parameters_schema = {
        "path": "Directory containing files to rename",
        "mode": "'sequential', 'replace', 'prefix', or 'suffix'",
        "pattern": "For sequential: base name (e.g., 'photo_'). For replace: search string. For prefix/suffix: text to add.",
        "replacement": "(for replace mode) Replacement string",
        "start_num": "(for sequential) Starting number. Default 1.",
        "extensions": "(optional) Only rename files with these extensions, e.g., '.jpg,.png'",
        "dry_run": "(optional) If true, just preview changes. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        mode = args.get("mode", "sequential")
        pattern = args.get("pattern", "")
        replacement = args.get("replacement", "")
        start_num = int(args.get("start_num", 1))
        extensions_str = args.get("extensions", "")
        dry_run = args.get("dry_run", False)

        if not os.path.isdir(path):
            return ToolResult(success=False, message=f"Not a directory: {path}")
        if not pattern:
            return ToolResult(success=False, message="pattern is required")

        extensions = set()
        if extensions_str:
            for ext in extensions_str.split(","):
                ext = ext.strip().lower()
                if not ext.startswith("."):
                    ext = "." + ext
                extensions.add(ext)

        try:
            files = sorted(os.listdir(path))
            renames = []
            num = start_num

            for name in files:
                full = os.path.join(path, name)
                if os.path.isdir(full):
                    continue
                ext = os.path.splitext(name)[1].lower()
                if extensions and ext not in extensions:
                    continue

                if mode == "sequential":
                    new_name = f"{pattern}{num:04d}{ext}"
                    num += 1
                elif mode == "replace":
                    new_name = name.replace(pattern, replacement)
                elif mode == "prefix":
                    new_name = pattern + name
                elif mode == "suffix":
                    base, ext_part = os.path.splitext(name)
                    new_name = base + pattern + ext_part
                else:
                    return ToolResult(success=False, message=f"Unknown mode: {mode}")

                if new_name != name:
                    renames.append({"old": name, "new": new_name, "path": full})

            if dry_run:
                return ToolResult(
                    success=True,
                    data={"renames": renames, "count": len(renames), "dry_run": True},
                    message=f"Preview: {len(renames)} files would be renamed",
                )

            renamed = 0
            for r in renames:
                new_full = os.path.join(path, r["new"])
                os.rename(r["path"], new_full)
                renamed += 1

            return ToolResult(
                success=True,
                data={"renames": renames, "count": renamed},
                message=f"Renamed {renamed} files",
                files_affected=[path],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Batch rename failed: {e}")


class OrganizeByExtensionTool(Tool):
    name = "organize_by_extension"
    description = "Organize files in a directory into subfolders by file extension (e.g., PDFs/ Images/ Code/)."
    parameters_schema = {
        "path": "Directory to organize",
        "dry_run": "(optional) Preview changes without moving. Default false.",
    }

    CATEGORY_MAP = {
        "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".tiff"},
        "Videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"},
        "Audio": {".mp3", ".wav", ".flac", ".ogg", ".aac", ".wma", ".m4a"},
        "Documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".rtf"},
        "Archives": {".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".tgz"},
        "Code": {".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp", ".go", ".rs", ".rb", ".sh", ".php"},
        "Data": {".json", ".yaml", ".yml", ".xml", ".csv", ".sql", ".db", ".sqlite"},
        "Text": {".txt", ".md", ".log", ".ini", ".cfg", ".conf", ".toml"},
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        dry_run = args.get("dry_run", False)

        if not os.path.isdir(path):
            return ToolResult(success=False, message=f"Not a directory: {path}")

        try:
            ext_to_cat = {}
            for cat, exts in self.CATEGORY_MAP.items():
                for ext in exts:
                    ext_to_cat[ext] = cat

            moves = []
            for name in os.listdir(path):
                full = os.path.join(path, name)
                if os.path.isdir(full):
                    continue
                ext = os.path.splitext(name)[1].lower()
                category = ext_to_cat.get(ext, "Other")
                dest_dir = os.path.join(path, category)
                dest = os.path.join(dest_dir, name)
                moves.append({"name": name, "category": category, "from": full, "to": dest})

            if dry_run:
                categories = {}
                for m in moves:
                    categories.setdefault(m["category"], []).append(m["name"])
                return ToolResult(
                    success=True,
                    data={"moves": len(moves), "categories": categories, "dry_run": True},
                    message=f"Preview: {len(moves)} files into {len(categories)} categories",
                )

            moved = 0
            for m in moves:
                os.makedirs(os.path.dirname(m["to"]), exist_ok=True)
                shutil.move(m["from"], m["to"])
                moved += 1

            return ToolResult(
                success=True,
                data={"moved": moved},
                message=f"Organized {moved} files by extension",
                files_affected=[path],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Organize failed: {e}")


class OrganizeByDateTool(Tool):
    name = "organize_by_date"
    description = "Organize files into subfolders by modification date (YYYY/MM format)."
    parameters_schema = {
        "path": "Directory to organize",
        "format": "(optional) Date folder format: 'year' (2024/), 'month' (2024/01/), or 'day' (2024/01/15/). Default 'month'.",
        "dry_run": "(optional) Preview changes without moving. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        date_format = args.get("format", "month")
        dry_run = args.get("dry_run", False)

        if not os.path.isdir(path):
            return ToolResult(success=False, message=f"Not a directory: {path}")

        try:
            moves = []
            for name in os.listdir(path):
                full = os.path.join(path, name)
                if os.path.isdir(full):
                    continue
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(full))
                except OSError:
                    continue

                if date_format == "year":
                    subfolder = str(mtime.year)
                elif date_format == "day":
                    subfolder = os.path.join(str(mtime.year), f"{mtime.month:02d}", f"{mtime.day:02d}")
                else:
                    subfolder = os.path.join(str(mtime.year), f"{mtime.month:02d}")

                dest_dir = os.path.join(path, subfolder)
                dest = os.path.join(dest_dir, name)
                moves.append({"name": name, "subfolder": subfolder, "from": full, "to": dest})

            if dry_run:
                groups = {}
                for m in moves:
                    groups.setdefault(m["subfolder"], []).append(m["name"])
                return ToolResult(
                    success=True,
                    data={"moves": len(moves), "groups": groups, "dry_run": True},
                    message=f"Preview: {len(moves)} files into {len(groups)} date folders",
                )

            moved = 0
            for m in moves:
                os.makedirs(os.path.dirname(m["to"]), exist_ok=True)
                shutil.move(m["from"], m["to"])
                moved += 1

            return ToolResult(
                success=True,
                data={"moved": moved},
                message=f"Organized {moved} files by date",
                files_affected=[path],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Organize failed: {e}")


# Register all fileops tools
ALL_FILEOPS_TOOLS = [
    CreateFileTool(),
    CompressFilesTool(),
    ExtractArchiveTool(),
    TrashFileTool(),
    RestoreFromTrashTool(),
    BatchRenameTool(),
    OrganizeByExtensionTool(),
    OrganizeByDateTool(),
]
