"""
Knowledge Base — Personal wiki with Markdown notes, semantic linking, and search.

Features:
  - Create/read/update/delete markdown notes (notes are .md files on disk)
  - Tag-based organization
  - Backlinks: every note that references another is linked
  - Full-text and semantic search across all notes
  - Project memory (context per project)
  - Import arbitrary text/documents into the KB
"""

import asyncio
import json
import os
import re
import time
from datetime import datetime
from typing import Dict, List, Optional

import aiosqlite

KB_DIR  = os.path.join(os.path.expanduser("~"), ".jarvis", "knowledge_base")
DB_PATH = os.path.join(os.path.expanduser("~"), ".jarvis", "kb_index.db")


# ── DB ────────────────────────────────────────────────────────────────────────

async def init_kb_db():
    os.makedirs(KB_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS notes (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                slug        TEXT UNIQUE NOT NULL,
                tags        TEXT DEFAULT '[]',
                project     TEXT DEFAULT '',
                file_path   TEXT UNIQUE NOT NULL,
                word_count  INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                id UNINDEXED, title, content, tags, project,
                content='', contentless_delete=1
            );
        """)
        await db.commit()


async def _get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


# ── Note CRUD ─────────────────────────────────────────────────────────────────

def _slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug or "note"


def _unique_slug(slug: str) -> str:
    base = slug
    i = 1
    while os.path.exists(os.path.join(KB_DIR, f"{slug}.md")):
        slug = f"{base}-{i}"
        i += 1
    return slug


class KnowledgeBase:
    """Manages the personal knowledge base."""

    async def create_note(self, title: str, content: str, tags: List[str] = None,
                          project: str = "") -> dict:
        import uuid
        note_id = str(uuid.uuid4())
        now     = datetime.now().isoformat()
        tags    = tags or []
        slug    = _unique_slug(_slugify(title))

        # Create the project subdirectory if needed
        note_dir = os.path.join(KB_DIR, project) if project else KB_DIR
        os.makedirs(note_dir, exist_ok=True)

        file_path = os.path.join(note_dir, f"{slug}.md")

        # Write YAML front-matter + content
        frontmatter = (
            f"---\n"
            f"id: {note_id}\n"
            f"title: {title}\n"
            f"tags: {json.dumps(tags)}\n"
            f"project: {project}\n"
            f"created: {now}\n"
            f"updated: {now}\n"
            f"---\n\n"
        )
        full_content = frontmatter + content
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        word_count = len(content.split())

        db = await _get_db()
        try:
            await db.execute(
                """INSERT INTO notes (id, title, slug, tags, project, file_path, word_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (note_id, title, slug, json.dumps(tags), project, file_path, word_count, now, now),
            )
            await db.execute(
                "INSERT INTO notes_fts (id, title, content, tags, project) VALUES (?, ?, ?, ?, ?)",
                (note_id, title, content, " ".join(tags), project),
            )
            await db.commit()
        finally:
            await db.close()

        return {"id": note_id, "title": title, "slug": slug, "file_path": file_path,
                "tags": tags, "project": project, "created_at": now}

    async def get_note(self, note_id: str = None, slug: str = None) -> Optional[dict]:
        db = await _get_db()
        try:
            if note_id:
                cur = await db.execute("SELECT * FROM notes WHERE id=?", (note_id,))
            else:
                cur = await db.execute("SELECT * FROM notes WHERE slug=?", (slug,))
            row = await cur.fetchone()
            if not row:
                return None
            note = _deserialize_note(dict(row))
            # Read content from file
            if os.path.exists(note["file_path"]):
                with open(note["file_path"], encoding="utf-8") as f:
                    note["content"] = _strip_frontmatter(f.read())
            return note
        finally:
            await db.close()

    async def update_note(self, note_id: str, title: str = None, content: str = None,
                          tags: List[str] = None, project: str = None) -> Optional[dict]:
        note = await self.get_note(note_id=note_id)
        if not note:
            return None

        now = datetime.now().isoformat()
        new_title   = title   if title   is not None else note["title"]
        new_tags    = tags    if tags    is not None else note["tags"]
        new_project = project if project is not None else note["project"]
        new_content = content if content is not None else note.get("content", "")

        # Rewrite file
        frontmatter = (
            f"---\n"
            f"id: {note_id}\n"
            f"title: {new_title}\n"
            f"tags: {json.dumps(new_tags)}\n"
            f"project: {new_project}\n"
            f"created: {note['created_at']}\n"
            f"updated: {now}\n"
            f"---\n\n"
        )
        with open(note["file_path"], "w", encoding="utf-8") as f:
            f.write(frontmatter + new_content)

        word_count = len(new_content.split())

        db = await _get_db()
        try:
            await db.execute(
                """UPDATE notes SET title=?, tags=?, project=?, word_count=?, updated_at=? WHERE id=?""",
                (new_title, json.dumps(new_tags), new_project, word_count, now, note_id),
            )
            await db.execute("DELETE FROM notes_fts WHERE id=?", (note_id,))
            await db.execute(
                "INSERT INTO notes_fts (id, title, content, tags, project) VALUES (?, ?, ?, ?, ?)",
                (note_id, new_title, new_content, " ".join(new_tags), new_project),
            )
            await db.commit()
        finally:
            await db.close()

        return await self.get_note(note_id=note_id)

    async def delete_note(self, note_id: str) -> bool:
        note = await self.get_note(note_id=note_id)
        if not note:
            return False
        try:
            os.remove(note["file_path"])
        except FileNotFoundError:
            pass
        db = await _get_db()
        try:
            await db.execute("DELETE FROM notes WHERE id=?", (note_id,))
            await db.execute("DELETE FROM notes_fts WHERE id=?", (note_id,))
            await db.commit()
        finally:
            await db.close()
        return True

    async def list_notes(self, project: str = "", tag: str = "", limit: int = 100) -> list:
        db = await _get_db()
        try:
            if project:
                cur = await db.execute(
                    "SELECT * FROM notes WHERE project=? ORDER BY updated_at DESC LIMIT ?",
                    (project, limit),
                )
            elif tag:
                cur = await db.execute(
                    "SELECT * FROM notes WHERE tags LIKE ? ORDER BY updated_at DESC LIMIT ?",
                    (f'%"{tag}"%', limit),
                )
            else:
                cur = await db.execute(
                    "SELECT * FROM notes ORDER BY updated_at DESC LIMIT ?", (limit,)
                )
            return [_deserialize_note(dict(r)) for r in await cur.fetchall()]
        finally:
            await db.close()

    async def search_notes(self, query: str, limit: int = 20) -> list:
        db = await _get_db()
        try:
            cur = await db.execute(
                """SELECT n.*, snippet(notes_fts, 2, '<b>', '</b>', '...', 32) AS snippet
                   FROM notes_fts f
                   JOIN notes n ON n.id = f.id
                   WHERE notes_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (query, limit),
            )
            return [_deserialize_note(dict(r)) for r in await cur.fetchall()]
        finally:
            await db.close()

    async def get_backlinks(self, slug: str) -> list:
        """Find all notes that reference [[slug]] or the note's title."""
        db = await _get_db()
        try:
            cur = await db.execute(
                "SELECT * FROM notes_fts WHERE notes_fts MATCH ? ORDER BY rank LIMIT 20",
                (slug,),
            )
            rows = await cur.fetchall()
            return [{"id": r["id"], "title": r["title"]} for r in rows]
        finally:
            await db.close()

    async def list_projects(self) -> list:
        db = await _get_db()
        try:
            cur = await db.execute(
                "SELECT project, COUNT(*) as note_count FROM notes WHERE project != '' GROUP BY project"
            )
            return [{"project": r["project"], "note_count": r["note_count"]} for r in await cur.fetchall()]
        finally:
            await db.close()

    async def import_text(self, title: str, text: str, tags: List[str] = None,
                          project: str = "") -> dict:
        """Import arbitrary text as a note."""
        return await self.create_note(title, text, tags, project)


def _strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        end = content.find("\n---\n", 3)
        if end != -1:
            return content[end + 5:].lstrip("\n")
    return content


def _deserialize_note(row: dict) -> dict:
    if isinstance(row.get("tags"), str):
        try:
            row["tags"] = json.loads(row["tags"])
        except Exception:
            row["tags"] = []
    return row


# Global instance
kb = KnowledgeBase()
