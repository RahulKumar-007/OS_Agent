"""
Performance Layer — Metadata cache, parallel scanning, and resource controls.

Features:
  - TTL-based in-memory metadata cache
  - LRU eviction
  - Background parallel directory scanner
  - Cache statistics
"""

import asyncio
import hashlib
import os
import time
from collections import OrderedDict
from typing import Any, Dict, Optional


class TTLCache:
    """Thread-safe in-memory TTL + LRU cache."""

    def __init__(self, maxsize: int = 2000, ttl: float = 300.0):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl
        self._hits = 0
        self._misses = 0
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            value, expires = self._cache[key]
            if time.monotonic() > expires:
                del self._cache[key]
                self._misses += 1
                return None
            # Move to end (LRU)
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    async def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        async with self._lock:
            expires = time.monotonic() + (ttl or self._ttl)
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, expires)
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def stats(self) -> Dict:
        async with self._lock:
            total = self._hits + self._misses
            return {
                "size":      len(self._cache),
                "maxsize":   self._maxsize,
                "ttl":       self._ttl,
                "hits":      self._hits,
                "misses":    self._misses,
                "hit_rate":  round(self._hits / total, 3) if total else 0.0,
            }

    def make_key(self, *parts: str) -> str:
        raw = ":".join(str(p) for p in parts)
        return hashlib.md5(raw.encode()).hexdigest()


class ParallelScanner:
    """Parallel async directory scanner with concurrency control."""

    def __init__(self, max_workers: int = 8):
        self._semaphore = asyncio.Semaphore(max_workers)

    async def scan(self, root: str, depth: int = 3, include_hidden: bool = False) -> list:
        """Recursively scan a directory in parallel. Returns list of file dicts."""
        results = []
        await self._scan_dir(root, depth, include_hidden, results)
        return results

    async def _scan_dir(self, path: str, depth: int, include_hidden: bool, results: list):
        if depth < 0:
            return
        async with self._semaphore:
            try:
                entries = await asyncio.to_thread(os.scandir, path)
            except (PermissionError, OSError):
                return

        tasks = []
        for entry in entries:
            if not include_hidden and entry.name.startswith("."):
                continue
            try:
                stat = entry.stat(follow_symlinks=False)
                results.append({
                    "path":       entry.path,
                    "name":       entry.name,
                    "is_dir":     entry.is_dir(follow_symlinks=False),
                    "size":       stat.st_size if not entry.is_dir() else 0,
                    "modified":   stat.st_mtime,
                    "depth":      depth,
                })
                if entry.is_dir(follow_symlinks=False) and depth > 0:
                    tasks.append(self._scan_dir(entry.path, depth - 1, include_hidden, results))
            except (PermissionError, OSError):
                continue

        if tasks:
            await asyncio.gather(*tasks)


# Global singletons
metadata_cache = TTLCache(maxsize=5000, ttl=120.0)
search_cache   = TTLCache(maxsize=500,  ttl=60.0)
parallel_scanner = ParallelScanner(max_workers=8)
