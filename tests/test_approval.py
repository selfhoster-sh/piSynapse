"""Quorum approval flag + pattern decisions (collective learning Phase 4 backend)."""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import db as dbmod
import main as mainmod


@pytest.fixture
def adb(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "adb.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    dbmod.invalidate_user_cache()
    yield dbmod
    asyncio.run(dbmod.close_db())


def test_migration_backfill_grandfathers_existing_users(adb, tmp_path, monkeypatch):
    # Simulate a v21 DB: drop the new column, rewind, plant users.
    asyncio.run(dbmod.close_db())
    import sqlite3

    raw = sqlite3.connect(str(tmp_path / "adb.db"))
    raw.execute("ALTER TABLE users DROP COLUMN is_approved")
    raw.execute(f"PRAGMA user_version = {len(dbmod.MIGRATIONS) - 1}")
    raw.execute("INSERT INTO users (id, name, key_hash, is_admin) VALUES ('old', 'old', 'h', 0)")
    raw.commit()
    raw.close()
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "adb.db"))
    asyncio.run(dbmod.init_db())
    assert asyncio.run(dbmod.get_user("old"))["is_approved"] is True
    assert asyncio.run(_version()) == len(dbmod.MIGRATIONS)


async def _version():
    db = await dbmod.get_db()
    cur = await db.execute("PRAGMA user_version")
    return (await cur.fetchone())[0]


def test_create_user_approval_defaults(adb):
    plain, _ = asyncio.run(dbmod.create_user("plain"))
    assert plain["is_approved"] is False
    admin, _ = asyncio.run(dbmod.create_user("root", is_admin=True))
    assert admin["is_approved"] is True
    expl, _ = asyncio.run(dbmod.create_user("exp", approved=True))
    assert expl["is_approved"] is True
    assert asyncio.run(dbmod.set_approved(plain["id"], True)) is True
    assert asyncio.run(dbmod.get_user(plain["id"]))["is_approved"] is True
    assert asyncio.run(dbmod.set_approved("ghost", True)) is False


