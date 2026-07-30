#!/usr/bin/env python3
"""
piSynapse Database Layer
Manages SQLite with aiosqlite: conversations, sessions, and long-term memory.
"""

import aiosqlite
import os
import logging
from embedding import embed_async, cosine_similarity

logger = logging.getLogger("piSynapse")

DB_PATH    = os.getenv("DB_PATH", "assistant.db")
DEFAULT_USER = os.getenv("ASSISTANT_USER", "default")

# Cosine similarity threshold above which a new memory is considered
# a duplicate of an existing one (see MEMORY_SIMILARITY_THRESHOLD in .env)
SIMILARITY_THRESHOLD = float(os.getenv("MEMORY_SIMILARITY_THRESHOLD", "0.68"))


# ── Database Initialization ──────────────────────────────────────────────────
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA cache_size=10000")
        await db.execute("PRAGMA temp_store=MEMORY")

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

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_session
            ON conversations(session_id, timestamp)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_user
            ON memories(user_id, importance DESC)
        """)

        # Migration: add name column if upgrading from older DB
        try:
            await db.execute("ALTER TABLE sessions ADD COLUMN name TEXT")
        except Exception:
            pass

        # Migration: add embedding column if upgrading from older DB
        try:
            await db.execute("ALTER TABLE memories ADD COLUMN embedding BLOB")
        except Exception:
            pass

        # Migration: add summarized_until column if upgrading from older DB
        try:
            await db.execute("ALTER TABLE sessions ADD COLUMN summarized_until INTEGER DEFAULT 0")
        except Exception:
            pass

        await db.commit()


# ── Save a chat message ──────────────────────────────────────────────────────
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


# ── Retrieve chat history for a session ──────────────────────────────────────
async def get_history(session_id: str, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT role, content FROM conversations
               WHERE session_id = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (session_id, limit)
        ) as cur:
            rows = await cur.fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


# ── Delete all messages and session record ───────────────────────────────────
async def clear_history(session_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()


# ── Rename a session ─────────────────────────────────────────────────────────
async def update_session_name(session_id: str, name: str):
    """Saves session name to DB — to see the same name across devices."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO sessions (id, name) VALUES (?, ?)
               ON CONFLICT(id) DO UPDATE SET name = ?, last_active = CURRENT_TIMESTAMP""",
            (session_id, name, name)
        )
        await db.commit()


# ── Rolling conversation summary (keeps old context without resending it) ────
async def get_session_meta(session_id: str) -> dict:
    """Returns the current rolling summary and how far it has been computed."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT summary, summarized_until FROM sessions WHERE id = ?",
            (session_id,)
        ) as cur:
            row = await cur.fetchone()
    if row is None:
        return {"summary": "", "summarized_until": 0}
    return {"summary": row[0] or "", "summarized_until": row[1] or 0}


async def get_messages_to_summarize(session_id: str, history_limit: int,
                                     summarized_until: int, batch_size: int) -> tuple[list[dict], int]:
    """Returns the next batch of messages that have aged out of the recent
    history window (sent to the LLM) and haven't been folded into the summary
    yet. Waits until at least `batch_size` such messages have piled up, so the
    summarizer isn't called on every single turn."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM conversations WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        ) as cur:
            ids = [r[0] for r in await cur.fetchall()]

        total = len(ids)
        if total <= history_limit:
            return [], summarized_until

        boundary_id = ids[total - history_limit - 1]
        pending_ids = [i for i in ids if summarized_until < i <= boundary_id]
        if len(pending_ids) < batch_size:
            return [], summarized_until

        async with db.execute(
            """SELECT role, content FROM conversations
               WHERE session_id = ? AND id > ? AND id <= ?
               ORDER BY id ASC""",
            (session_id, summarized_until, boundary_id)
        ) as cur:
            rows = await cur.fetchall()

    return [{"role": r[0], "content": r[1]} for r in rows], boundary_id


async def update_session_summary(session_id: str, summary: str, summarized_until: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO sessions (id, summary, summarized_until) VALUES (?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET summary = ?, summarized_until = ?""",
            (session_id, summary, summarized_until, summary, summarized_until)
        )
        await db.commit()


