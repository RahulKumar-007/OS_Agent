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
import fnmatch
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


# ═══════════════════════════════════════════════════
# BATCH MOVE
# ═══════════════════════════════════════════════════

class BatchMoveTool(Tool):
    name = "batch_move"
    description = "Move multiple files matching a pattern or extension to a target directory."
    parameters_schema = {
        "source_dir": "Directory containing files to move",
        "target_dir": "Destination directory",
        "pattern": "(optional) Glob pattern to match files, e.g. '*.pdf' or 'photo_*'",
        "extensions": "(optional) Comma-separated extensions to move, e.g. '.jpg,.png'",
        "recursive": "(optional) Search recursively in source_dir. Default false.",
        "dry_run": "(optional) If true, just preview changes. Default false.",
        "create_target": "(optional) Create target directory if it doesn't exist. Default true.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        source_dir = os.path.expanduser(args.get("source_dir", ""))
        target_dir = os.path.expanduser(args.get("target_dir", ""))
        pattern = args.get("pattern", "")
        extensions_str = args.get("extensions", "")
        recursive = args.get("recursive", False)
        dry_run = args.get("dry_run", False)
        create_target = args.get("create_target", True)

        if not source_dir or not target_dir:
            return ToolResult(success=False, message="source_dir and target_dir are required")
        if not os.path.isdir(source_dir):
            return ToolResult(success=False, message=f"Source directory does not exist: {source_dir}")

        if create_target:
            try:
                os.makedirs(target_dir, exist_ok=True)
            except Exception as e:
                return ToolResult(success=False, message=f"Cannot create target directory: {e}")
        elif not os.path.isdir(target_dir):
            return ToolResult(success=False, message=f"Target directory does not exist: {target_dir}")

        # Collect files to move
        files_to_move = []
        extensions = set()
        if extensions_str:
            for ext in extensions_str.split(","):
                ext = ext.strip().lower()
                if not ext.startswith("."):
                    ext = "." + ext
                extensions.add(ext)

        try:
            if recursive:
                for root, dirs, fnames in os.walk(source_dir):
                    for fname in fnames:
                        full = os.path.join(root, fname)
                        ext = os.path.splitext(fname)[1].lower()
                        if extensions and ext not in extensions:
                            continue
                        if pattern and not fnmatch.fnmatch(fname, pattern):
                            continue
                        files_to_move.append(full)
            else:
                for fname in os.listdir(source_dir):
                    full = os.path.join(source_dir, fname)
                    if not os.path.isfile(full):
                        continue
                    ext = os.path.splitext(fname)[1].lower()
                    if extensions and ext not in extensions:
                        continue
                    if pattern and not fnmatch.fnmatch(fname, pattern):
                        continue
                    files_to_move.append(full)
        except PermissionError:
            return ToolResult(success=False, message=f"Permission denied: {source_dir}")

        if not files_to_move:
            return ToolResult(success=True, data={"moves": [], "count": 0}, message="No matching files found to move")

        moves = []
        for fp in files_to_move:
            name = os.path.basename(fp)
            dest = os.path.join(target_dir, name)
            moves.append({"from": fp, "to": dest, "name": name})

        if dry_run:
            return ToolResult(
                success=True,
                data={"moves": moves, "count": len(moves), "dry_run": True},
                message=f"Preview: {len(moves)} files would be moved to {target_dir}",
            )

        moved = 0
        errors = []
        for m in moves:
            try:
                if os.path.exists(m["to"]):
                    base, ext = os.path.splitext(m["to"])
                    counter = 1
                    while os.path.exists(f"{base}_{counter}{ext}"):
                        counter += 1
                    m["to"] = f"{base}_{counter}{ext}"
                shutil.move(m["from"], m["to"])
                moved += 1
            except Exception as e:
                errors.append({"file": m["name"], "error": str(e)})

        return ToolResult(
            success=True,
            data={"moves": moves, "count": moved, "errors": errors if errors else None},
            message=f"Moved {moved} files to {target_dir}" + (f" ({len(errors)} errors)" if errors else ""),
            files_affected=[m["to"] for m in moves[:moved]],
        )


# ═══════════════════════════════════════════════════
# DELETE DUPLICATES
# ═══════════════════════════════════════════════════

class DeleteDuplicatesTool(Tool):
    name = "delete_duplicates"
    description = "Find and delete duplicate files, keeping the first copy. DESTRUCTIVE - requires approval."
    parameters_schema = {
        "path": "Directory to scan for duplicates",
        "extension": "(optional) Only check files with this extension, e.g. '.pdf'",
        "dry_run": "(optional) Preview duplicates without deleting. Default true (safe default).",
        "keep_newest": "(optional) Keep the newest file instead of the first found. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        import hashlib
        from collections import defaultdict

        path = os.path.expanduser(args.get("path", ""))
        extension = args.get("extension", None)
        dry_run = args.get("dry_run", True)
        keep_newest = args.get("keep_newest", False)

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")
        if not os.path.isdir(path):
            return ToolResult(success=False, message=f"Not a directory: {path}")

        def hash_file(fp):
            sha256 = hashlib.sha256()
            with open(fp, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    sha256.update(chunk)
            return sha256.hexdigest()

        try:
            # Group by size first (fast filter)
            size_groups = defaultdict(list)
            for root, _, files in os.walk(path):
                for name in files:
                    if extension and not name.lower().endswith(extension.lower()):
                        continue
                    full_path = os.path.join(root, name)
                    try:
                        size = os.path.getsize(full_path)
                        size_groups[size].append(full_path)
                    except (PermissionError, OSError):
                        continue

            # Hash files with same size
            hash_groups = defaultdict(list)
            for size, file_paths in size_groups.items():
                if len(file_paths) < 2:
                    continue
                for fp in file_paths:
                    try:
                        h = hash_file(fp)
                        hash_groups[h].append(fp)
                    except (PermissionError, OSError):
                        continue

            # Build deletion list
            duplicates = []
            total_wasted = 0
            to_delete = []

            for h, file_paths in hash_groups.items():
                if len(file_paths) < 2:
                    continue

                if keep_newest:
                    file_paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                else:
                    file_paths.sort()

                keep = file_paths[0]
                copies = file_paths[1:]
                size = os.path.getsize(keep)
                wasted = size * len(copies)
                total_wasted += wasted

                duplicates.append({
                    "hash": h,
                    "kept": keep,
                    "copies": copies,
                    "count": len(copies),
                    "size": size,
                    "wasted_bytes": wasted,
                })
                to_delete.extend(copies)

            if dry_run:
                return ToolResult(
                    success=True,
                    data={
                        "duplicate_groups": duplicates,
                        "total_groups": len(duplicates),
                        "to_delete": to_delete,
                        "total_to_delete": len(to_delete),
                        "total_wasted_bytes": total_wasted,
                        "dry_run": True,
                    },
                    message=f"DRY RUN: Found {len(duplicates)} duplicate groups, {len(to_delete)} files would be deleted, {_format_size(total_wasted)} would be freed",
                )

            # Actually delete
            deleted = 0
            errors = []
            for fp in to_delete:
                try:
                    os.remove(fp)
                    deleted += 1
                except Exception as e:
                    errors.append({"path": fp, "error": str(e)})

            return ToolResult(
                success=True,
                data={
                    "duplicate_groups": duplicates,
                    "total_groups": len(duplicates),
                    "deleted": deleted,
                    "freed_bytes": total_wasted,
                    "freed_formatted": _format_size(total_wasted),
                    "errors": errors if errors else None,
                },
                message=f"Deleted {deleted} duplicate files, freed {_format_size(total_wasted)}",
                files_affected=to_delete,
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Duplicate deletion failed: {e}")


# ═══════════════════════════════════════════════════
# AI-POWERED ORGANIZATION
# ═══════════════════════════════════════════════════

class OrganizeByAITool(Tool):
    name = "organize_by_ai"
    description = (
        "Organize files using LLM-powered AI categorization. "
        "The LLM examines filenames and suggests smart category folders. "
        "Supports custom category prompts."
    )
    parameters_schema = {
        "path": "Directory to organize",
        "categories": "(optional) Comma-separated custom categories. Default: auto-detected.",
        "dry_run": "(optional) Preview changes without moving. Default false.",
        "prompt": "(optional) Custom instruction for the LLM on how to categorize. "
                  "E.g. 'group by project name' or 'sort into work/personal/templates'.",
    }

    llm_client = None

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        categories_str = args.get("categories", "")
        dry_run = args.get("dry_run", False)
        prompt = args.get("prompt", "")

        if not os.path.isdir(path):
            return ToolResult(success=False, message=f"Not a directory: {path}")

        # Gather file names (skip directories)
        try:
            files = []
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                if not os.path.isfile(full):
                    continue
                st = os.stat(full)
                files.append({
                    "name": name,
                    "path": full,
                    "ext": os.path.splitext(name)[1].lower(),
                    "size": st.st_size,
                    "size_formatted": _format_size(st.st_size),
                    "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                })
        except PermissionError:
            return ToolResult(success=False, message=f"Permission denied: {path}")

        if not files:
            return ToolResult(success=True, message="No files to organize in this directory")

        # Use LLM to categorize if no explicit categories
        if not categories_str and self.llm_client:
            categories = await self._generate_categories(files, prompt)
        elif categories_str:
            categories = [c.strip() for c in categories_str.split(",") if c.strip()]
        else:
            categories = await self._suggest_categories_fallback(files)

        if not categories:
            return ToolResult(
                success=False,
                message="Could not determine categories. Try specifying them manually.",
            )

        # Use LLM to classify each file if available
        if self.llm_client and not categories_str:
            organized = await self._classify_files(files, categories, prompt)
        else:
            organized = self._classify_by_extension_fallback(files, categories)

        if dry_run:
            cat_groups = {}
            for item in organized:
                cat = item["category"]
                cat_groups.setdefault(cat, []).append(item["name"])
            return ToolResult(
                success=True,
                data={
                    "categories": cat_groups,
                    "total_files": len(organized),
                    "dry_run": True,
                },
                message=f"Preview: {len(organized)} files into {len(cat_groups)} categories",
            )

        # Move files
        moved = 0
        errors = []
        for item in organized:
            try:
                dest_dir = os.path.join(path, item["category"])
                os.makedirs(dest_dir, exist_ok=True)
                dest = os.path.join(dest_dir, item["name"])
                if os.path.exists(dest):
                    base, ext = os.path.splitext(dest)
                    counter = 1
                    while os.path.exists(f"{base}_{counter}{ext}"):
                        counter += 1
                    dest = f"{base}_{counter}{ext}"
                shutil.move(item["path"], dest)
                moved += 1
            except Exception as e:
                errors.append({"file": item["name"], "error": str(e)})

        return ToolResult(
            success=True,
            data={
                "categories": {c: [i["name"] for i in organized if i["category"] == c] for c in categories},
                "moved": moved,
                "errors": errors if errors else None,
            },
            message=f"Organized {moved} files into {len(categories)} AI-generated categories" + (f" ({len(errors)} errors)" if errors else ""),
            files_affected=[path],
        )

    async def _generate_categories(self, files: list, prompt: str) -> list:
        """Use LLM to suggest category names based on filenames."""
        names = [f["name"] for f in files[:100]]
        names_str = "\n".join(names)

        instruction = ""
        if prompt:
            instruction = f"Additional instruction: {prompt}"

        system_msg = "You are a file categorization assistant. Respond only with a JSON array of category names."
        user_msg = f"""Suggest 3-8 category folder names to organize these files. Categories should be short (1-2 words).

Files:
{names_str}

{instruction}

Return a JSON array of strings, e.g. ["Documents", "Images", "Archives"]
"""
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]
        result = await self.llm_client.generate_json(messages, temperature=0.2)
        parsed = result.get("parsed", [])
        if isinstance(parsed, list) and len(parsed) >= 2:
            return parsed
        return await self._suggest_categories_fallback(files)

    async def _classify_files(self, files: list, categories: list, prompt: str) -> list:
        """Use LLM to classify each file into a category."""
        names_str = "\n".join(f["name"] for f in files[:150])
        cats_str = ", ".join(categories)

        instruction = ""
        if prompt:
            instruction = f"Additional instruction: {prompt}"

        system_msg = "You are a file classifier. Respond with a JSON object mapping each filename to a category."
        user_msg = f"""Classify each file into one of these categories: {cats_str}

{instruction}

Files:
{names_str}

Return a JSON object where keys are filenames and values are category names.
Example: {{"photo.jpg": "Images", "report.pdf": "Documents"}}
"""
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]
        result = await self.llm_client.generate_json(messages, temperature=0.1)
        parsed = result.get("parsed", {})

        organized = []
        if isinstance(parsed, dict):
            name_to_cat = {k: v for k, v in parsed.items()}
            for f in files:
                cat = name_to_cat.get(f["name"])
                if cat and cat in categories:
                    organized.append({**f, "category": cat})
                else:
                    organized.append({**f, "category": self._best_match_category(f["name"], categories)})

            # Add any files not in the LLM response
            classified_names = {f["name"] for f in organized}
            for f in files:
                if f["name"] not in classified_names:
                    organized.append({**f, "category": self._best_match_category(f["name"], categories)})
        else:
            organized = [{**f, "category": self._best_match_category(f["name"], categories)} for f in files]

        return organized

    def _best_match_category(self, filename: str, categories: list) -> str:
        """Fallback: assign category based on extension or keyword match."""
        name_lower = filename.lower()
        ext = os.path.splitext(name_lower)[1]

        ext_map = {
            ".jpg": "Images", ".jpeg": "Images", ".png": "Images", ".gif": "Images",
            ".pdf": "Documents", ".docx": "Documents", ".txt": "Documents",
            ".mp4": "Videos", ".mkv": "Videos",
            ".mp3": "Audio", ".wav": "Audio",
            ".zip": "Archives", ".tar": "Archives",
            ".py": "Code", ".js": "Code", ".ts": "Code",
        }

        if ext in ext_map:
            cat = ext_map[ext]
            if cat in categories:
                return cat

        for cat in categories:
            if cat.lower() in name_lower:
                return cat

        return categories[0] if categories else "Other"

    def _classify_by_extension_fallback(self, files: list, categories: list) -> list:
        """Fallback when no LLM: use extension mapping."""
        return [{**f, "category": self._best_match_category(f["name"], categories)} for f in files]

    async def _suggest_categories_fallback(self, files: list) -> list:
        """Fallback: generate categories from extensions."""
        ext_categories = {
            ".jpg": "Images", ".jpeg": "Images", ".png": "Images", ".gif": "Images",
            ".bmp": "Images", ".webp": "Images", ".svg": "Images",
            ".mp4": "Videos", ".mkv": "Videos", ".avi": "Videos", ".mov": "Videos",
            ".mp3": "Audio", ".wav": "Audio", ".flac": "Audio", ".ogg": "Audio",
            ".pdf": "Documents", ".docx": "Documents", ".txt": "Documents", ".md": "Documents",
            ".zip": "Archives", ".tar": "Archives", ".gz": "Archives",
            ".py": "Code", ".js": "Code", ".ts": "Code", ".html": "Code", ".css": "Code",
        }
        cats = set()
        for f in files:
            cat = ext_categories.get(f["ext"])
            if cat:
                cats.add(cat)
        if not cats:
            cats = {"Documents", "Other"}
        return sorted(cats)


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
    BatchMoveTool(),
    DeleteDuplicatesTool(),
    OrganizeByAITool(),
]
