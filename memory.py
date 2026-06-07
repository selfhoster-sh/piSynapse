import aiosqlite
import os
import asyncio
import logging

logger = logging.getLogger("piSynapse")

DB_PATH = os.getenv("DB_PATH", "assistant.db")
DEFAULT_USER = os.getenv("ASSISTANT_USER", "default")
SIMILARITY_THRESHOLD = float(os.getenv("MEMORY_SIMILARITY_THRESHOLD", "0.68"))


async def init_db():
    """Creates database tables and indexes if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
                summary     TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       TEXT NOT NULL DEFAULT 'default',
                content       TEXT NOT NULL,
                category      TEXT,
                importance    INTEGER DEFAULT 5,
                embedding     BLOB,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
                access_count  INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_session
            ON conversations(session_id, timestamp)
        """)
        await db.commit()


async def save_message(session_id: str, role: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content)
        )
        await db.execute(
            """INSERT INTO sessions (id) VALUES (?)
               ON CONFLICT(id) DO UPDATE SET last_active = CURRENT_TIMESTAMP""",
            (session_id,)
        )
        await db.commit()


async def get_history(session_id: str, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT role, content FROM conversations
               WHERE session_id = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (session_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


async def clear_history(session_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        await db.commit()


async def get_all_sessions() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id, created_at, last_active,
                      (SELECT COUNT(*) FROM conversations WHERE session_id = sessions.id) AS msg_count
               FROM sessions ORDER BY last_active DESC"""
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {"session_id": r[0], "created_at": r[1], "last_active": r[2], "message_count": r[3]}
                for r in rows
            ]


def _sync_find_similar(new_vec: bytes, rows: list, threshold: float) -> int | None:
    """CPU-bound cosine comparisons — runs off the event loop in a thread."""
    from embedding import cosine_similarity
    for mem_id, blob in rows:
        try:
            if cosine_similarity(new_vec, blob) >= threshold:
                return mem_id
        except Exception:
            continue
    return None


async def find_similar_memory(content: str, user_id: str, threshold: float | None = None) -> int | None:
    """Returns the ID of a semantically similar existing memory, or None."""
    from embedding import embed
    threshold = threshold if threshold is not None else SIMILARITY_THRESHOLD
    new_vec = await asyncio.to_thread(embed, content)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, embedding FROM memories WHERE user_id = ? AND embedding IS NOT NULL",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()

    return await asyncio.to_thread(_sync_find_similar, new_vec, rows, threshold)


async def save_memory(content: str, category: str = "general", importance: int = 5, user_id: str = None):
    """Saves a new memory, skipping it if a semantically similar one already exists."""
    from embedding import embed
    user_id = user_id or DEFAULT_USER
    content = content.strip()

    if len(content) < 5:
        return

    duplicate_id = await find_similar_memory(content, user_id)
    if duplicate_id:
        logger.info(f"💾 [Deduplication] Similar memory exists (ID: {duplicate_id}), updating access metrics.")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """UPDATE memories
                   SET last_accessed = CURRENT_TIMESTAMP,
                       access_count  = access_count + 1
                   WHERE id = ?""",
                (duplicate_id,)
            )
            await db.commit()
        return

    vec_blob = await asyncio.to_thread(embed, content)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO memories (user_id, content, category, importance, embedding)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, content, category, importance, vec_blob)
        )
        await db.commit()
    logger.info("🧠 New memory saved to semantic store.")


async def get_memories(user_id: str = None, limit: int = 10) -> list[dict]:
    user_id = user_id or DEFAULT_USER
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id, content, category, importance, created_at
               FROM memories WHERE user_id = ?
               ORDER BY importance DESC, last_accessed DESC LIMIT ?""",
            (user_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            memories = [
                {"id": r[0], "content": r[1], "category": r[2], "importance": r[3], "created_at": r[4]}
                for r in rows
            ]

        if memories:
            ids = [m["id"] for m in memories]
            placeholders = ",".join("?" for _ in ids)
            await db.execute(
                f"""UPDATE memories
                    SET last_accessed = CURRENT_TIMESTAMP,
                        access_count  = access_count + 1
                    WHERE id IN ({placeholders})""",
                ids
            )
            await db.commit()

    return memories


async def delete_memory(memory_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        await db.commit()


async def get_all_memories(user_id: str = None) -> list[dict]:
    user_id = user_id or DEFAULT_USER
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id, content, category, importance, created_at
               FROM memories WHERE user_id = ?
               ORDER BY importance DESC""",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {"id": r[0], "content": r[1], "category": r[2], "importance": r[3], "created_at": r[4]}
                for r in rows
            ]
