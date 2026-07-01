"""
Advanced search tools for the filesystem agent.
Handles: fuzzy filename search, search by extension/size/date/owner, hidden files, recursive search,
document content search (PDF, Office, images via OCR, code files), semantic/natural language search.
"""
import os
import stat
import pwd
import fnmatch
import re
import json
from datetime import datetime, timedelta
from typing import Dict, Optional
from tools.base import Tool, ToolResult
from tools.extraction_tools import extract_text_from_file, SUPPORTED_EXTENSIONS, BINARY_DOCUMENT_EXTENSIONS, IMAGE_EXTENSIONS


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
        "created_after": "(optional) Created after date: ISO date or relative like '7d', '2w', 'today'",
        "created_before": "(optional) Created before date: ISO date or relative like '30d'",
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
        created_after = _parse_date_offset(args.get("created_after", ""))
        created_before = _parse_date_offset(args.get("created_before", ""))
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
            # Date filters — modified
            modified_str = entry.get("modified", "")
            if modified_str:
                mod_dt = datetime.fromisoformat(modified_str)
                if modified_after and mod_dt < modified_after:
                    return False
                if modified_before and mod_dt > modified_before:
                    return False
            # Date filters — created
            created_str = entry.get("created", "")
            if created_str:
                cre_dt = datetime.fromisoformat(created_str)
                if created_after and cre_dt < created_after:
                    return False
                if created_before and cre_dt > created_before:
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
            if created_after:
                filters_applied.append(f"created_after={args.get('created_after')}")
            if created_before:
                filters_applied.append(f"created_before={args.get('created_before')}")
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


# ═══════════════════════════════════════════════════
# DOCUMENT CONTENT SEARCH
# ═══════════════════════════════════════════════════

class SearchDocumentsTool(Tool):
    name = "search_documents"
    description = (
        "Search for text content inside documents: PDFs, Office files (DOCX, XLSX, PPTX), "
        "images (via OCR), source code, and text files. "
        "Extracts text from each file and searches for the query."
    )
    parameters_schema = {
        "path": "Directory to search in",
        "query": "Text to search for inside document content",
        "extensions": "(optional) Comma-separated extensions to restrict search, e.g. '.pdf,.docx,.py'",
        "case_sensitive": "(optional) Case-sensitive search. Default false.",
        "max_files": "(optional) Maximum files to process. Default 50.",
        "max_results": "(optional) Maximum matching files to return. Default 30.",
        "recursive": "(optional) Search recursively. Default true.",
        "context_chars": "(optional) Characters of context around match. Default 100.",
        "max_pages": "(optional) Max pages per PDF. Default 20.",
        "ocr_language": "(optional) Tesseract OCR language. Default 'eng'.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", "~"))
        query = args.get("query", "")
        extensions_str = args.get("extensions", "")
        case_sensitive = args.get("case_sensitive", False)
        max_files = int(args.get("max_files", 50))
        max_results = int(args.get("max_results", 30))
        recursive = args.get("recursive", True)
        context_chars = int(args.get("context_chars", 100))
        max_pages = int(args.get("max_pages", 20))
        ocr_language = args.get("ocr_language", "eng")

        if not query:
            return ToolResult(success=False, message="query is required")
        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")
        if not os.path.isdir(path):
            return ToolResult(success=False, message=f"Not a directory: {path}")

        # Determine target extensions
        ALL_DOC_EXTS = SUPPORTED_EXTENSIONS | BINARY_DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS
        if extensions_str:
            target_exts = set()
            for ext in extensions_str.split(","):
                ext = ext.strip().lower()
                if not ext.startswith("."):
                    ext = "." + ext
                target_exts.add(ext)
        else:
            target_exts = ALL_DOC_EXTS

        # Walk and collect files
        files_to_search = []
        try:
            if recursive:
                for root, dirs, fnames in os.walk(path):
                    for fname in fnames:
                        if len(files_to_search) >= max_files:
                            break
                        ext = os.path.splitext(fname)[1].lower()
                        if ext in target_exts:
                            files_to_search.append(os.path.join(root, fname))
                    if len(files_to_search) >= max_files:
                        break
            else:
                for fname in os.listdir(path):
                    if len(files_to_search) >= max_files:
                        break
                    full = os.path.join(path, fname)
                    if os.path.isfile(full):
                        ext = os.path.splitext(fname)[1].lower()
                        if ext in target_exts:
                            files_to_search.append(full)
        except PermissionError:
            return ToolResult(success=False, message=f"Permission denied: {path}")

        if not files_to_search:
            return ToolResult(success=True, data={"results": [], "total": 0, "search_path": path}, message="No supported documents found")

        # Search each file
        results = []
        errors = []
        query_lower = query.lower() if not case_sensitive else query

        for fp in files_to_search:
            if len(results) >= max_results:
                break
            try:
                extraction = extract_text_from_file(fp, max_pages, ocr_language)
                text = extraction.get("text", "")
                if not text:
                    continue

                # Search in extracted text
                if case_sensitive:
                    matches = list(_find_all_matches(text, query, context_chars))
                else:
                    matches = list(_find_all_matches(text, query_lower, context_chars))

                if matches:
                    st = os.stat(fp)
                    results.append({
                        "path": fp,
                        "name": os.path.basename(fp),
                        "extension": os.path.splitext(fp)[1].lower(),
                        "size": st.st_size,
                        "size_formatted": _format_size(st.st_size),
                        "method": extraction.get("method", "unknown"),
                        "match_count": len(matches),
                        "matches": matches[:5],  # Show first 5 context snippets
                        "text_length": len(text),
                    })
            except Exception as e:
                errors.append({"path": fp, "error": str(e)})

        # Sort by match count (relevance)
        results.sort(key=lambda r: r["match_count"], reverse=True)

        return ToolResult(
            success=True,
            data={
                "results": results,
                "total": len(results),
                "scanned": len(files_to_search),
                "errors": errors[:10] if errors else [],
                "search_path": path,
                "query": query,
            },
            message=f"Found {len(results)} documents matching '{query}' (scanned {len(files_to_search)} files)",
        )


