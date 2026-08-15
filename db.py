"""piSynapse Database Layer
SQLite with aiosqlite: conversations, sessions, and long-term memory.
Single persistent connection with WAL mode for Pi-friendly I/O.
"""

import asyncio
import json
import logging
import os

import aiosqlite

from config import DB_PATH

logger = logging.getLogger("piSynapse")

# DB files hold conversations, memories and audit params (incl. e-mail
# bodies). Restrict the process umask so any file SQLite creates
# (assistant.db / -wal / -shm / -journal) is born 0o600, never world-readable.
os.umask(0o077)

_db: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()

_LOCKED_RETRIES = 3


async def _write_with_retry(db: aiosqlite.Connection, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
    """Execute a write, retrying briefly on 'database is locked' / 'busy'."""
    import sqlite3
    for attempt in range(_LOCKED_RETRIES + 1):
        try:
            cur = await db.execute(sql, params)
            await db.commit()
            return cur
        except sqlite3.OperationalError as e:
            if "locked" not in str(e).lower() and "busy" not in str(e).lower():
                raise
            if attempt >= _LOCKED_RETRIES:
                raise
            logger.warning(f"SQLite busy, retrying ({attempt + 1}/{_LOCKED_RETRIES})...")
            await asyncio.sleep(0.25 * (attempt + 1))


async def _secure_db_files() -> None:
    """Force owner-only permissions on the DB and its SQLite sidecars.

    The DB is created on first run (not by install.py), so this runs on
    every startup as a guarantee for fresh and pre-existing installs.
    """
    for path in (DB_PATH, DB_PATH + "-wal", DB_PATH + "-shm", DB_PATH + "-journal"):
        try:
            if os.path.exists(path):
                os.chmod(path, 0o600)
        except OSError as e:
            logger.warning(f"Could not secure permissions on {path}: {e}")


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
        await conn.execute("PRAGMA busy_timeout=10000")
        await _secure_db_files()
        _db = conn
        return _db


async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None


# -- Schema --

# Ordered schema migrations. `user_version` tracks how many are applied.
#
# IMPORTANT — keep this list in sync with the CREATE TABLE definitions in
# init_db() below. The CREATE TABLEs describe the full CURRENT schema (they
# already include every column listed here) and are what brand-new databases
# get. MIGRATIONS only matters for pre-existing databases whose tables were
# created before a column existed. When adding a column:
#   1. add it to the matching CREATE TABLE statement (new DBs), AND
#   2. append a new entry at the END of MIGRATIONS (old DBs).
# Never reorder, edit or remove an existing entry: user_version numbers are
# baked into live databases and renumbering would re-run/skip migrations.
MIGRATIONS: list[tuple[str, str, str]] = [
    ("conversations", "images", "TEXT"),
    ("sessions", "name", "TEXT"),
    ("sessions", "summarized_until", "INTEGER DEFAULT 0"),
    ("memories", "embedding", "BLOB"),
    ("conversations", "reasoning", "TEXT"),
]


async def _get_schema_version(db: aiosqlite.Connection) -> int:
    cur = await db.execute("PRAGMA user_version")
    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def _apply_migrations(db: aiosqlite.Connection):
    version = await _get_schema_version(db)
    for i in range(version, len(MIGRATIONS)):
        table, column, definition = MIGRATIONS[i]
        try:
            await _write_with_retry(db, f"ALTER TABLE {table} ADD COLUMN {column} {definition}")  # noqa: E501
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                logger.warning(f"Migration {table}.{column} failed: {e}")
                break
        await db.execute(f"PRAGMA user_version = {i + 1}")
    await db.commit()


async def init_db():
    db = await get_db()

    await db.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            images     TEXT,
            reasoning  TEXT,
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
        CREATE TABLE IF NOT EXISTS tool_audit_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name      TEXT NOT NULL,
            params         TEXT,
            success        INTEGER NOT NULL,
            duration_ms    REAL,
            error          TEXT,
            is_summary     INTEGER NOT NULL DEFAULT 0,
            day            TEXT,
            total_calls    INTEGER,
            success_count  INTEGER,
            error_count    INTEGER,
            tool_breakdown TEXT,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await db.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id, timestamp)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id, importance DESC)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_tool_audit_created ON tool_audit_log(created_at)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_tool_audit_rollup ON tool_audit_log(is_summary, created_at)")

    await _apply_migrations(db)

    await cleanup_expired_data()

    await db.commit()

    # Sidecar -wal/-shm now exist after the first write; lock them down too.
    await _secure_db_files()


