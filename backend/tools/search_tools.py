"""
Advanced search tools for the filesystem agent.
Handles: fuzzy filename search, search by extension/size/date/owner, hidden files, recursive search.
"""
import os
import stat
import pwd
import fnmatch
import re
from datetime import datetime, timedelta
from typing import Dict, Optional
from tools.base import Tool, ToolResult


def _format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    if size_bytes == 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} B"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _parse_size(size_str: str) -> Optional[int]:
    """Parse size string like '10MB', '500KB', '1GB' to bytes."""
    if not size_str:
        return None
    size_str = size_str.strip().upper()
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for unit, mult in units.items():
        if size_str.endswith(unit):
            try:
                return int(float(size_str[:-len(unit)].strip()) * mult)
            except ValueError:
                return None
    try:
        return int(size_str)
    except ValueError:
        return None


def _parse_date_offset(date_str: str) -> Optional[datetime]:
    """Parse relative date like 'today', 'yesterday', '7d', '2w', '1m'."""
    if not date_str:
        return None
    date_str = date_str.strip().lower()
    now = datetime.now()
    if date_str in ("today", "0d"):
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if date_str == "yesterday":
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if date_str.endswith("d"):
        try:
            return now - timedelta(days=int(date_str[:-1]))
        except ValueError:
            pass
    if date_str.endswith("w"):
        try:
            return now - timedelta(weeks=int(date_str[:-1]))
        except ValueError:
            pass
    if date_str.endswith("m"):
        try:
            return now - timedelta(days=int(date_str[:-1]) * 30)
        except ValueError:
            pass
    # Try ISO date
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        return None


def _fuzzy_match(query: str, text: str) -> bool:
    """Simple fuzzy matching: all query chars must appear in order in text."""
    query = query.lower()
    text = text.lower()
    qi = 0
    for char in text:
        if qi < len(query) and char == query[qi]:
            qi += 1
    return qi == len(query)


