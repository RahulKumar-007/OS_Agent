"""
Filesystem Index Tools.
Instant search backed by a persistent SQLite FTS5 index — the agent's
"intelligence database" of every file on the machine, kept warm in the
background so lookups feel immediate rather than searched-for.
"""

import asyncio
from typing import Dict

from tools.base import Tool, ToolResult


class IndexedSearchTool(Tool):
    name = "indexed_search"
    description = (
        "Instantly search the pre-built filename index — far faster than a live "
        "filesystem walk. Best for quick filename/path lookups across the entire "
        "allowed filesystem."
    )
    parameters_schema = {
        "query": "Search terms to match against file/directory names",
        "limit": "(optional) Max results. Default 50.",
    }

    def __init__(self):
        self.store = None  # injected at startup by main.py

    async def execute(self, args: Dict) -> ToolResult:
        if not self.store:
            return ToolResult(success=False, message="Index not initialized")
        query = args.get("query", "").strip()
        limit = int(args.get("limit", 50))
        if not query:
            return ToolResult(success=False, message="Query required")
        try:
            results = await self.store.search(query, limit=limit)
            return ToolResult(
                success=True,
                data={"results": results, "count": len(results)},
                message=f"{len(results)} indexed match(es) for '{query}'",
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Index search failed: {e}")


class RebuildIndexTool(Tool):
    name = "rebuild_index"
    description = "Trigger a full rebuild of the filesystem search index in the background"
    parameters_schema = {}

    def __init__(self):
        self.indexer = None  # injected at startup by main.py

    async def execute(self, args: Dict) -> ToolResult:
        if not self.indexer:
            return ToolResult(success=False, message="Indexer not initialized")
        if self.indexer.is_building:
            return ToolResult(
                success=True,
                data=self.indexer.status(),
                message="Index rebuild already in progress",
            )
        roots = self.indexer.default_roots
        asyncio.create_task(self.indexer.build_index(roots))
        return ToolResult(
            success=True, data=self.indexer.status(), message="Index rebuild started"
        )


class IndexStatusTool(Tool):
    name = "index_status"
    description = "Get the status of the filesystem search index (build progress, file count, last update, live-watch state)"
    parameters_schema = {}

    def __init__(self):
        self.indexer = None  # injected
        self.store = None  # injected

    async def execute(self, args: Dict) -> ToolResult:
        if not self.indexer or not self.store:
            return ToolResult(success=False, message="Indexer not initialized")
        status = self.indexer.status()
        try:
            status["total_indexed"] = await self.store.count()
        except Exception:
            status["total_indexed"] = 0
        return ToolResult(success=True, data=status, message="Index status retrieved")


ALL_INDEX_TOOLS = [IndexedSearchTool(), RebuildIndexTool(), IndexStatusTool()]