async def _vacuum_if_fragmented(db: aiosqlite.Connection) -> None:
    """Compact the DB file only when it is mostly free pages.

    The tool-audit rollup deletes thousands of detail rows every day, leaving
    free pages behind; an unconditional daily VACUUM would add pointless I/O
    and write-lock contention on every cleanup run. Triggering only above a
    20% free-page ratio (and only for a meaningfully large DB) keeps the file
    compact in practice with negligible overhead. Never raises.
    """
    try:
        async with db.execute("PRAGMA freelist_count") as cur:
            free = (await cur.fetchone())[0]
        async with db.execute("PRAGMA page_count") as cur:
            total = (await cur.fetchone())[0]
        if total > 256 and free / total > 0.2:
            await db.execute("VACUUM")
            logger.info(f"VACUUM: reclaimed {free} free pages (file was {total} pages)")
    except Exception as e:
        logger.warning(f"VACUUM skipped: {e}")


async def cleanup_expired_data() -> tuple[int, int]:
    """Delete data older than the configured retention (0 = keep forever).

    Runs on startup and then periodically (see ``periodic_cleanup_loop``).
    Never raises — a failure (DB locked, etc.) is logged and retried on the
    next cycle so it cannot crash the service.

    Returns (deleted_conversation_rows, deleted_memory_rows).
    """
    from config import CONVERSATION_RETENTION_DAYS, MEMORY_RETENTION_DAYS

    try:
        db = await get_db()
        removed_conv = removed_mem = 0
        if CONVERSATION_RETENTION_DAYS > 0:
            cur = await _write_with_retry(
                db,
                "DELETE FROM conversations WHERE timestamp < datetime('now', ?)",
                (f"-{CONVERSATION_RETENTION_DAYS} days",),
            )
            removed_conv = cur.rowcount if cur.rowcount else 0
            await _write_with_retry(
                db,
                "DELETE FROM sessions WHERE id NOT IN (SELECT DISTINCT session_id FROM conversations)"
            )
        if MEMORY_RETENTION_DAYS > 0:
            cur = await _write_with_retry(
                db,
                "DELETE FROM memories WHERE created_at < datetime('now', ?)",
                (f"-{MEMORY_RETENTION_DAYS} days",),
            )
            removed_mem = cur.rowcount if cur.rowcount else 0
        if removed_conv or removed_mem:
            logger.info(f"Retention cleanup: {removed_conv} conversations, {removed_mem} memories deleted")
        # Free-page compaction (opportunistic, see helper) after the deletes.
        await _vacuum_if_fragmented(db)
        return removed_conv, removed_mem
    except Exception as e:
        logger.warning(f"Retention cleanup failed, will retry next cycle: {e}")
        return 0, 0


# -- Tool audit log --

# Params keys whose values are user content or secrets; their values are
# replaced with [REDACTED] in the audit row so raw email/note/memory text and
# credentials never hit the DB (the log keeps tool_name/success/duration/error
# for accountability).
_AUDIT_REDACT_KEYS = {
    "password", "passwd", "pass", "token", "api_key", "apikey", "api-key",
    "secret", "auth", "authorization", "credential", "credentials",
    "body", "content", "text", "message", "prompt",
}
_AUDIT_PARAMS_MAX_CHARS = 2048


def _redact_params(value):
    """Recursively redact sensitive keys and return a log-safe structure."""
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if _is_redact_key(k) else _redact_params(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_params(v) for v in value]
    return value


