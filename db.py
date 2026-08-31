"""piSynapse Database Layer
SQLite with aiosqlite: conversations, sessions, and long-term memory.
Single persistent connection with WAL mode for Pi-friendly I/O.
"""

import asyncio
import csv
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

# Backfill task control (prevents unbounded embedding tasks on legacy memories)
_BACKFILL_SEMAPHORE = asyncio.Semaphore(2)
_BACKFILL_BATCH_SIZE = 10
_backfill_task: asyncio.Task | None = None

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


async def _commit_with_retry(db: aiosqlite.Connection) -> None:
    """Commit a multi-statement write, retrying briefly on locked/busy.

    Complementary to _write_with_retry for hand-rolled transaction bodies
    (save_message, clear_history, ...) whose statements must stay grouped in
    a single transaction. busy_timeout already buffers most contention; this
    is a secondary safety net on the critical chat completion path.
    """
    import sqlite3
    for attempt in range(_LOCKED_RETRIES + 1):
        try:
            await db.commit()
            return
        except sqlite3.OperationalError as e:
            if "locked" not in str(e).lower() and "busy" not in str(e).lower():
                raise
            if attempt >= _LOCKED_RETRIES:
                raise
            logger.warning(f"SQLite busy on commit, retrying ({attempt + 1}/{_LOCKED_RETRIES})...")
            await asyncio.sleep(0.25 * (attempt + 1))