@pytest.fixture
def admin_api(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "adm.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    dbmod.invalidate_user_cache()
    app = FastAPI()
    app.middleware("http")(mainmod.security_middleware)
    from routers.admin import router as admin_router
    from routers.users import router as users_router

    app.include_router(users_router)
    app.include_router(admin_router)
    client = TestClient(app, base_url="http://localhost")
    admin, admin_key = asyncio.run(dbmod.create_user("root", is_admin=True))
    user, _ = asyncio.run(dbmod.create_user("pleb"))
    yield client, admin_key, admin["id"], user["id"]
    asyncio.run(dbmod.close_db())


def test_approve_unapprove_endpoints(admin_api):
    client, key, _, uid = admin_api
    h = {"x-api-key": key}
    assert client.post(f"/users/{uid}/approve", headers=h).json()["is_approved"] is True
    assert client.post(f"/users/{uid}/unapprove", headers=h).json()["is_approved"] is False
    assert client.post("/users/ghost/approve", headers=h).status_code == 404
    assert client.post(f"/users/{uid}/approve").status_code == 401


def test_pattern_decision_endpoints_and_queue(admin_api):
    client, key, _, _ = admin_api
    h = {"x-api-key": key}
    assert client.get("/admin/patterns/review", headers=h).json() == {"patterns": []}
    body = client.post("/admin/patterns/approve", headers=h,
                       json={"signature": "s1", "group": "email"}).json()
    assert body["status"] == "approved"
    decs = client.get("/admin/patterns/decisions", headers=h).json()["decisions"]
    assert decs[0]["signature"] == "s1" and decs[0]["status"] == "approved"
    body = client.post("/admin/patterns/reject", headers=h,
                       json={"signature": "s1", "group": "email"}).json()
    assert body["status"] == "rejected"
    assert client.get("/admin/patterns/review").status_code == 401


def test_review_queue_lists_frozen_candidate(admin_api):
    import db as _db

    client, key, _, _ = admin_api
    h = {"x-api-key": key}
    a, _ = asyncio.run(_db.create_user("anna", approved=True))
    b, _ = asyncio.run(_db.create_user("bob", approved=True))
    for uid, sess, grp in ((a["id"], "s1", "email"), (b["id"], "s2", "tasks")):
        asyncio.run(_db.save_message(sess, "user", "Ahmet e mail at", user_id=uid))
        mid = asyncio.run(_db.save_message(sess, "assistant", "ok", user_id=uid))
        aid = asyncio.run(_db.log_tool_call("send_email", {}, True, user_id=uid))
        asyncio.run(_db.link_audits_to_message(mid, [aid]))
        asyncio.run(_db.record_feedback_vote(aid, uid, "correct", grp))
    queue = client.get("/admin/patterns/review", headers=h).json()["patterns"]
    assert len(queue) == 1
    assert queue[0]["groups"] and queue[0]["signature"]


def test_feeder_honors_admin_decision(tmp_path):
    import asyncio as _aio
    import sqlite3

    import corpus_feeder as cf

    sig = _sig("Ahmet e mail at")
    db_path = tmp_path / "dec.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE conversations (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, user_id TEXT)")
    conn.execute("CREATE TABLE tool_audit_log (id INTEGER PRIMARY KEY, tool_name TEXT, conversation_id INTEGER, confirmed_at DATETIME, expected_group TEXT, user_id TEXT)")
    conn.execute("CREATE TABLE feedback_votes (audit_id INTEGER, user_id TEXT, signature TEXT, proposed_group TEXT, signal TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(audit_id, user_id))")
    conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY, is_admin INTEGER DEFAULT 0, is_approved INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE pattern_approvals (signature TEXT PRIMARY KEY, proposed_group TEXT, status TEXT, decided_by TEXT, decided_at DATETIME)")
    conn.execute("INSERT INTO conversations VALUES (1, 's', 'user', 'Ahmet e mail at', 'a')")
    conn.execute("INSERT INTO conversations VALUES (2, 's', 'assistant', 'ok', 'a')")
    conn.execute("INSERT INTO tool_audit_log VALUES (1, 'send_email', 2, NULL, 'tasks', 'a')")
    conn.execute("INSERT INTO users VALUES ('a', 0, 1)")
    conn.execute("INSERT INTO users VALUES ('b', 0, 1)")
    conn.execute("INSERT INTO feedback_votes VALUES (1, 'a', ?, 'tasks', 'correct', datetime('now'))", (sig,))
    conn.execute("INSERT INTO feedback_votes VALUES (9, 'b', ?, 'email', 'correct', datetime('now'))", (sig,))
    conn.commit()
    row = {"id": 1, "tool_name": "send_email", "conversation_id": 2,
           "confirmed_at": None, "expected_group": "tasks"}
    kwargs = dict(tool_to_group={"send_email": "email"}, conn=conn, base_groups=[],
                  base_matrix=None, existing_additions=[], addition_matrix=None, dry_run=True)
    # Rejected → skipped before any vote/embedding work.
    conn.execute("INSERT INTO pattern_approvals VALUES (?, 'tasks', 'rejected', 'root', datetime('now'))", (sig,))
    conn.commit()
    assert _aio.run(cf._process_audit_row(row, **kwargs))["status"] == "skip_admin_rejected"
    # Approved → freeze waived despite the reputable contradiction; the
    # pre-seeded matching addition takes the signature-dup exit (no embedding).
    conn.execute("UPDATE pattern_approvals SET status = 'approved' WHERE signature = ?", (sig,))
    conn.commit()
    kwargs["existing_additions"] = [{"text": "Ahmet e mail at", "signature": sig, "group": "tasks"}]
    assert _aio.run(cf._process_audit_row(row, **kwargs))["status"] == "skip_duplicate"
    conn.close()


def _sig(text):
    from textnorm import normalize_signature

    return normalize_signature(text)