def _is_redact_key(key: str) -> bool:
    norm = str(key).lower().replace(" ", "_").replace("-", "_")
    return norm in _AUDIT_REDACT_KEYS


def _audit_params_json(params) -> str | None:
    """Serialise params with sensitive fields redacted and a size cap."""
    if not params:
        return None
    safe = _redact_params(params)
    try:
        out = json.dumps(safe, ensure_ascii=False)
    except (TypeError, ValueError):
        out = json.dumps(_redact_params(str(params)), ensure_ascii=False)
    if len(out) > _AUDIT_PARAMS_MAX_CHARS:
        out = out[:_AUDIT_PARAMS_MAX_CHARS] + " ...(truncated)"
    return out


async def log_tool_call(
    tool_name: str,
    params: dict | None,
    success: bool,
    duration_ms: float | None = None,
    error: str | None = None,
) -> None:
    """Append a row to the tool audit log.

    Deliberately swallows every failure (DB down, locked, schema issue) and
    only logs a warning — this runs inside the tool-call loop's verification
    hook and must never break or stall an actual tool execution.
    """
    try:
        db = await get_db()
        await _write_with_retry(
            db,
            "INSERT INTO tool_audit_log (tool_name, params, success, duration_ms, error) VALUES (?, ?, ?, ?, ?)",
            (tool_name, _audit_params_json(params), 1 if success else 0, duration_ms, error),
        )
    except Exception as e:
        logger.warning(f"Tool audit log write failed for '{tool_name}': {e}")


async def rollup_tool_audit(days: int = 14) -> int:
    """Compress detail rows older than `days` into one daily summary row per day.

    Retention policy: detail rows survive for `days` (default 14), then are
    aggregated into a per-day summary (total/success/error counts + per-tool
    breakdown) and the detail rows are removed. Each day is processed inside
    its own ``BEGIN IMMEDIATE`` transaction so the summary INSERT and the
    detail DELETE commit atomically — a crash can never leave an orphan
    summary row or a partially-removed day. Days that already have a summary
    row are skipped, so a crash between runs cannot produce duplicate
    summaries. Idempotent and never raises.

    Returns the number of days rolled up.
    """
    import sqlite3
    try:
        db = await get_db()
        cutoff = f"-{days} days"
        cur = await db.execute(
            """SELECT substr(created_at, 1, 10) AS day
               FROM tool_audit_log
               WHERE is_summary = 0 AND created_at < datetime('now', ?)
                 AND substr(created_at, 1, 10) NOT IN
                     (SELECT day FROM tool_audit_log WHERE is_summary = 1)
               GROUP BY substr(created_at, 1, 10)""",
            (cutoff,),
        )
        days_found = [row[0] for row in await cur.fetchall()]

        days_summarized = 0
        for day in days_found:
            # Each day is atomic: summary INSERT + detail DELETE in one txn.
            for attempt in range(_LOCKED_RETRIES + 1):
                try:
                    await db.execute("BEGIN IMMEDIATE")
                    breakdown = {}
                    cur2 = await db.execute(
                        """SELECT tool_name, COUNT(*) FROM tool_audit_log
                           WHERE is_summary = 0 AND created_at < datetime('now', ?)
                             AND substr(created_at, 1, 10) = ?
                           GROUP BY tool_name""",
                        (cutoff, day),
                    )
                    for name, cnt in await cur2.fetchall():
                        breakdown[name] = cnt

                    await db.execute(
                        """INSERT INTO tool_audit_log
                           (is_summary, day, total_calls, success_count, error_count, tool_breakdown, tool_name, success, created_at)
                           SELECT 1, ?, COUNT(*), SUM(success), SUM(1 - success), ?, 'rollup', 1, ?
                           FROM tool_audit_log
                           WHERE is_summary = 0 AND created_at < datetime('now', ?)
                             AND substr(created_at, 1, 10) = ?""",
                        (day, json.dumps(breakdown), day, cutoff, day),
                    )
                    await db.execute(
                        """DELETE FROM tool_audit_log
                           WHERE is_summary = 0 AND created_at < datetime('now', ?)
                             AND substr(created_at, 1, 10) = ?""",
                        (cutoff, day),
                    )
                    await db.commit()
                    days_summarized += 1
                    break
                except sqlite3.OperationalError as e:
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    if "locked" not in str(e).lower() and "busy" not in str(e).lower():
                        raise
                    if attempt >= _LOCKED_RETRIES:
                        raise
                    logger.warning(f"SQLite busy during rollup of {day}, retrying ({attempt + 1}/{_LOCKED_RETRIES})...")
                    await asyncio.sleep(0.25 * (attempt + 1))
                except Exception:
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    raise

        if days_summarized:
            logger.info(f"Tool audit rollup: {days_summarized} day(s) summarized")
        return days_summarized
    except Exception as e:
        logger.warning(f"Tool audit rollup failed: {e}")
        return 0