async def _secure_db_files() -> None:
    """Force owner-only permissions on the DB and its SQLite sidecars.

    The DB is created on first run (not by install.py), so this runs on
    every startup as a guarantee for fresh and pre-existing installs.
    """
    for path in (DB_PATH, DB_PATH + "-wal", DB_PATH + "-shm", DB_PATH + "-journal"):
        path = os.path.abspath(path)
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
    # Stop any in-flight embedding backfill (fire-and-forget: it runs on its
    # own connection, so this is housekeeping, not a correctness requirement).
    if _backfill_task is not None and not _backfill_task.done():
        _backfill_task.cancel()
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
    ("conversations", "embedding", "BLOB"),
    ("tool_audit_log", "expected_tool", "TEXT"),
    ("tool_audit_log", "corrected_at", "DATETIME"),
    ("tool_audit_log", "verification_status", "TEXT"),
    ("tool_audit_log", "expected_group", "TEXT"),
    ("tool_audit_log", "confirmed_at", "DATETIME"),
    ("tool_audit_log", "conversation_id", "INTEGER"),
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
            embedding  BLOB,
            timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS message_feedback (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL UNIQUE,
            value      TEXT NOT NULL CHECK (value IN ('up','down')),
            note       TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            expected_tool  TEXT,
            corrected_at   DATETIME,
            expected_group TEXT,
            verification_status TEXT,
            confirmed_at   DATETIME,
            conversation_id INTEGER
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS intent_audit_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            message      TEXT NOT NULL,
            chosen_group TEXT,
            best_sim     REAL,
            margin       REAL,
            source       TEXT NOT NULL,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS email_session_map (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            seq        INTEGER NOT NULL,
            message_id TEXT NOT NULL,
            subject    TEXT DEFAULT '',
            sender     TEXT DEFAULT '',
            preview    TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, seq)
        )
    """)

    await db.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id, timestamp)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id, importance DESC)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_tool_audit_created ON tool_audit_log(created_at)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_tool_audit_rollup ON tool_audit_log(is_summary, created_at)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_intent_audit_created ON intent_audit_log(created_at)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_intent_audit_source ON intent_audit_log(source, created_at)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_email_session_map_session ON email_session_map(session_id, seq)")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS notes_session_map (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            seq        INTEGER NOT NULL,
            note_id    INTEGER NOT NULL,
            title      TEXT DEFAULT '',
            category   TEXT DEFAULT '',
            preview    TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, seq)
        )
    """)

    await db.execute("CREATE INDEX IF NOT EXISTS idx_notes_session_map_session ON notes_session_map(session_id, seq)")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS tasks_session_map (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            seq        INTEGER NOT NULL,
            uid        TEXT NOT NULL,
            summary    TEXT DEFAULT '',
            due        TEXT DEFAULT '',
            priority   INTEGER DEFAULT 0,
            completed  INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, seq)
        )
    """)

    await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_session_map_session ON tasks_session_map(session_id, seq)")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS calendar_session_map (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            seq        INTEGER NOT NULL,
            uid        TEXT NOT NULL,
            summary    TEXT DEFAULT '',
            start_time TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, seq)
        )
    """)

    await db.execute("CREATE INDEX IF NOT EXISTS idx_calendar_session_map_session ON calendar_session_map(session_id, seq)")

    # FTS5 full-text index for session message search
    # unicode61 tokenizer: proper Turkish/diacritik support
    # content= + content_rowid= : external-content table (conversations)
    await db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts
        USING fts5(content, session_id, content='conversations', content_rowid='id',
                   tokenize='unicode61 remove_diacritics 2')
    """)
    # Migrate old ascii tokenizer → unicode61 (one-time, only if needed).
    # CREATE IF NOT EXISTS won't recreate an existing table with the old
    # tokenizer, so we must detect and rebuild the schema explicitly.
    try:
        async with db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='conversations_fts'") as cur:
            row = await cur.fetchone()
            fts_sql = row[0] if row else ""
        if fts_sql and "unicode61" not in fts_sql:
            logger.info("FTS5 tokenizer migration: ascii → unicode61")
            await db.execute("DROP TABLE IF EXISTS conversations_fts")
            await db.execute("""
                CREATE VIRTUAL TABLE conversations_fts
                USING fts5(content, session_id, content='conversations', content_rowid='id',
                           tokenize='unicode61 remove_diacritics 2')
            """)
            await db.execute("""
                INSERT INTO conversations_fts (rowid, content, session_id)
                SELECT id, content, session_id FROM conversations
            """)
        else:
            # Light drift check: rebuild only if row counts diverge
            # (e.g. crash mid-write). Avoids O(N) rebuild on every startup.
            async with db.execute("SELECT COUNT(*) FROM conversations") as cur:
                conv_count = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM conversations_fts") as cur:
                fts_count = (await cur.fetchone())[0]
            if conv_count != fts_count:
                logger.info(f"FTS5 drift detected (conversations={conv_count}, fts={fts_count}) — rebuilding")
                await db.execute("INSERT INTO conversations_fts(conversations_fts) VALUES('rebuild')")
    except Exception as e:
        logger.warning(f"FTS5 migration/drift check failed (non-fatal): {e}")

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
            # Purge matching FTS5 rows
            await _write_with_retry(
                db,
                "DELETE FROM conversations_fts WHERE rowid NOT IN (SELECT id FROM conversations)",
            )
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
    # E-mail fields: recipient addresses, subject and sender are PII and
    # must not land in the audit log in plaintext.
    "to", "cc", "bcc", "from", "sender", "recipient", "recipients",
    "subject", "reply_to", "replyto", "from_address", "to_address",
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
    verification_status: str | None = None,
) -> int | None:
    """Append a row to the tool audit log.

    ``verification_status`` records the outcome of ID-based backend
    verification (one of "verified", "verified_by_fallback", "unverified",
    "verification_failed", or None when verification is not applicable).

    Returns the new row's id (the audit_id the frontend uses to attach a
    correction to this exact tool call), or None on failure.

    Deliberately swallows every failure (DB down, locked, schema issue) and
    only logs a warning — this runs inside the tool-call loop's verification
    hook and must never break or stall an actual tool execution.
    """
    try:
        db = await get_db()
        cur = await _write_with_retry(
            db,
            "INSERT INTO tool_audit_log (tool_name, params, success, duration_ms, error, verification_status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tool_name, _audit_params_json(params), 1 if success else 0, duration_ms, error, verification_status),
        )
        return cur.lastrowid
    except Exception as e:
        logger.warning(f"Tool audit log write failed for '{tool_name}': {e}")
        return None


async def log_intent_audit(message: str, chosen_group: str | None,
                           best_sim: float | None, margin: float | None,
                           source: str) -> None:
    """Fire-and-forget intent ambiguity record. Never raises."""
    try:
        db = await get_db()
        await db.execute(
            "INSERT INTO intent_audit_log (message, chosen_group, best_sim, margin, source) "
            "VALUES (?, ?, ?, ?, ?)",
            (message[:500], chosen_group, best_sim, margin, source),
        )
        await db.commit()
    except Exception as e:
        logger.warning(f"Intent audit write failed (source={source}): {e}")


async def set_tool_correction(audit_id: int, expected_tool: str | None,
                              expected_group: str | None = None) -> bool:
    """Set a correction on a tool audit log entry.

    Updates expected_tool and/or expected_group and sets corrected_at to
    current timestamp. expected_tool is a precise positive signal (exact
    tool name); expected_group is a coarse signal (domain) used when the
    user only picks a group. Either may be NULL. Sets confirmed_at to NULL:
    confirmation and correction are mutually exclusive feedback states, so a
    row always holds at most one of them. Returns True if a row was updated,
    False if not found.
    """
    try:
        db = await get_db()
        cur = await db.execute(
            "UPDATE tool_audit_log SET expected_tool = ?, expected_group = ?, "
            "corrected_at = CURRENT_TIMESTAMP, confirmed_at = NULL WHERE id = ?",
            (expected_tool, expected_group, audit_id),
        )
        await db.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.warning(f"Tool correction update failed for audit_id={audit_id}: {e}")
        return False


async def get_audit_tool_name(audit_id: int) -> str | None:
    """Return the tool_name of an audit log row, or None if not found."""
    try:
        db = await get_db()
        cur = await db.execute(
            "SELECT tool_name FROM tool_audit_log WHERE id = ?", (audit_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.warning(f"fetch audit tool_name failed for audit_id={audit_id}: {e}")
        return None


async def set_tool_confirmation(audit_id: int) -> bool:
    """Record a positive (confirmation) signal on a tool audit log entry.

    Sets confirmed_at to the current timestamp. Confirmation is the opposite
    of a correction: any previously stored expected_tool/expected_group and
    their corrected_at are cleared so a row never holds two opposing signals.
    Returns True if a row was updated, False if not found.
    """
    try:
        db = await get_db()
        cur = await db.execute(
            "UPDATE tool_audit_log SET confirmed_at = CURRENT_TIMESTAMP, "
            "expected_tool = NULL, expected_group = NULL, corrected_at = NULL "
            "WHERE id = ?",
            (audit_id,),
        )
        await db.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.warning(f"Tool confirmation update failed for audit_id={audit_id}: {e}")
        return False


async def upsert_message_feedback(message_id: int, value: str,
                                  note: str | None = None) -> bool:
    """Store a user's 👍/👎 verdict for an assistant message that had no tool
    call (or whose round failed before any audit existed). One row per message:
    pressing the other thumb overwrites the stored verdict; a note can be
    attached to a 👎 to capture *why* it was wrong (model dropped the intent,
    asked instead of acting, hallucinated, …). Never raises.
    """
    if value not in ("up", "down"):
        return False
    note = (note or "").strip() or None
    try:
        db = await get_db()
        async with db.execute(
            "SELECT role FROM conversations WHERE id = ?", (message_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row or row[0] != "assistant":
            return False
        await db.execute(
            """INSERT INTO message_feedback (message_id, value, note, created_at, updated_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
               ON CONFLICT(message_id) DO UPDATE SET
                 value = excluded.value, note = excluded.note, updated_at = CURRENT_TIMESTAMP""",
            (message_id, value, note),
        )
        await _commit_with_retry(db)
        return True
    except Exception as e:
        logger.warning(f"Message feedback upsert failed for message_id={message_id}: {e}")
        return False


async def link_audits_to_message(conversation_id: int, audit_ids: list[int]):
    """Bind audit rows to the assistant message that produced them.

    Called after the assistant message is written, using the audit_ids the
    stream collected from its SSE tool events. `IS NULL` guard keeps a row
    owned by an earlier message (e.g. a previous regeneration) untouched.
    Never raises; returns the number of rows linked.
    """
    if not audit_ids or conversation_id is None:
        return 0
    try:
        db = await get_db()
        ph = ",".join("?" * len(audit_ids))
        cur = await db.execute(
            f"UPDATE tool_audit_log SET conversation_id = ? WHERE id IN ({ph}) AND conversation_id IS NULL",
            (conversation_id, *audit_ids),
        )
        await _commit_with_retry(db)
        return cur.rowcount
    except Exception as e:
        logger.warning(f"Audit->message link failed for conversation_id={conversation_id}: {e}")
        return 0


async def purge_intent_audit(days: int = 30) -> int:
    """Delete intent audit rows older than `days`. Never raises; returns deleted count."""
    try:
        db = await get_db()
        cur = await db.execute(
            "DELETE FROM intent_audit_log WHERE created_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        await db.commit()
        return cur.rowcount
    except Exception as e:
        logger.warning(f"Intent audit purge failed: {e}")
        return 0


# -- Audit export before retention rollup --

# The full detail-row shape: every audit column plus the conversation the row
# was linked to (thumbs/fine-tuning context survives the 14-day purge).
AUDIT_EXPORT_COLUMNS = [
    "id", "tool_name", "params", "success", "duration_ms", "error", "is_summary",
    "day", "total_calls", "success_count", "error_count", "tool_breakdown",
    "created_at", "expected_tool", "corrected_at", "verification_status",
    "expected_group", "confirmed_at", "conversation_id", "session_id",
]


def audit_export_dir() -> str:
    """Directory for pre-rollup audit exports.

    `AUDIT_EXPORT_DIR` env wins; otherwise ``<dirname of DB_PATH>/audit_exports``
    — in production that is ``audit_exports/`` next to ``assistant.db``, and in
    tests it lands inside the tmp fixture DB's own directory (no repo litter).
    """
    env = os.getenv("AUDIT_EXPORT_DIR")
    if env:
        return env
    return os.path.join(os.path.dirname(DB_PATH), "audit_exports")


def _write_audit_csv(day: str, rows: list[tuple]) -> int:
    """Write `rows` to ``tool-audit-<day>.csv`` atomically (tmp + os.replace).

    Runs in a worker thread; overwrites the day's file (idempotent — a crash
    after the write but before the rollup commit just re-writes the same file).
    Raises on failure so the caller's rollback keeps the rows for the next try.
    """
    outdir = audit_export_dir()
    os.makedirs(outdir, exist_ok=True)
    final = os.path.join(outdir, f"tool-audit-{day}.csv")
    tmp = final + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(AUDIT_EXPORT_COLUMNS)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])
    os.replace(tmp, final)
    return len(rows)


async def export_tool_audit_day(day: str, cutoff_sql: str) -> int:
    """Fetch and export every detail row of `day` to CSV; returns row count.

    Called INSIDE the rollup transaction: on success the caller proceeds to
    summarize + delete; on exception it rolls back, so nothing is discarded
    until its archive exists.
    """
    cols = ", ".join(
        "c.session_id" if c == "session_id" else "t." + c
        for c in AUDIT_EXPORT_COLUMNS
    )
    db = await get_db()
    cur = await db.execute(
        f"""SELECT {cols}
            FROM tool_audit_log t
            LEFT JOIN conversations c ON c.id = t.conversation_id
            WHERE t.is_summary = 0 AND t.created_at < datetime('now', ?)
              AND substr(t.created_at, 1, 10) = ?""",
        (cutoff_sql, day),
    )
    rows = await cur.fetchall()
    if not rows:
        return 0
    return await asyncio.to_thread(_write_audit_csv, day, rows)


async def rollup_tool_audit(days: int = 14) -> int:
    """Compress detail rows older than `days` into one daily summary row per day.

    Retention policy: detail rows survive for `days` (default 14), then are
    exported to ``audit_exports/`` as per-day CSV files (``tool-audit-YYYY-MM-DD.csv``,
    one row per audited call, incl. the linked conversation), aggregated into a
    per-day summary (total/success/error counts + per-tool breakdown) and the
    detail rows are removed. Each day is processed inside its own ``BEGIN
    IMMEDIATE`` transaction so the export completion, the summary INSERT and the
    detail DELETE are all-or-nothing: a failed export rolls the day back and
    nothing is discarded until a copy exists on disk. Days that already have a
    summary row are skipped, so a crash between runs cannot produce duplicate
    summaries (or duplicate exports — the day's CSV is overwritten in place).
    Idempotent and never raises.

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

                    # Archive first, delete second: a failed export raises and
                    # rolls the day back, so detail rows are never discarded
                    # without a CSV copy existing on disk.
                    await export_tool_audit_day(day, cutoff)

                    await db.execute(
                        """INSERT INTO tool_audit_log
                           (is_summary, day, total_calls, success_count, error_count, tool_breakdown, tool_name, success, created_at, expected_tool, corrected_at)
                           SELECT 1, ?, COUNT(*), SUM(success), SUM(1 - success), ?, 'rollup', 1, ?, NULL, NULL
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
            await purge_intent_audit()
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

    # Retry dedup: same user message as the last row → skip to avoid
    # duplicate context when the frontend re-sends after regenerate.
    if role == "user":
        async with db.execute(
            "SELECT role, content FROM conversations "
            "WHERE session_id = ? ORDER BY id DESC LIMIT 1", (session_id,)
        ) as cur:
            last = await cur.fetchone()
            if last and last[0] == "user" and last[1] == content:
                return  # duplicate — do not insert

    # Generate embedding for semantic search (best-effort, never blocks chat on failure)
    embedding_blob = None
    if content and content.strip():
        try:
            from embedding import embed_async
            embedding_blob = await embed_async(content)
        except Exception as e:
            logger.warning(f"Embedding failed for save_message (non-fatal): {e}")

    await db.execute(
        "INSERT INTO conversations (session_id, role, content, images, reasoning, embedding) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, role, content, images_json, reasoning, embedding_blob),
    )
    # Keep FTS5 index in sync
    async with db.execute("SELECT last_insert_rowid()") as cur:
        rowid = (await cur.fetchone())[0]
    await db.execute(
        "INSERT INTO conversations_fts (rowid, content, session_id) VALUES (?, ?, ?)",
        (rowid, content, session_id),
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
            from title import generate_rake_title
            name = generate_rake_title(content)
            await db.execute(
                "UPDATE sessions SET name = ? WHERE id = ?",
                (name, session_id),
            )
    await _commit_with_retry(db)
    return rowid


async def delete_last_assistant(session_id: str) -> bool:
    """Delete the last assistant message in a session.

    Returns True if a row was removed, False if no assistant message existed.
    Used by the regenerate flow: the old response is purged before the user
    message is re-sent so the model never sees the stale reply in context.
    """
    db = await get_db()
    async with db.execute(
        "SELECT id FROM conversations "
        "WHERE session_id = ? AND role = 'assistant' ORDER BY id DESC LIMIT 1",
        (session_id,),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return False
    await db.execute("DELETE FROM conversations WHERE id = ?", (row[0],))
    await db.execute("DELETE FROM conversations_fts WHERE rowid = ?", (row[0],))
    await _commit_with_retry(db)
    return True


async def delete_branch(session_id: str, anchor_id: int) -> list[int]:
    """Truncate a conversation from an anchor message onward (regenerate branch).

    Deletes the anchored message and everything saved after it (messages are
    appended strictly in id order), so a regenerated reply never sits on a
    stale tail — both in the model's context window and in the UI's history.
    Returns the list of deleted message ids (FTS rows are removed in lockstep).

    Unlike delete_last_assistant this is position-agnostic: the frontend picks
    ANY assistant message to regenerate and the whole downstream tail goes away,
    exactly like ChatGPT/Claude's branch semantics for old responses.
    """
    db = await get_db()
    async with db.execute(
        "SELECT id FROM conversations WHERE session_id = ? AND id >= ? ORDER BY id",
        (session_id, anchor_id),
    ) as cur:
        ids = [r[0] for r in await cur.fetchall()]
    if ids:
        ph = ",".join("?" * len(ids))
        await db.execute(
            f"DELETE FROM conversations WHERE session_id = ? AND id IN ({ph})",
            (session_id, *ids),
        )
        await db.execute(f"DELETE FROM conversations_fts WHERE rowid IN ({ph})", ids)
    # Keep the session alive + surfaced even though no rows were inserted.
    await db.execute(
        "INSERT INTO sessions (id) VALUES (?) "
        "ON CONFLICT(id) DO UPDATE SET last_active = CURRENT_TIMESTAMP",
        (session_id,),
    )
    await _commit_with_retry(db)
    return ids


async def get_history(session_id: str, limit: int = 20, include_reasoning: bool = False,
                      include_audits: bool = False) -> list[dict]:
    import json
    db = await get_db()
    async with db.execute(
        """SELECT id, role, content, images, timestamp, reasoning FROM conversations
           WHERE session_id = ? ORDER BY id DESC LIMIT ?""",
        (session_id, limit),
    ) as cur:
        rows = await cur.fetchall()
    # Per-assistant-message audit list for the C-7 feedback UI. Only used by
    # /chat/history; the LLM context path keeps include_audits=False so audit
    # data never pollutes model input.
    audits_by_msg: dict[int, list[dict]] = {}
    fb_by_msg: dict[int, tuple] = {}
    if include_audits and rows:
        ids = [r[0] for r in rows]
        ph = ",".join("?" * len(ids))
        async with db.execute(
            f"""SELECT m.id, a.id, a.tool_name, a.confirmed_at, a.corrected_at, a.expected_group
                FROM conversations m JOIN tool_audit_log a ON a.conversation_id = m.id
                WHERE m.id IN ({ph}) ORDER BY m.id, a.id""",
            tuple(ids),
        ) as cur:
            for mid, aid, tool, c_at, cor_at, grp in await cur.fetchall():
                audits_by_msg.setdefault(mid, []).append(
                    {"audit_id": aid, "tool_name": tool,
                     "confirmed_at": c_at, "corrected_at": cor_at, "expected_group": grp}
                )
        # Message-level verdict (👍/👎) for messages without tool audits —
        # same /chat/history-only gate so context never sees it.
        async with db.execute(
            f"SELECT message_id, value, note FROM message_feedback WHERE message_id IN ({ph})",
            tuple(ids),
        ) as cur:
            for mid, val, note in await cur.fetchall():
                fb_by_msg[mid] = (val, note)
    result = []
    for r in reversed(rows):
        item = {"id": r[0], "role": r[1], "content": r[2], "timestamp": r[4]}
        if r[3]:
            try:
                item["images"] = json.loads(r[3])
            except Exception:
                pass
        if include_reasoning and r[5]:
            item["reasoning"] = r[5]
        if include_audits and r[0] in audits_by_msg:
            item["audits"] = audits_by_msg[r[0]]
        if include_audits and r[0] in fb_by_msg:
            fbval, fbnote = fb_by_msg[r[0]]
            item["feedback"] = fbval
            if fbnote:
                item["feedback_note"] = fbnote
        result.append(item)
    return result


async def clear_history(session_id: str):
    db = await get_db()
    await db.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
    await db.execute("DELETE FROM conversations_fts WHERE session_id = ?", (session_id,))
    await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    await db.execute("DELETE FROM email_session_map WHERE session_id = ?", (session_id,))
    await db.execute("DELETE FROM notes_session_map WHERE session_id = ?", (session_id,))
    await db.execute("DELETE FROM tasks_session_map WHERE session_id = ?", (session_id,))
    await db.execute("DELETE FROM calendar_session_map WHERE session_id = ?", (session_id,))
    await _commit_with_retry(db)


async def search_sessions(query: str, limit: int = 20) -> list[dict]:
    """Hybrid search: FTS5 keyword + semantic embedding.

    FTS5 gives exact keyword matches (ranked by BM25), semantic gives meaning
    matches (e.g. 'hava nasıl' ↔ 'weather outside') via cosine similarity.
    Results are merged, deduplicated, and capped at `limit`.
    Falls back to LIKE if FTS5 query fails.
    """
    import re as _re
    db = await get_db()
    # Sanitize for FTS5: strip special match characters
    safe_q = _re.sub(r'[^\w\s]', '', query).strip()
    if not safe_q:
        return []
    # FTS: try AND first (precise), fallback to OR if no hits
    terms = safe_q.split()
    fts_query_and = " AND ".join(terms)
    fts_query_or = " OR ".join(terms)
    rows: list = []
    try:
        async with db.execute("""
            SELECT f.session_id, s.name,
                   snippet(conversations_fts, 0, '<b>', '</b>', '…', 12) AS snippet
            FROM conversations_fts f
            LEFT JOIN sessions s ON s.id = f.session_id
            WHERE conversations_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (fts_query_and, limit)) as cur:
            rows = await cur.fetchall()
        # If AND gave no results and query has multiple terms, try OR for recall
        if not rows and len(terms) > 1:
            async with db.execute("""
                SELECT f.session_id, s.name,
                       snippet(conversations_fts, 0, '<b>', '</b>', '…', 12) AS snippet
                FROM conversations_fts f
                LEFT JOIN sessions s ON s.id = f.session_id
                WHERE conversations_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query_or, limit)) as cur:
                rows = await cur.fetchall()
    except Exception:
        # Fallback: LIKE on raw table (safe_q, escape %/_)
        safe_like = safe_q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        async with db.execute("""
            SELECT DISTINCT c.session_id, s.name, c.content
            FROM conversations c
            LEFT JOIN sessions s ON s.id = c.session_id
            WHERE c.content LIKE ? ESCAPE '\\'
            ORDER BY c.timestamp DESC
            LIMIT ?
        """, (f"%{safe_like}%", limit)) as cur:
            rows = await cur.fetchall()
    seen = set()
    results = []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            results.append({"session_id": r[0], "name": r[1] or "", "snippet": r[2] or ""})

    # Semantic supplement: only for multi-word queries and when FTS is sparse.
    # Single-word exact matches are better served by FTS (semantic gives many
    # false positives for short queries: "omlet" vs "teşekkürler" 0.637).
    # Threshold 0.50 for higher precision (memories uses 0.35, but search needs stricter).
    if len(results) < 5 and len(terms) > 1 and len(results) < limit:
        try:
            from embedding import cosine_similarity, embed_async
            query_emb = await embed_async(safe_q)
            async with db.execute("""
                SELECT c.session_id, s.name, c.content, c.embedding
                FROM conversations c LEFT JOIN sessions s ON s.id = c.session_id
                WHERE c.embedding IS NOT NULL
                ORDER BY c.timestamp DESC LIMIT 200
            """) as cur:
                cand_rows = await cur.fetchall()
            scored: list[tuple[float, str, str, str]] = []
            for sess_id, name, content, blob in cand_rows:
                if not blob or sess_id in seen:
                    continue
                try:
                    sim = cosine_similarity(query_emb, blob)
                except Exception:
                    continue
                if sim >= 0.50:
                    scored.append((sim, sess_id, name or "", content))
            scored.sort(key=lambda x: x[0], reverse=True)
            for sim, sess_id, name, content in scored[: limit - len(results)]:
                if sess_id not in seen:
                    snippet = content[:80].replace("\n", " ").strip() + "…"
                    results.append({"session_id": sess_id, "name": name, "snippet": snippet})
                    seen.add(sess_id)
        except Exception as e:
            logger.warning(f"Semantic search supplement failed (non-fatal): {e}")

    return results


# -- Email list-number → message-ID mapping --
#
# The model sees email lists as "1., 2., ..." and is told never to show raw
# IDs. This table persists the mapping from that list number to the real IMAP
# message ID per session, so a follow-up like "read email 3" keeps resolving
# correctly even after a restart or when a session is resumed later. Rows are
# replaced on every list_emails / search_emails call.

async def save_email_map(session_id: str, emails: list[dict]):
    """Replace the stored email listing for a session with a new one."""
    if not session_id or not emails:
        return
    db = await get_db()
    await _write_with_retry(db, "DELETE FROM email_session_map WHERE session_id = ?", (session_id,))
    for seq, m in enumerate(emails, 1):
        await _write_with_retry(
            db,
            "INSERT INTO email_session_map (session_id, seq, message_id, subject, sender, preview) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                seq,
                str(m.get("id", "")),
                m.get("subject", "")[:200],
                m.get("from", "")[:200],
                (m.get("body", "") or "")[:200],
            ),
        )


async def get_email_map(session_id: str) -> list[dict]:
    """Return the persisted email listing for a session (list-number order)."""
    if not session_id:
        return []
    db = await get_db()
    async with db.execute(
        """SELECT message_id, subject, sender, preview FROM email_session_map
           WHERE session_id = ? ORDER BY seq ASC""",
        (session_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [
        {"id": r[0], "subject": r[1], "from": r[2], "preview": r[3]}
        for r in rows
    ]


async def clear_email_map(session_id: str):
    """Drop the stored email listing for a session (used on history clear)."""
    if not session_id:
        return
    db = await get_db()
    await _write_with_retry(db, "DELETE FROM email_session_map WHERE session_id = ?", (session_id,))


# -- Notes Session Map --
# Same pattern as email_session_map: the model sees numbered note lists
# ("1., 2., ...") and this table maps list positions to real Nextcloud note
# IDs per session, so "read note 3" resolves correctly.

async def save_notes_map(session_id: str, notes: list[dict]):
    """Replace the stored note listing for a session with a new one."""
    if not session_id or not notes:
        return
    db = await get_db()
    await _write_with_retry(db, "DELETE FROM notes_session_map WHERE session_id = ?", (session_id,))
    for seq, n in enumerate(notes, 1):
        await _write_with_retry(
            db,
            "INSERT INTO notes_session_map (session_id, seq, note_id, title, category, preview) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                seq,
                int(n.get("id", 0)),
                n.get("title", "")[:200],
                n.get("category", "")[:100],
                (n.get("content", "") or "")[:200],
            ),
        )


async def get_notes_map(session_id: str) -> list[dict]:
    """Return the persisted note listing for a session (list-number order)."""
    if not session_id:
        return []
    db = await get_db()
    async with db.execute(
        """SELECT note_id, title, category, preview FROM notes_session_map
           WHERE session_id = ? ORDER BY seq ASC""",
        (session_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [
        {"id": r[0], "title": r[1], "category": r[2], "preview": r[3]}
        for r in rows
    ]


async def clear_notes_map(session_id: str):
    """Drop the stored note listing for a session (used on history clear)."""
    if not session_id:
        return
    db = await get_db()
    await _write_with_retry(db, "DELETE FROM notes_session_map WHERE session_id = ?", (session_id,))


# -- Tasks Session Map --
# Same pattern as email/notes: model sees numbered list, we map to real UIDs.

async def save_tasks_map(session_id: str, tasks: list[dict]):
    """Replace the stored task listing for a session with a new one."""
    if not session_id or not tasks:
        return
    db = await get_db()
    await _write_with_retry(db, "DELETE FROM tasks_session_map WHERE session_id = ?", (session_id,))
    for seq, t in enumerate(tasks, 1):
        await _write_with_retry(
            db,
            "INSERT INTO tasks_session_map (session_id, seq, uid, summary, due, priority, completed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                seq,
                str(t.get("uid", "")),
                t.get("summary", "")[:200],
                t.get("due", "")[:50],
                int(t.get("priority", 0)),
                1 if t.get("completed") else 0,
            ),
        )


async def get_tasks_map(session_id: str) -> list[dict]:
    """Return the persisted task listing for a session (list-number order)."""
    if not session_id:
        return []
    db = await get_db()
    async with db.execute(
        """SELECT uid, summary, due, priority, completed FROM tasks_session_map
           WHERE session_id = ? ORDER BY seq ASC""",
        (session_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [
        {"uid": r[0], "summary": r[1], "due": r[2], "priority": r[3], "completed": bool(r[4])}
        for r in rows
    ]


async def clear_tasks_map(session_id: str):
    """Drop the stored task listing for a session (used on history clear)."""
    if not session_id:
        return
    db = await get_db()
    await _write_with_retry(db, "DELETE FROM tasks_session_map WHERE session_id = ?", (session_id,))


# -- Calendar Session Map --
# Same pattern as email/notes/tasks: model sees numbered list, we map to real UIDs.

async def save_calendar_map(session_id: str, events: list[dict]):
    """Replace the stored calendar listing for a session with a new one."""
    if not session_id or not events:
        return
    db = await get_db()
    await _write_with_retry(db, "DELETE FROM calendar_session_map WHERE session_id = ?", (session_id,))
    for seq, ev in enumerate(events, 1):
        await _write_with_retry(
            db,
            "INSERT INTO calendar_session_map (session_id, seq, uid, summary, start_time) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                session_id,
                seq,
                str(ev.get("uid", "")),
                ev.get("summary", "")[:200],
                ev.get("start", "")[:50],
            ),
        )


async def get_calendar_map(session_id: str) -> list[dict]:
    """Return the persisted calendar listing for a session (list-number order)."""
    if not session_id:
        return []
    db = await get_db()
    async with db.execute(
        """SELECT uid, summary, start_time FROM calendar_session_map
           WHERE session_id = ? ORDER BY seq ASC""",
        (session_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [
        {"uid": r[0], "summary": r[1], "start": r[2]}
        for r in rows
    ]


async def clear_calendar_map(session_id: str):
    """Drop the stored calendar listing for a session (used on history clear)."""
    if not session_id:
        return
    db = await get_db()
    await _write_with_retry(db, "DELETE FROM calendar_session_map WHERE session_id = ?", (session_id,))


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
        """SELECT s.id, s.created_at, s.last_active, s.name,
                  COUNT(c.session_id) as msg_count
           FROM sessions s
           LEFT JOIN conversations c ON c.session_id = s.id
           GROUP BY s.id
           ORDER BY s.last_active DESC"""
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
                      importance: int = 5, user_id: str | None = None) -> tuple[str, int]:
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
                return "Memory updated (similar content exists).", mem_id

    cur = await db.execute(
        "INSERT INTO memories (user_id, content, category, importance, embedding) VALUES (?, ?, ?, ?, ?)",
        (user_id, content, category, importance, new_embedding),
    )
    await db.commit()
    rowid = cur.lastrowid
    return "Memory saved.", rowid


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
    # Phase 1: load only IDs + embeddings for fast similarity scoring
    async with db.execute(
        "SELECT id, embedding FROM memories WHERE user_id = ?",
        (user_id,),
    ) as cur:
        rows = await cur.fetchall()

    scored = []
    backfill_ids = []
    for mem_id, blob in rows:
        if blob is None:
            backfill_ids.append(mem_id)
            continue
        sim = cosine_similarity(query_embedding, blob)
        scored.append((sim, mem_id))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [(sim, mid) for sim, mid in scored[:limit] if sim >= 0.35]

    # Phase 2: fetch full content only for top results
    result = []
    if top:
        placeholders = ",".join("?" * len(top))
        ids = [m_id for _, m_id in top]
        async with db.execute(
            f"SELECT id, content, category, importance, created_at FROM memories WHERE id IN ({placeholders})",
            ids,
        ) as cur:
            content_map = {r[0]: r[1:] for r in await cur.fetchall()}
        for sim, mem_id in top:
            c, cat, imp, cat_at = content_map.get(mem_id, ("", "", 0, ""))
            result.append({
                "id": mem_id, "content": c, "category": cat,
                "importance": imp, "created_at": cat_at, "similarity": sim,
            })

    if backfill_ids:
        async def _backfill():
            # Own connection: the shared `db` is mid-writing the caller's
            # search results, and a backfill commit on it would commit the
            # caller's partially-assembled transaction too. WAL allows
            # concurrent writers from a separate connection safely.
            async with _BACKFILL_SEMAPHORE:
                conn = await aiosqlite.connect(DB_PATH)
                try:
                    await conn.execute("PRAGMA busy_timeout=10000")
                    for i in range(0, len(backfill_ids), _BACKFILL_BATCH_SIZE):
                        batch = backfill_ids[i : i + _BACKFILL_BATCH_SIZE]
                        for mid in batch:
                            try:
                                row = await conn.execute("SELECT content FROM memories WHERE id = ?", (mid,))
                                r = await row.fetchone()
                                if r:
                                    emb = await embed_async(r[0])
                                    await conn.execute("UPDATE memories SET embedding = ? WHERE id = ?", (emb, mid))
                            except Exception as e:
                                logger.error("Embedding backfill failed for memory %s: %s", mid, e)
                        await conn.commit()
                        # Small yield between batches to avoid starving the event loop
                        await asyncio.sleep(0.05)
                except asyncio.CancelledError:
                    pass
                finally:
                    await conn.close()

        global _backfill_task
        # Cancel any previous backfill to avoid duplicate work
        if _backfill_task and not _backfill_task.done():
            _backfill_task.cancel()
        _backfill_task = asyncio.create_task(_backfill())

    # Update access stats for retrieved results
    if result:
        ids = [m["id"] for m in result]
        placeholders = ",".join("?" * len(ids))
        await db.execute(
            f"""UPDATE memories SET last_accessed = CURRENT_TIMESTAMP,
               access_count = access_count + 1 WHERE id IN ({placeholders})""",
            ids,
        )

    await _commit_with_retry(db)

    return result


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
    await _commit_with_retry(db)


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
