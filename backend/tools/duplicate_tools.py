"""
Duplicate detection tools.
Hashes files and finds duplicates within directories.
"""
import hashlib
import os
from collections import defaultdict
from typing import Dict
from tools.base import Tool, ToolResult


def _hash_file(filepath: str, chunk_size: int = 8192) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


class HashFileTool(Tool):
    name = "hash_file"
    description = "Compute SHA-256 hash of a file for comparison or deduplication."
    parameters_schema = {
        "path": "Absolute path to the file to hash",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"File does not exist: {path}")
        if os.path.isdir(path):
            return ToolResult(success=False, message=f"Cannot hash a directory: {path}")

        try:
            file_hash = _hash_file(path)
            return ToolResult(
                success=True,
                data={"path": path, "hash": file_hash},
                message=f"SHA-256: {file_hash}",
            )
        except PermissionError:
            return ToolResult(success=False, message=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(success=False, message=f"Hash failed: {e}")


class FindDuplicatesTool(Tool):
    name = "find_duplicates"
    description = "Find duplicate files in a directory by comparing file hashes. Optionally filter by extension."
    parameters_schema = {
        "path": "Directory to scan for duplicates",
        "extension": "(optional) File extension filter, e.g. '.pdf'",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        extension = args.get("extension", None)

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")
        if not os.path.isdir(path):
            return ToolResult(success=False, message=f"Not a directory: {path}")

        try:
            # First pass: group by size (quick filter)
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

            # Second pass: hash files that share the same size
            hash_groups = defaultdict(list)
            for size, file_paths in size_groups.items():
                if len(file_paths) < 2:
                    continue
                for fp in file_paths:
                    try:
                        h = _hash_file(fp)
                        hash_groups[h].append(fp)
                    except (PermissionError, OSError):
                        continue

            # Collect duplicate groups
            duplicates = []
            total_wasted = 0
            for h, file_paths in hash_groups.items():
                if len(file_paths) < 2:
                    continue
                size = os.path.getsize(file_paths[0])
                wasted = size * (len(file_paths) - 1)
                total_wasted += wasted
                duplicates.append({
                    "hash": h,
                    "count": len(file_paths),
                    "size": size,
                    "wasted_bytes": wasted,
                    "files": file_paths,
                    "original": file_paths[0],  # Keep the first one
                    "copies": file_paths[1:],  # Mark rest as copies
                })

            return ToolResult(
                success=True,
                data={
                    "duplicate_groups": duplicates,
                    "total_groups": len(duplicates),
                    "total_wasted_bytes": total_wasted,
                },
                message=f"Found {len(duplicates)} duplicate groups, {total_wasted} bytes wasted",
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Duplicate scan failed: {e}")


# Register all duplicate tools
ALL_DUPLICATE_TOOLS = [
    HashFileTool(),
    FindDuplicatesTool(),
]
