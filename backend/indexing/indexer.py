"""
Background filesystem indexer.

Walks allowed paths to build a searchable file index, then (optionally)
keeps it live-updated in real time via `watchdog` filesystem events —
giving the agent a permanently warm, instantly queryable map of the disk.

The full walk is synchronous, blocking I/O (os.walk + os.stat across
potentially hundreds of thousands of files), so it runs in a worker thread
via a dedicated sqlite3 connection. WAL journaling + a busy timeout let it
coexist safely with the async connection used for reads and live watchdog
updates without ever blocking the event loop.
"""

import asyncio
import os
import sqlite3
import time
from typing import List, Optional

from indexing.index_store import IndexStore

SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".cache",
    ".npm",
    ".cargo",
    "site-packages",
    ".Trash",
    "$RECYCLE.BIN",
}

BATCH_SIZE = 500


class IndexerService:
    """Owns the lifecycle of the on-disk search index: build, watch, report status."""

    def __init__(self, store: IndexStore, policy_engine=None):
        self.store = store
        self.policy_engine = policy_engine
        self.default_roots: List[str] = []

        self.is_building = False
        self.files_indexed = 0
        self.last_build_started: Optional[float] = None
        self.last_build_finished: Optional[float] = None
        self.last_error: Optional[str] = None
        self._observer = None
        self._cancel_requested = False

    def status(self) -> dict:
        return {
            "is_building": self.is_building,
            "files_indexed": self.files_indexed,
            "last_build_started": self.last_build_started,
            "last_build_finished": self.last_build_finished,
            "last_error": self.last_error,
            "watching": self._observer is not None,
            "roots": self.default_roots,
        }

    def _dir_allowed(self, path: str) -> bool:
        if not self.policy_engine:
            return True
        try:
            return self.policy_engine.validate(path).get("allowed", True)
        except Exception:
            return True

    async def build_index(self, roots: List[str]):
        """Full rebuild of the index across the given root directories.

        The heavy walk runs in a thread pool so it never blocks the event
        loop (and therefore never blocks other API requests, including
        index searches while the build is in progress).
        """
        if self.is_building:
            return
        self.is_building = True
        self.files_indexed = 0
        self.last_build_started = time.time()
        self.last_error = None

        # Make sure the schema exists via the async path too (harmless no-op
        # if already created by the sync worker).
        await self.store.init()

        loop = asyncio.get_event_loop()
        try:
            count = await loop.run_in_executor(
                None, self._sync_build, list(roots), self.store.db_path
            )
            self.files_indexed = count
        except Exception as e:
            self.last_error = str(e)
        finally:
            self.is_building = False
            self.last_build_finished = time.time()

    def _sync_build(self, roots: List[str], db_path: str) -> int:
        """Runs in a worker thread — pure blocking I/O, no asyncio here."""
        conn = sqlite3.connect(db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute(
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
        conn.execute(
            "CREATE TABLE IF NOT EXISTS index_meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        conn.execute("DELETE FROM file_index")
        conn.commit()

        batch = []
        count = 0

        try:
            for root in roots:
                root = os.path.expanduser(root)
                if not os.path.isdir(root):
                    continue

                for dirpath, dirnames, filenames in os.walk(
                    root, topdown=True, onerror=lambda e: None
                ):
                    dirnames[:] = [
                        d
                        for d in dirnames
                        if d not in SKIP_DIRS
                        and not d.startswith(".")
                        and self._dir_allowed(os.path.join(dirpath, d))
                    ]

                    for fname in filenames:
                        full_path = os.path.join(dirpath, fname)
                        try:
                            st = os.stat(full_path)
                        except OSError:
                            continue

                        ext = os.path.splitext(fname)[1].lstrip(".").lower()
                        batch.append(
                            (full_path, fname, dirpath, ext, st.st_size, st.st_mtime)
                        )
                        count += 1
                        self.files_indexed = count

                        if len(batch) >= BATCH_SIZE:
                            conn.executemany(
                                "INSERT INTO file_index (path, name, dir, ext, size, mtime) VALUES (?, ?, ?, ?, ?, ?)",
                                batch,
                            )
                            conn.commit()
                            batch = []

            if batch:
                conn.executemany(
                    "INSERT INTO file_index (path, name, dir, ext, size, mtime) VALUES (?, ?, ?, ?, ?, ?)",
                    batch,
                )
                conn.commit()

            conn.execute(
                """INSERT INTO index_meta (key, value) VALUES ('last_build_finished', ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (str(time.time()),),
            )
            conn.commit()
        finally:
            conn.close()

        return count

    def start_watching(self, roots: List[str], loop: asyncio.AbstractEventLoop) -> bool:
        """Start real-time filesystem watching (optional, requires 'watchdog')."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            return False

        store = self.store

        async def index_single(path: str):
            try:
                st = os.stat(path)
            except OSError:
                return
            fname = os.path.basename(path)
            ext = os.path.splitext(fname)[1].lstrip(".").lower()
            await store.remove_path(path)
            await store.upsert_many(
                [
                    {
                        "path": path,
                        "name": fname,
                        "dir": os.path.dirname(path),
                        "ext": ext,
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                    }
                ]
            )

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    asyncio.run_coroutine_threadsafe(index_single(event.src_path), loop)

            def on_modified(self, event):
                if not event.is_directory:
                    asyncio.run_coroutine_threadsafe(index_single(event.src_path), loop)

            def on_deleted(self, event):
                if not event.is_directory:
                    asyncio.run_coroutine_threadsafe(store.remove_path(event.src_path), loop)

            def on_moved(self, event):
                if not event.is_directory:
                    asyncio.run_coroutine_threadsafe(store.remove_path(event.src_path), loop)
                    asyncio.run_coroutine_threadsafe(index_single(event.dest_path), loop)

        handler = Handler()
        observer = Observer()
        scheduled = False
        for root in roots:
            root = os.path.expanduser(root)
            if os.path.isdir(root):
                try:
                    observer.schedule(handler, root, recursive=True)
                    scheduled = True
                except OSError:
                    continue

        if not scheduled:
            return False

        observer.start()
        self._observer = observer
        return True

    def stop_watching(self):
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