def _get_entry(full_path: str) -> dict:
    """Get basic file info for a path."""
    try:
        st = os.stat(full_path)
        name = os.path.basename(full_path)
        try:
            owner = pwd.getpwuid(st.st_uid).pw_name
        except KeyError:
            owner = str(st.st_uid)
        return {
            "name": name,
            "path": full_path,
            "is_dir": os.path.isdir(full_path),
            "is_hidden": name.startswith("."),
            "size": st.st_size,
            "size_formatted": _format_size(st.st_size),
            "extension": os.path.splitext(name)[1].lower(),
            "owner": owner,
            "created": datetime.fromtimestamp(st.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
            "permissions": stat.filemode(st.st_mode),
        }
    except (PermissionError, OSError):
        return None


class AdvancedSearchTool(Tool):
    name = "advanced_search"
    description = (
        "Search for files and directories with multiple filters: name (with fuzzy matching), "
        "extension, size range, date range, owner, hidden files. Supports recursive search."
    )
    parameters_schema = {
        "path": "Directory to search in (absolute path or ~)",
        "query": "(optional) Filename query string. Supports glob patterns like *.pdf",
        "fuzzy": "(optional) Enable fuzzy matching for query. Default false (exact/glob).",
        "extensions": "(optional) Comma-separated extensions to filter, e.g. '.pdf,.docx'",
        "min_size": "(optional) Minimum file size, e.g. '10KB', '5MB'",
        "max_size": "(optional) Maximum file size, e.g. '100MB', '1GB'",
        "modified_after": "(optional) Modified after date: ISO date or relative like '7d', '2w', 'today'",
        "modified_before": "(optional) Modified before date: ISO date or relative like '30d'",
        "owner": "(optional) Filter by file owner username",
        "include_hidden": "(optional) Include hidden files. Default false.",
        "include_dirs": "(optional) Include directories in results. Default false.",
        "recursive": "(optional) Search recursively. Default true.",
        "max_results": "(optional) Maximum number of results to return. Default 200.",
        "regex": "(optional) Use regex pattern matching for query. Overrides fuzzy.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", "~"))
        query = args.get("query", "")
        fuzzy = args.get("fuzzy", False)
        use_regex = args.get("regex", False)
        extensions_str = args.get("extensions", "")
        min_size = _parse_size(args.get("min_size", ""))
        max_size = _parse_size(args.get("max_size", ""))
        modified_after = _parse_date_offset(args.get("modified_after", ""))
        modified_before = _parse_date_offset(args.get("modified_before", ""))
        owner_filter = args.get("owner", "")
        include_hidden = args.get("include_hidden", False)
        include_dirs = args.get("include_dirs", False)
        recursive = args.get("recursive", True)
        max_results = int(args.get("max_results", 200))

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")
        if not os.path.isdir(path):
            return ToolResult(success=False, message=f"Not a directory: {path}")

        # Parse extensions
        extensions = set()
        if extensions_str:
            for ext in extensions_str.split(","):
                ext = ext.strip().lower()
                if not ext.startswith("."):
                    ext = "." + ext
                extensions.add(ext)

        # Compile regex if needed
        regex_pattern = None
        if use_regex and query:
            try:
                regex_pattern = re.compile(query, re.IGNORECASE)
            except re.error as e:
                return ToolResult(success=False, message=f"Invalid regex: {e}")

        results = []
        scanned = 0

        def matches(entry: dict) -> bool:
            name = entry["name"]
            # Hidden filter
            if not include_hidden and entry.get("is_hidden"):
                return False
            # Dir filter
            if entry.get("is_dir") and not include_dirs:
                return False
            # Name/query matching
            if query:
                if use_regex and regex_pattern:
                    if not regex_pattern.search(name):
                        return False
                elif fuzzy:
                    if not _fuzzy_match(query, name):
                        return False
                else:
                    # Glob or substring
                    if "*" in query or "?" in query or "[" in query:
                        if not fnmatch.fnmatch(name.lower(), query.lower()):
                            return False
                    else:
                        if query.lower() not in name.lower():
                            return False
            # Extension filter
            if extensions and entry.get("extension") not in extensions:
                return False
            # Size filters
            if not entry.get("is_dir"):
                size = entry.get("size", 0)
                if min_size is not None and size < min_size:
                    return False
                if max_size is not None and size > max_size:
                    return False
            # Date filters
            modified_str = entry.get("modified", "")
            if modified_str:
                mod_dt = datetime.fromisoformat(modified_str)
                if modified_after and mod_dt < modified_after:
                    return False
                if modified_before and mod_dt > modified_before:
                    return False
            # Owner filter
            if owner_filter and entry.get("owner", "").lower() != owner_filter.lower():
                return False
            return True

        try:
            if recursive:
                for root, dirs, files in os.walk(path):
                    # Filter hidden dirs unless include_hidden
                    if not include_hidden:
                        dirs[:] = [d for d in dirs if not d.startswith(".")]

                    items = files[:]
                    if include_dirs:
                        items += dirs

                    for name in items:
                        if len(results) >= max_results:
                            break
                        scanned += 1
                        full_path = os.path.join(root, name)
                        entry = _get_entry(full_path)
                        if entry and matches(entry):
                            results.append(entry)

                    if len(results) >= max_results:
                        break
            else:
                for name in os.listdir(path):
                    if len(results) >= max_results:
                        break
                    scanned += 1
                    full_path = os.path.join(path, name)
                    entry = _get_entry(full_path)
                    if entry and matches(entry):
                        results.append(entry)

            # Sort by relevance: exact matches first, then by modified date
            if query and not use_regex:
                results.sort(
                    key=lambda e: (
                        0 if e["name"].lower() == query.lower() else
                        1 if e["name"].lower().startswith(query.lower()) else 2,
                        e.get("modified", ""),
                    ),
                    reverse=False,
                )
            else:
                results.sort(key=lambda e: e.get("modified", ""), reverse=True)

            filters_applied = []
            if query:
                filters_applied.append(f"name={'fuzzy:' if fuzzy else ''}{query}")
            if extensions:
                filters_applied.append(f"ext={','.join(extensions)}")
            if min_size is not None:
                filters_applied.append(f"size>={args.get('min_size')}")
            if max_size is not None:
                filters_applied.append(f"size<={args.get('max_size')}")
            if modified_after:
                filters_applied.append(f"after={args.get('modified_after')}")
            if modified_before:
                filters_applied.append(f"before={args.get('modified_before')}")
            if owner_filter:
                filters_applied.append(f"owner={owner_filter}")

            return ToolResult(
                success=True,
                data={
                    "results": results,
                    "total": len(results),
                    "scanned": scanned,
                    "truncated": len(results) >= max_results,
                    "filters_applied": filters_applied,
                    "search_path": path,
                },
                message=f"Found {len(results)} files (scanned {scanned})",
            )
        except PermissionError:
            return ToolResult(success=False, message=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(success=False, message=str(e))


class SearchByContentTool(Tool):
    name = "search_by_content"
    description = (
        "Search for text content inside files using grep. "
        "Finds files containing a specific string or pattern."
    )
    parameters_schema = {
        "path": "Directory to search in",
        "content_query": "Text or pattern to search for inside files",
        "extensions": "(optional) Comma-separated extensions to search within, e.g. '.py,.txt,.md'",
        "case_sensitive": "(optional) Case-sensitive search. Default false.",
        "regex": "(optional) Treat content_query as regex. Default false.",
        "max_results": "(optional) Maximum files to return. Default 50.",
        "recursive": "(optional) Search recursively. Default true.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        import subprocess

        path = os.path.expanduser(args.get("path", "~"))
        query = args.get("content_query", "")
        extensions_str = args.get("extensions", "")
        case_sensitive = args.get("case_sensitive", False)
        use_regex = args.get("regex", False)
        max_results = int(args.get("max_results", 50))
        recursive = args.get("recursive", True)

        if not query:
            return ToolResult(success=False, message="content_query is required")
        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")

        try:
            cmd = ["grep", "-l"]  # -l = list filenames only
            if not case_sensitive:
                cmd.append("-i")
            if use_regex:
                cmd.append("-E")
            else:
                cmd.append("-F")  # Fixed string (faster)
            if recursive:
                cmd.append("-r")

            # Extension filters
            if extensions_str:
                exts = [e.strip().lstrip(".") for e in extensions_str.split(",")]
                include_patterns = [f"--include=*.{ext}" for ext in exts]
                cmd.extend(include_patterns)

            cmd.extend(["--", query, path])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            file_paths = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
            file_paths = file_paths[:max_results]

            results = []
            for fp in file_paths:
                try:
                    st = os.stat(fp)
                    results.append({
                        "name": os.path.basename(fp),
                        "path": fp,
                        "size": st.st_size,
                        "size_formatted": _format_size(st.st_size),
                        "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                        "extension": os.path.splitext(fp)[1].lower(),
                    })
                except OSError:
                    continue

            return ToolResult(
                success=True,
                data={
                    "results": results,
                    "total": len(results),
                    "query": query,
                    "truncated": len(file_paths) >= max_results,
                },
                message=f"Found {len(results)} files containing '{query}'",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, message="Search timed out (>30s)")
        except FileNotFoundError:
            return ToolResult(success=False, message="grep not found on this system")
        except Exception as e:
            return ToolResult(success=False, message=str(e))


# Register all search tools
ALL_SEARCH_TOOLS = [
    AdvancedSearchTool(),
    SearchByContentTool(),
]
