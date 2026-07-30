"""piSynapse Database Layer
SQLite with aiosqlite: conversations, sessions, and long-term memory.
Single persistent connection with WAL mode for Pi-friendly I/O.
"""

import asyncio
import logging

import aiosqlite

from config import DB_PATH

logger = logging.getLogger("piSynapse")

_db: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is not None:
        try:
            await _db.execute("SELECT 1")
            return _db
        except Exception:
            logger.warning("SQLite connection lost, reconnecting...")
            _db = None

    async with _db_lock:
        if _db is not None:
            return _db
        conn = await aiosqlite.connect(DB_PATH)
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA cache_size=10000")
        await conn.execute("PRAGMA temp_store=MEMORY")
        await conn.execute("PRAGMA foreign_keys=ON")
        _db = conn
        return _db


async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None


# -- Schema --

async def init_db():
    db = await get_db()

    await db.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            images     TEXT,
            timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migration: add images column if missing (for existing databases)
    try:
        await db.execute("SELECT images FROM conversations LIMIT 1")
    except Exception:
        await db.execute("ALTER TABLE conversations ADD COLUMN images TEXT")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
            name        TEXT,
            summary     TEXT,
            summarized_until INTEGER DEFAULT 0
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      TEXT NOT NULL DEFAULT 'default',
            content      TEXT NOT NULL,
            category     TEXT,
            importance   INTEGER DEFAULT 5,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
            access_count INTEGER DEFAULT 0,
            embedding    BLOB
        )
    """)

    await db.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id, timestamp)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id, importance DESC)")

    # Migrations from older DB versions (safe: table/column/definition are hardcoded)
    for table, column, definition in [
        ("sessions", "name", "TEXT"),
        ("sessions", "summarized_until", "INTEGER DEFAULT 0"),
        ("memories", "embedding", "BLOB"),
    ]:
        try:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")  # noqa: E501
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                logger.warning(f"Migration {table}.{column} failed: {e}")

    await db.commit()


# -- Conversations --

async def save_message(session_id: str, role: str, content: str, images: list[str] | None = None):
    import json
    images_json = json.dumps(images) if images else None
    db = await get_db()
    await db.execute(
        "INSERT INTO conversations (session_id, role, content, images) VALUES (?, ?, ?, ?)",
        (session_id, role, content, images_json),
    )
    await db.execute(
        """INSERT INTO sessions (id) VALUES (?)
           ON CONFLICT(id) DO UPDATE SET last_active = CURRENT_TIMESTAMP""",
        (session_id,),
    )
    if role == "user":
        existing = await db.execute("SELECT name FROM sessions WHERE id = ?", (session_id,))
        row = await existing.fetchone()
        if not row or not row[0]:
            name = content[:40] + ("\u2026" if len(content) > 40 else "")
            await db.execute(
                "UPDATE sessions SET name = ? WHERE id = ?",
                (name, session_id),
            )
    await db.commit()


async def get_history(session_id: str, limit: int = 20) -> list[dict]:
    import json
    db = await get_db()
    async with db.execute(
        """SELECT role, content, images, timestamp FROM conversations
           WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?""",
        (session_id, limit),
    ) as cur:
        rows = await cur.fetchall()
    result = []
    for r in reversed(rows):
        item = {"role": r[0], "content": r[1], "timestamp": r[3]}
        if r[2]:
            try:
                item["images"] = json.loads(r[2])
            except Exception:
                pass
        result.append(item)
    return result


async def clear_history(session_id: str):
    db = await get_db()
    await db.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
    await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    await db.commit()


# -- Sessions --

async def update_session_name(session_id: str, name: str):
    db = await get_db()
    await db.execute(
        """INSERT INTO sessions (id, name) VALUES (?, ?)
           ON CONFLICT(id) DO UPDATE SET name = ?, last_active = CURRENT_TIMESTAMP""",
        (session_id, name, name),
    )
    await db.commit()


async def get_all_sessions() -> list[dict]:
    db = await get_db()
    async with db.execute(
        """SELECT id, created_at, last_active, name,
                  (SELECT COUNT(*) FROM conversations WHERE session_id = sessions.id) as msg_count
           FROM sessions ORDER BY last_active DESC"""
    ) as cur:
        rows = await cur.fetchall()
    return [
        {"session_id": r[0], "created_at": r[1], "last_active": r[2],
         "name": r[3], "message_count": r[4]}
        for r in rows
    ]


async def get_session_meta(session_id: str) -> dict:
    db = await get_db()
    async with db.execute(
        "SELECT summary, summarized_until FROM sessions WHERE id = ?",
        (session_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return {"summary": "", "summarized_until": 0}
    return {"summary": row[0] or "", "summarized_until": row[1] or 0}


# -- Rolling Summary --

async def get_messages_to_summarize(
    session_id: str,
    history_limit: int,
    summarized_until: int,
    batch_size: int,
    early_trigger: int = 0,
) -> tuple[list[dict], int]:
    """Return the next batch of aged-out messages not yet folded into the summary.

    early_trigger: if >0 and this is the first summary (summarized_until == 0),
    fire as soon as this many messages are available.
    """
    db = await get_db()
    async with db.execute(
        "SELECT id FROM conversations WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ) as cur:
        ids = [r[0] for r in await cur.fetchall()]

    total = len(ids)
    if total <= history_limit:
        return [], summarized_until

    boundary_id = ids[total - history_limit - 1]
    pending_ids = [i for i in ids if summarized_until < i <= boundary_id]
    pending_count = len(pending_ids)

    effective_batch = (
        early_trigger
        if (early_trigger > 0 and summarized_until == 0 and pending_count >= early_trigger)
        else batch_size
    )
    if pending_count < effective_batch:
        return [], summarized_until

    async with db.execute(
        """SELECT role, content FROM conversations
           WHERE session_id = ? AND id > ? AND id <= ?
           ORDER BY id ASC""",
        (session_id, summarized_until, boundary_id),
    ) as cur:
        rows = await cur.fetchall()

    return [{"role": r[0], "content": r[1]} for r in rows], boundary_id


async def update_session_summary(session_id: str, summary: str, summarized_until: int):
    db = await get_db()
    await db.execute(
        """INSERT INTO sessions (id, summary, summarized_until) VALUES (?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET summary = ?, summarized_until = ?""",
        (session_id, summary, summarized_until, summary, summarized_until),
    )
    await db.commit()


# -- Long-term Memories --

async def save_memory(content: str, category: str = "general",
                      importance: int = 5, user_id: str | None = None):
    from config import DEFAULT_USER
    from embedding import cosine_similarity, embed_async

    user_id = user_id or DEFAULT_USER

    try:
        new_embedding = await embed_async(content)
    except Exception as e:
        logger.error(f"Embedding failed, saving memory without vector: {e}")
        new_embedding = None

    db = await get_db()

    if new_embedding is not None:
        async with db.execute(
            "SELECT id, embedding FROM memories WHERE user_id = ? AND embedding IS NOT NULL",
            (user_id,),
        ) as cur:
            existing = await cur.fetchall()

        for mem_id, existing_embedding in existing:
            if cosine_similarity(new_embedding, existing_embedding) >= 0.85:
                await db.execute(
                    """UPDATE memories SET last_accessed = CURRENT_TIMESTAMP,
                       access_count = access_count + 1 WHERE id = ?""",
                    (mem_id,),
                )
                await db.commit()
                return

    await db.execute(
        "INSERT INTO memories (user_id, content, category, importance, embedding) VALUES (?, ?, ?, ?, ?)",
        (user_id, content, category, importance, new_embedding),
    )
    await db.commit()


async def search_memories(query: str, user_id: str | None = None, limit: int = 5) -> list[dict]:
    from config import DEFAULT_USER
    from embedding import cosine_similarity, embed_async

    user_id = user_id or DEFAULT_USER

    try:
        query_embedding = await embed_async(query)
    except Exception as e:
        logger.error(f"Embedding failed for memory search: {e}")
        return []

    db = await get_db()
    async with db.execute(
        "SELECT id, content, category, importance, created_at, embedding FROM memories WHERE user_id = ?",
        (user_id,),
    ) as cur:
        rows = await cur.fetchall()

    scored = []
    for mem_id, content, category, importance, created_at, blob in rows:
        if blob is None:
            try:
                blob = await embed_async(content)
                await db.execute("UPDATE memories SET embedding = ? WHERE id = ?", (blob, mem_id))
            except Exception as e:
                logger.error(f"Embedding backfill failed for memory {mem_id}: {e}")
                continue

        sim = cosine_similarity(query_embedding, blob)
        scored.append((sim, {
            "id": mem_id, "content": content, "category": category,
            "importance": importance, "created_at": created_at, "similarity": sim,
        }))

    await db.commit()
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [m for sim, m in scored[:limit] if sim >= 0.35]

    if top:
        for m in top:
            await db.execute(
                """UPDATE memories SET last_accessed = CURRENT_TIMESTAMP,
                   access_count = access_count + 1 WHERE id = ?""",
                (m["id"],),
            )
        await db.commit()

    return top


async def get_memories(user_id: str | None = None, limit: int = 10) -> list[dict]:
    from config import DEFAULT_USER
    user_id = user_id or DEFAULT_USER
    try:
        db = await get_db()
        async with db.execute(
            """SELECT id, content, category, importance, created_at
               FROM memories WHERE user_id = ?
               ORDER BY importance DESC, last_accessed DESC LIMIT ?""",
            (user_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [{"id": r[0], "content": r[1], "category": r[2],
                 "importance": r[3], "created_at": r[4]} for r in rows]
    except Exception:
        logger.exception("Failed to retrieve memories")
        return []


async def delete_memory(user_id: str, memory_id: int):
    db = await get_db()
    await db.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id))
    await db.commit()


async def get_all_memories(user_id: str | None = None) -> list[dict]:
    from config import DEFAULT_USER
    user_id = user_id or DEFAULT_USER
    try:
        db = await get_db()
        async with db.execute(
            """SELECT id, content, category, importance, created_at
               FROM memories WHERE user_id = ? ORDER BY importance DESC""",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [{"id": r[0], "content": r[1], "category": r[2],
                 "importance": r[3], "created_at": r[4]} for r in rows]
    except Exception:
        logger.exception("Failed to retrieve all memories")
        return []
