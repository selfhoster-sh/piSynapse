import aiosqlite
import os

DB_PATH = os.getenv("DB_PATH", "assistant.db")
DEFAULT_USER = os.getenv("ASSISTANT_USER", "default")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
                summary TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'default',
                content TEXT NOT NULL,
                category TEXT,
                importance INTEGER DEFAULT 5,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0
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
                      (SELECT COUNT(*) FROM conversations WHERE session_id = sessions.id) as msg_count
               FROM sessions ORDER BY last_active DESC"""
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "session_id": r[0],
                    "created_at": r[1],
                    "last_active": r[2],
                    "message_count": r[3]
                }
                for r in rows
            ]


async def save_memory(content: str, category: str = "general", importance: int = 5, user_id: str = None):
    user_id = user_id or DEFAULT_USER
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO memories (user_id, content, category, importance) VALUES (?, ?, ?, ?)",
            (user_id, content, category, importance)
        )
        await db.commit()


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
            return [
                {"id": r[0], "content": r[1], "category": r[2], "importance": r[3], "created_at": r[4]}
                for r in rows
            ]


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