ROLLUP_INTERVAL_SECONDS = 24 * 3600  # retention sweep runs once a day


async def periodic_rollup_loop(interval: float = ROLLUP_INTERVAL_SECONDS, sleep=asyncio.sleep):
    """Run rollup_tool_audit() once per `interval` until cancelled.

    Mirrors the "never raise" principle of the verification hook: any failure
    (DB lock, disk issue, ...) is logged and retried on the next cycle instead
    of crashing the service. Cancellation propagates so the app can shut down
    cleanly.

    `sleep` is injectable for tests (avoids waiting a real 24 hours).
    """
    while True:
        await sleep(interval)
        try:
            await rollup_tool_audit()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Periodic rollup failed, will retry next cycle: {e}")


CLEANUP_INTERVAL_SECONDS = 24 * 3600  # retention cleanup runs once a day


async def periodic_cleanup_loop(interval: float = CLEANUP_INTERVAL_SECONDS, sleep=asyncio.sleep):
    """Run cleanup_expired_data() once per `interval` until cancelled.

    Mirrors the "never raise" principle of the retention sweep — cleanup
    failures are logged and retried on the next cycle instead of crashing the
    service. Cancellation propagates so the app can shut down cleanly.

    `sleep` is injectable for tests (avoids waiting a real 24 hours).
    """
    while True:
        await sleep(interval)
        try:
            await cleanup_expired_data()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Periodic retention cleanup failed, will retry next cycle: {e}")


# -- Conversations --

async def save_message(session_id: str, role: str, content: str, images: list[str] | None = None, reasoning: str | None = None):
    import json
    images_json = json.dumps(images) if images else None
    db = await get_db()
    await db.execute(
        "INSERT INTO conversations (session_id, role, content, images, reasoning) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, images_json, reasoning),
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


async def get_history(session_id: str, limit: int = 20, include_reasoning: bool = False) -> list[dict]:
    import json
    db = await get_db()
    async with db.execute(
        """SELECT role, content, images, timestamp, reasoning FROM conversations
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
        if include_reasoning and r[4]:
            item["reasoning"] = r[4]
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
    from config import DEFAULT_USER, MEMORY_SIMILARITY_THRESHOLD
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
            if cosine_similarity(new_embedding, existing_embedding) >= MEMORY_SIMILARITY_THRESHOLD:
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


async def search_memories(query: str, user_id: str | None = None, limit: int = 5, query_embedding: bytes | None = None) -> list[dict]:
    from config import DEFAULT_USER
    from embedding import cosine_similarity, embed_async

    user_id = user_id or DEFAULT_USER

    try:
        if query_embedding is None:
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

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [m for sim, m in scored[:limit] if sim >= 0.35]

    if top:
        for m in top:
            await db.execute(
                """UPDATE memories SET last_accessed = CURRENT_TIMESTAMP,
                   access_count = access_count + 1 WHERE id = ?""",
                (m["id"],),
            )

    # Single commit covers both the embedding backfill and the access stats.
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
