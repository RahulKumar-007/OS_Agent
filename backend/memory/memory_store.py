"""
Memory store.
Persists user preferences and learned patterns to SQLite.
Allows the agent to remember things across sessions.
"""
import json
from typing import Any, Dict, Optional
from database.models import get_db


class MemoryStore:
    """Persistent memory for user preferences and learned patterns."""

    async def get(self, key: str) -> Optional[Any]:
        """Get a memory value by key."""
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT value_json FROM memories WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None
        finally:
            await db.close()

    async def set(self, key: str, value: Any):
        """Set a memory value."""
        db = await get_db()
        try:
            value_json = json.dumps(value)
            await db.execute(
                """INSERT INTO memories (key, value_json, updated_at) 
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(key) DO UPDATE SET value_json=?, updated_at=datetime('now')""",
                (key, value_json, value_json),
            )
            await db.commit()
        finally:
            await db.close()

    async def delete(self, key: str):
        """Delete a memory."""
        db = await get_db()
        try:
            await db.execute("DELETE FROM memories WHERE key = ?", (key,))
            await db.commit()
        finally:
            await db.close()

    async def get_all(self) -> Dict[str, Any]:
        """Get all memories."""
        db = await get_db()
        try:
            cursor = await db.execute("SELECT key, value_json FROM memories")
            rows = await cursor.fetchall()
            return {row[0]: json.loads(row[1]) for row in rows}
        finally:
            await db.close()

    async def get_context_for_prompt(self) -> str:
        """Get memories formatted for LLM prompt context."""
        memories = await self.get_all()
        if not memories:
            return "No user preferences stored yet."
        
        lines = ["User preferences and learned patterns:"]
        for key, value in memories.items():
            if isinstance(value, dict):
                lines.append(f"- {key}: {json.dumps(value)}")
            else:
                lines.append(f"- {key}: {value}")
        return "\n".join(lines)
