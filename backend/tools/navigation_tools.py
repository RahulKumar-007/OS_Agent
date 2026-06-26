"""
Navigation tools for the filesystem agent.
Handles: browse_directory, get_directory_info, list_drives, get_common_folders
"""
import os
import stat
import pwd
import grp
from datetime import datetime
from typing import Dict
from tools.base import Tool, ToolResult


def _get_entry_info(full_path: str, name: str) -> dict:
    """Get detailed info for a single file/directory entry."""
    try:
        st = os.stat(full_path)
        lstat = os.lstat(full_path)  # for symlink detection
        is_symlink = stat.S_ISLNK(lstat.st_mode)
        is_dir = os.path.isdir(full_path)

        # Owner info
        try:
            owner = pwd.getpwuid(st.st_uid).pw_name
        except KeyError:
            owner = str(st.st_uid)

        # Group info
        try:
            group = grp.getgrgid(st.st_gid).gr_name
        except KeyError:
            group = str(st.st_gid)

        return {
            "name": name,
            "path": full_path,
            "is_dir": is_dir,
            "is_symlink": is_symlink,
            "is_hidden": name.startswith("."),
            "size": st.st_size,
            "size_formatted": _format_size(st.st_size),
            "permissions": stat.filemode(st.st_mode),
            "owner": owner,
            "group": group,
            "created": datetime.fromtimestamp(st.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
            "accessed": datetime.fromtimestamp(st.st_atime).isoformat(),
            "extension": "" if is_dir else os.path.splitext(name)[1].lower(),
            "symlink_target": os.readlink(full_path) if is_symlink else None,
        }
    except (PermissionError, OSError) as e:
        return {
            "name": name,
            "path": full_path,
            "is_dir": False,
            "is_hidden": name.startswith("."),
            "size": 0,
            "error": str(e),
        }


def _format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    if size_bytes == 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} B"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


class BrowseDirectoryTool(Tool):
    name = "browse_directory"
    description = (
        "Browse a directory with full file details. Returns entries sorted by type then name. "
        "Supports showing hidden files and filtering."
    )
    parameters_schema = {
        "path": "Absolute path to browse (use ~ for home)",
        "show_hidden": "(optional) Include hidden files (dot-files). Default false.",
        "sort_by": "(optional) Sort field: 'name', 'size', 'modified', 'type'. Default 'type'.",
        "sort_desc": "(optional) Sort descending. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", "~"))
        show_hidden = args.get("show_hidden", False)
        sort_by = args.get("sort_by", "type")
        sort_desc = args.get("sort_desc", False)

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")
        if not os.path.isdir(path):
            return ToolResult(success=False, message=f"Not a directory: {path}")

        try:
            entries = []
            for name in os.listdir(path):
                if not show_hidden and name.startswith("."):
                    continue
                full_path = os.path.join(path, name)
                entries.append(_get_entry_info(full_path, name))

            # Sort
            sort_key_map = {
                "name": lambda e: e.get("name", "").lower(),
                "size": lambda e: e.get("size", 0),
                "modified": lambda e: e.get("modified", ""),
                "type": lambda e: (0 if e.get("is_dir") else 1, e.get("name", "").lower()),
            }
            key_fn = sort_key_map.get(sort_by, sort_key_map["type"])
            entries.sort(key=key_fn, reverse=sort_desc)

            # Parent dir info
            parent = str(os.path.dirname(path)) if path != "/" else None

            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "parent": parent,
                    "entries": entries,
                    "total": len(entries),
                    "dirs": sum(1 for e in entries if e.get("is_dir")),
                    "files": sum(1 for e in entries if not e.get("is_dir")),
                },
                message=f"Browsing {path}: {len(entries)} items",
            )
        except PermissionError:
            return ToolResult(success=False, message=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(success=False, message=str(e))


class GetDirectoryInfoTool(Tool):
    name = "get_directory_info"
    description = "Get summary info about a directory: total size, file count, largest files, most recent files."
    parameters_schema = {
        "path": "Absolute path to the directory",
        "max_depth": "(optional) Max recursion depth. Default 3.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", "~"))
        max_depth = int(args.get("max_depth", 3))

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")

        try:
            total_size = 0
            file_count = 0
            dir_count = 0
            all_files = []

            def walk(current_path, depth):
                nonlocal total_size, file_count, dir_count
                if depth > max_depth:
                    return
                try:
                    for name in os.listdir(current_path):
                        full = os.path.join(current_path, name)
                        try:
                            st = os.stat(full)
                            if os.path.isdir(full):
                                dir_count += 1
                                walk(full, depth + 1)
                            else:
                                file_count += 1
                                total_size += st.st_size
                                all_files.append({
                                    "name": name,
                                    "path": full,
                                    "size": st.st_size,
                                    "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                                })
                        except (PermissionError, OSError):
                            continue
                except (PermissionError, OSError):
                    pass

            walk(path, 0)

            largest = sorted(all_files, key=lambda f: f["size"], reverse=True)[:10]
            recent = sorted(all_files, key=lambda f: f["modified"], reverse=True)[:10]

            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "total_size": total_size,
                    "total_size_formatted": _format_size(total_size),
                    "file_count": file_count,
                    "dir_count": dir_count,
                    "largest_files": largest,
                    "most_recent_files": recent,
                },
                message=f"Directory info for {path}: {file_count} files, {_format_size(total_size)}",
            )
        except Exception as e:
            return ToolResult(success=False, message=str(e))


class GetCommonFoldersTool(Tool):
    name = "get_common_folders"
    description = "Get paths to common user folders: Home, Desktop, Downloads, Documents, Pictures, Videos, Music."
    parameters_schema = {}

    async def execute(self, args: Dict) -> ToolResult:
        home = os.path.expanduser("~")
        folders = {
            "Home": home,
            "Desktop": os.path.join(home, "Desktop"),
            "Downloads": os.path.join(home, "Downloads"),
            "Documents": os.path.join(home, "Documents"),
            "Pictures": os.path.join(home, "Pictures"),
            "Videos": os.path.join(home, "Videos"),
            "Music": os.path.join(home, "Music"),
            "Root": "/",
        }

        result = {}
        for name, path in folders.items():
            exists = os.path.exists(path)
            result[name] = {
                "path": path,
                "exists": exists,
                "size": 0,
            }
            if exists:
                try:
                    st = os.stat(path)
                    result[name]["modified"] = datetime.fromtimestamp(st.st_mtime).isoformat()
                except OSError:
                    pass

        return ToolResult(
            success=True,
            data=result,
            message="Common folders retrieved",
        )


# Register all navigation tools
ALL_NAVIGATION_TOOLS = [
    BrowseDirectoryTool(),
    GetDirectoryInfoTool(),
    GetCommonFoldersTool(),
]