def _find_all_matches(text: str, query: str, context_chars: int = 100):
    """Yield dicts with context around each match of query in text."""
    idx = 0
    text_lower = text.lower() if query.islower() else text
    search_in = text_lower if query.islower() else text
    q = query.lower() if query.islower() else query

    while True:
        pos = search_in.find(q, idx)
        if pos == -1:
            break
        start = max(0, pos - context_chars)
        end = min(len(text), pos + len(query) + context_chars)
        before = text[start:pos].strip()
        matched = text[pos:pos + len(query)]
        after = text[pos + len(query):end].strip()
        # Truncate with ellipsis
        if start > 0:
            before = "..." + before[-context_chars//2:]
        if end < len(text):
            after = after[:context_chars//2] + "..."
        yield {
            "before": before,
            "match": matched,
            "after": after,
            "position": pos,
        }
        idx = pos + len(query)


# ═══════════════════════════════════════════════════
# SEMANTIC / NATURAL LANGUAGE SEARCH
# ═══════════════════════════════════════════════════

class SemanticSearchTool(Tool):
    name = "semantic_search"
    description = (
        "Search files using natural language. Understands the meaning and intent behind queries, "
        "not just keywords. Also searches inside document content (PDF, Office, images via OCR). "
        "For example: 'find invoices from last quarter' or 'show me all my resume drafts'."
    )
    parameters_schema = {
        "path": "Directory to search in",
        "query": "Natural language search query describing what you're looking for",
        "extensions": "(optional) Comma-separated extensions to restrict search",
        "max_files": "(optional) Maximum files to process. Default 50.",
        "max_results": "(optional) Maximum results to return. Default 30.",
        "recursive": "(optional) Search recursively. Default true.",
    }

    # Set by main.py after LLM client is initialized
    llm_client = None

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", "~"))
        query = args.get("query", "")
        extensions_str = args.get("extensions", "")
        max_files = int(args.get("max_files", 50))
        max_results = int(args.get("max_results", 30))
        recursive = args.get("recursive", True)

        if not query:
            return ToolResult(success=False, message="query is required")
        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")

        # Phase 1: Use LLM to understand the query and generate search strategy
        terms = await self._expand_query(query)
        if not terms:
            return ToolResult(success=False, message="Failed to analyze query")

        # Phase 2: Search using the expanded terms
        results = await self._search_with_terms(
            path, terms, extensions_str, max_files, max_results, recursive
        )

        # Phase 3: Score and rank results using LLM
        scored = await self._rank_results(query, results, max_results)

        return ToolResult(
            success=True,
            data={
                "results": scored,
                "total": len(scored),
                "query": query,
                "expanded_terms": terms,
                "search_path": path,
            },
            message=f"Found {len(scored)} semantically relevant results for '{query}'",
        )

    async def _expand_query(self, query: str) -> list:
        """Use LLM to expand a natural language query into search keywords and patterns."""
        if not self.llm_client:
            # Fallback: use query as-is and extract keywords
            keywords = [w for w in re.sub(r'[^\w\s]', ' ', query).split() if len(w) > 2]
            return [query] + keywords[:5]

        prompt = f"""You are a search query analyzer for a filesystem agent. 
Given a natural language query, generate effective search terms.

Rules:
- Generate 3-8 search terms/keywords
- Include file extensions if mentioned
- Include alternative phrasings
- Think about what the user is ACTUALLY looking for

Respond with a JSON array of strings, nothing else.
Example input: "find my tax documents from last year"
Example output: ["tax", "tax document", "tax return", "taxes", "*.pdf", "2024 tax"]

User query: {query}
"""
        messages = [
            {"role": "system", "content": "You are a search query analyzer. Respond only with a JSON array of search terms."},
            {"role": "user", "content": prompt},
        ]

        result = await self.llm_client.generate_json(messages, temperature=0.1)
        parsed = result.get("parsed")
        if isinstance(parsed, list) and len(parsed) > 0:
            return parsed

        # Fallback: extract keywords
        keywords = [w for w in re.sub(r'[^\w\s]', ' ', query).split() if len(w) > 2]
        return [query] + keywords[:5]

    async def _search_with_terms(
        self, path: str, terms: list, extensions_str: str,
        max_files: int, max_results: int, recursive: bool
    ) -> list:
        """Search using expanded terms across filename and document content."""
        ALL_DOC_EXTS = SUPPORTED_EXTENSIONS | BINARY_DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS
        if extensions_str:
            target_exts = set()
            for ext in extensions_str.split(","):
                ext = ext.strip().lower()
                if not ext.startswith("."):
                    ext = "." + ext
                target_exts.add(ext)
        else:
            target_exts = ALL_DOC_EXTS

        # Collect files
        files_to_search = []
        try:
            if recursive:
                for root, dirs, fnames in os.walk(path):
                    for fname in fnames:
                        if len(files_to_search) >= max_files:
                            break
                        ext = os.path.splitext(fname)[1].lower()
                        if ext in target_exts:
                            files_to_search.append(os.path.join(root, fname))
                    if len(files_to_search) >= max_files:
                        break
            else:
                for fname in os.listdir(path):
                    if len(files_to_search) >= max_files:
                        break
                    full = os.path.join(path, fname)
                    if os.path.isfile(full):
                        ext = os.path.splitext(fname)[1].lower()
                        if ext in target_exts:
                            files_to_search.append(full)
        except PermissionError:
            return []

        # Build term patterns for matching (both filename and content)
        term_patterns = []
        for term in terms:
            term_lower = term.lower()
            is_glob = "*" in term or "?" in term
            term_patterns.append({"original": term, "lower": term_lower, "is_glob": is_glob})

        scored_results = []

        for fp in files_to_search:
            if len(scored_results) >= max_results * 2:
                break

            name = os.path.basename(fp)
            name_lower = name.lower()
            st = os.stat(fp)
            entry = {
                "path": fp,
                "name": name,
                "extension": os.path.splitext(fp)[1].lower(),
                "size": st.st_size,
                "size_formatted": _format_size(st.st_size),
                "score": 0,
                "match_type": "",
            }

            # Score by filename matches (weighted higher)
            for tp in term_patterns:
                if tp["is_glob"]:
                    if fnmatch.fnmatch(name_lower, tp["lower"]):
                        entry["score"] += 10
                        entry["match_type"] = "filename_glob"
                elif tp["lower"] in name_lower:
                    entry["score"] += 8
                    entry["match_type"] = "filename"
                # Partial word match
                if any(tp["lower"] in word for word in name_lower.split(".")):
                    entry["score"] += 3

            if entry["score"] > 0:
                scored_results.append(entry)
                continue

            # Content search for documents (lower weight)
            ext = os.path.splitext(fp)[1].lower()
            if ext in BINARY_DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS or ext in SUPPORTED_EXTENSIONS:
                try:
                    extraction = extract_text_from_file(fp, max_pages=5)
                    text = extraction.get("text", "")[:5000]
                    text_lower = text.lower()
                    content_score = 0
                    for tp in term_patterns:
                        if tp["is_glob"]:
                            continue
                        count = text_lower.count(tp["lower"])
                        if count > 0:
                            content_score += min(count, 5) * 2
                    if content_score > 0:
                        entry["score"] = content_score
                        entry["match_type"] = "content"
                        scored_results.append(entry)
                except Exception:
                    pass

        scored_results.sort(key=lambda r: r["score"], reverse=True)
        return scored_results[:max_results]

    async def _rank_results(self, query: str, results: list, max_results: int) -> list:
        """Use LLM to rank/filter results by relevance to the natural language query."""
        if not self.llm_client or not results:
            return results

        # Only rank if we have a reasonable number of results
        if len(results) > 15:
            # Ask LLM to select the most relevant ones
            names = [r["name"] for r in results]
            prompt = f"""Given this natural language query: "{query}"

Which of these files are most relevant? Return a JSON array of the MOST relevant filenames (up to {max_results}).

Files: {json.dumps(names)}

CRITICAL: Return ONLY a JSON array of strings (the most relevant filenames from the list above)."""
            messages = [
                {"role": "system", "content": "You are a relevance ranker. Return only a JSON array of the most relevant filenames."},
                {"role": "user", "content": prompt},
            ]
            result = await self.llm_client.generate_json(messages, temperature=0.1)
            parsed = result.get("parsed")
            if isinstance(parsed, list) and len(parsed) > 0:
                # Re-rank based on LLM selection
                name_order = {name: i for i, name in enumerate(parsed)}
                results.sort(key=lambda r: name_order.get(r["name"], 999))

        return results[:max_results]


# ═══════════════════════════════════════════════════
# CODE REPOSITORY SEARCH
# ═══════════════════════════════════════════════════

class SearchCodeTool(Tool):
    name = "search_code"
    description = (
        "Search inside code repositories. Searches code files (.py, .js, .ts, .go, .rs, .java, .c, .cpp, etc.) "
        "by function/class names, comments, strings, and code patterns. "
        "Also searches git history if available."
    )
    parameters_schema = {
        "path": "Directory to search in (repository root)",
        "query": "Search query - function name, variable, pattern, or natural language",
        "language": "(optional) Language filter: 'python', 'javascript', 'typescript', 'rust', 'go', etc.",
        "search_in": "(optional) What to search: 'code', 'comments', 'strings', 'all'. Default 'all'.",
        "max_results": "(optional) Maximum results to return. Default 30.",
        "recursive": "(optional) Search recursively. Default true.",
        "include_tests": "(optional) Include test files. Default true.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", "~"))
        query = args.get("query", "")
        language = args.get("language", "")
        search_in = args.get("search_in", "all")
        max_results = int(args.get("max_results", 30))
        recursive = args.get("recursive", True)
        include_tests = args.get("include_tests", True)

        if not query:
            return ToolResult(success=False, message="query is required")
        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")

        # Language-to-extension mapping
        LANG_EXTS = {
            "python": {".py", ".pyi", ".pyx", ".pxd"},
            "javascript": {".js", ".jsx", ".mjs", ".cjs"},
            "typescript": {".ts", ".tsx"},
            "rust": {".rs", ".rlib"},
            "go": {".go"},
            "java": {".java"},
            "cpp": {".cpp", ".cxx", ".cc", ".hpp", ".hxx"},
            "c": {".c", ".h"},
            "ruby": {".rb", ".rbw"},
            "php": {".php", ".phtml"},
            "swift": {".swift"},
            "kotlin": {".kt", ".kts"},
            "scala": {".scala"},
            "shell": {".sh", ".bash", ".zsh"},
            "sql": {".sql"},
            "rust": {".rs"},
        }

        if language:
            target_exts = LANG_EXTS.get(language.lower(), set())
            if not target_exts:
                # Treat language as extension
                lang = language.lower().lstrip(".")
                target_exts = {f".{lang}"}
        else:
            # All code extensions
            target_exts = set()
            for exts in LANG_EXTS.values():
                target_exts.update(exts)
            target_exts.update(SUPPORTED_EXTENSIONS)

        # Test file patterns to optionally skip
        test_patterns = ["test_", "_test", ".test.", "spec_", "_spec", "__tests__", "tests/"]

        # Collect files
        files_to_search = []
        try:
            if recursive:
                for root, dirs, fnames in os.walk(path):
                    # Skip node_modules, .git, __pycache__, etc.
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
                        "node_modules", "vendor", "bower_components", ".git", "__pycache__",
                        "target", "build", "dist", ".tox", ".eggs", "eggs",
                    )]
                    for fname in fnames:
                        if len(files_to_search) >= 200:
                            break
                        ext = os.path.splitext(fname)[1].lower()
                        if ext not in target_exts:
                            continue
                        if not include_tests and any(p in fname.lower() or p in root.lower() for p in test_patterns):
                            continue
                        files_to_search.append(os.path.join(root, fname))
                    if len(files_to_search) >= 200:
                        break
            else:
                for fname in os.listdir(path):
                    if len(files_to_search) >= 200:
                        break
                    full = os.path.join(path, fname)
                    if os.path.isfile(full):
                        ext = os.path.splitext(fname)[1].lower()
                        if ext in target_exts:
                            files_to_search.append(full)
        except PermissionError:
            return ToolResult(success=False, message=f"Permission denied: {path}")

        if not files_to_search:
            return ToolResult(
                success=True,
                data={"results": [], "total": 0, "query": query, "search_path": path},
                message="No matching code files found",
            )

        # Search in code files
        results = []
        query_lower = query.lower()

        for fp in files_to_search:
            if len(results) >= max_results:
                break
            try:
                with open(fp, "r", errors="replace") as f:
                    lines = f.readlines()

                file_matches = []
                for i, line in enumerate(lines, 1):
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue

                    # Determine if we should search this line based on search_in
                    if search_in == "comments":
                        # Only check comment lines
                        comment_chars = {"#", "//", "/*", "*", "--", "%", ";"}
                        if not line_stripped.startswith(tuple(comment_chars)):
                            continue
                    elif search_in == "strings":
                        # Only check string literals (crude approximation)
                        if not ('"' in line_stripped or "'" in line_stripped or '"""' in line_stripped):
                            continue

                    if query_lower in line_stripped.lower():
                        # Extract context
                        context_before = ""
                        context_after = ""
                        if i > 1:
                            context_before = lines[i - 2].strip() if i >= 2 else ""
                        if i < len(lines):
                            context_after = lines[i].strip() if i < len(lines) else ""

                        file_matches.append({
                            "line": i,
                            "content": line_stripped[:200],
                            "context_before": context_before[:150] if context_before else "",
                            "context_after": context_after[:150] if context_after else "",
                        })

                if file_matches:
                    st = os.stat(fp)
                    results.append({
                        "path": fp,
                        "name": os.path.basename(fp),
                        "extension": os.path.splitext(fp)[1].lower(),
                        "size": st.st_size,
                        "size_formatted": _format_size(st.st_size),
                        "match_count": len(file_matches),
                        "matches": file_matches[:10],
                    })
            except (PermissionError, OSError, UnicodeDecodeError):
                continue

        # Sort by match count
        results.sort(key=lambda r: r["match_count"], reverse=True)

        return ToolResult(
            success=True,
            data={
                "results": results,
                "total": len(results),
                "scanned": len(files_to_search),
                "query": query,
                "search_path": path,
                "language_filter": language or "all",
            },
            message=f"Found {len(results)} code files matching '{query}' (scanned {len(files_to_search)} files)",
        )


# Register all search tools
ALL_SEARCH_TOOLS = [
    AdvancedSearchTool(),
    SearchByContentTool(),
    SearchDocumentsTool(),
    SearchCodeTool(),
    SemanticSearchTool(),
]