# ── List all sessions with message counts ────────────────────────────────────
async def get_all_sessions() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
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


# ── Save a long-term memory ──────────────────────────────────────────────────
async def save_memory(content: str, category: str = "general",
                      importance: int = 5, user_id: str = None):
    user_id = user_id or DEFAULT_USER

    # Compute an embedding for semantic search and duplicate detection
    try:
        new_embedding = await embed_async(content)
    except Exception as e:
        logger.error(f"Embedding generation failed, saving memory without vector: {e}")
        new_embedding = None

    async with aiosqlite.connect(DB_PATH) as db:
        if new_embedding is not None:
            # If a near-duplicate memory already exists for this user, just
            # bump its access stats instead of inserting a new row
            async with db.execute(
                "SELECT id, embedding FROM memories WHERE user_id = ? AND embedding IS NOT NULL",
                (user_id,)
            ) as cur:
                existing = await cur.fetchall()

            for mem_id, existing_embedding in existing:
                if cosine_similarity(new_embedding, existing_embedding) >= SIMILARITY_THRESHOLD:
                    await db.execute(
                        """UPDATE memories SET last_accessed = CURRENT_TIMESTAMP,
                           access_count = access_count + 1 WHERE id = ?""",
                        (mem_id,)
                    )
                    await db.commit()
                    return

        await db.execute(
            "INSERT INTO memories (user_id, content, category, importance, embedding) VALUES (?, ?, ?, ?, ?)",
            (user_id, content, category, importance, new_embedding)
        )
        await db.commit()


# ── Semantic search over memories (embedding cosine similarity) ─────────────
async def search_memories(query: str, user_id: str = None, limit: int = 5) -> list[dict]:
    """Returns the memories whose content is semantically closest to `query`."""
    user_id = user_id or DEFAULT_USER

    try:
        query_embedding = await embed_async(query)
    except Exception as e:
        logger.error(f"Embedding generation failed for memory search: {e}")
        return []

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id, content, category, importance, created_at, embedding
               FROM memories WHERE user_id = ?""",
            (user_id,)
        ) as cur:
            rows = await cur.fetchall()

        scored = []
        for mem_id, content, category, importance, created_at, blob in rows:
            # Backfill embeddings for memories saved before this feature existed
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
                "importance": importance, "created_at": created_at,
                "similarity": sim,
            }))

        await db.commit()

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [m for sim, m in scored[:limit] if sim > 0]

    if top:
        async with aiosqlite.connect(DB_PATH) as db:
            for m in top:
                await db.execute(
                    """UPDATE memories SET last_accessed = CURRENT_TIMESTAMP,
                       access_count = access_count + 1 WHERE id = ?""",
                    (m["id"],)
                )
            await db.commit()

    return top


# ── Retrieve top memories for a user (by importance + recency) ───────────────
async def get_memories(user_id: str = None, limit: int = 10) -> list[dict]:
    user_id = user_id or DEFAULT_USER
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id, content, category, importance, created_at
               FROM memories WHERE user_id = ?
               ORDER BY importance DESC, last_accessed DESC LIMIT ?""",
            (user_id, limit)
        ) as cur:
            rows = await cur.fetchall()
    return [{"id": r[0], "content": r[1], "category": r[2],
             "importance": r[3], "created_at": r[4]} for r in rows]


# ── Delete a memory by ID (scoped to user) ───────────────────────────────────
async def delete_memory(user_id: str, memory_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id))
        await db.commit()


# ── List all memories for a user ─────────────────────────────────────────────
async def get_all_memories(user_id: str = None) -> list[dict]:
    user_id = user_id or DEFAULT_USER
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id, content, category, importance, created_at
               FROM memories WHERE user_id = ?
               ORDER BY importance DESC""",
            (user_id,)
        ) as cur:
            rows = await cur.fetchall()
    return [{"id": r[0], "content": r[1], "category": r[2],
             "importance": r[3], "created_at": r[4]} for r in rows]
