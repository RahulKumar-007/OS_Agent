"""
Persistent full-text file index using SQLite FTS5.

Enables instant filename/path search across the entire filesystem without
walking directories on every query — the "intelligence database" the agent
scans against.

Uses a single long-lived connection guarded by an asyncio.Lock (rather than
opening a fresh connection per call) plus WAL journaling, so the background
full-index build and live watchdog updates never collide with "database is
locked" errors.
"""

import asyncio
import os
from typing import List, Optional

import aiosqlite

INDEX_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "index.db"
)


class IndexStore:
    """FTS5-backed store of filename/path metadata for instant search."""

    def __init__(self, db_path: str = INDEX_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.row_factory = aiosqlite.Row
        return self._conn

    async def init(self):
        async with self._lock:
            db = await self._get_conn()
            await db.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS file_index USING fts5(
                    path UNINDEXED,
                    name,
                    dir,
                    ext UNINDEXED,
                    size UNINDEXED,
                    mtime UNINDEXED
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS index_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
            await db.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def clear(self):
        async with self._lock:
            db = await self._get_conn()
            await db.execute("DELETE FROM file_index")
            await db.commit()

    async def upsert_many(self, entries: List[dict]):
        if not entries:
            return
        async with self._lock:
            db = await self._get_conn()
            await db.executemany(
                "INSERT INTO file_index (path, name, dir, ext, size, mtime) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (e["path"], e["name"], e["dir"], e["ext"], e["size"], e["mtime"])
                    for e in entries
                ],
            )
            await db.commit()

    async def remove_path(self, path: str):
        async with self._lock:
            db = await self._get_conn()
            await db.execute("DELETE FROM file_index WHERE path = ?", (path,))
            await db.commit()

    async def search(self, query: str, limit: int = 50) -> List[dict]:
        """Prefix-match every token in the query against indexed names/dirs."""
        terms = [t.strip().replace('"', "") for t in query.split() if t.strip()]
        if not terms:
            return []
        match_expr = " ".join(f'"{t}"*' for t in terms)

        async with self._lock:
            db = await self._get_conn()
            try:
                cursor = await db.execute(
                    """SELECT path, name, dir, ext, size, mtime FROM file_index
                       WHERE file_index MATCH ? ORDER BY rank LIMIT ?""",
                    (match_expr, limit),
                )
                rows = await cursor.fetchall()
            except aiosqlite.OperationalError:
                return []
            return [dict(r) for r in rows]

    async def set_meta(self, key: str, value: str):
        async with self._lock:
            db = await self._get_conn()
            await db.execute(
                """INSERT INTO index_meta (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (key, value),
            )
            await db.commit()

    async def get_meta(self, key: str) -> Optional[str]:
        async with self._lock:
            db = await self._get_conn()
            cursor = await db.execute(
                "SELECT value FROM index_meta WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def count(self) -> int:
        async with self._lock:
            db = await self._get_conn()
            cursor = await db.execute("SELECT COUNT(*) FROM file_index")
            row = await cursor.fetchone()
            return row[0] if row else 0
