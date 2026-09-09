"""Collective-learning Phase 3: votes, quorum, reputation, rate cap, freeze."""
import asyncio
import sqlite3

import pytest


@pytest.fixture
def qdb(tmp_path, monkeypatch):
    import db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "q.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


@pytest.fixture
def voters(qdb):
    a, _ = asyncio.run(qdb.create_user("anna", approved=True))
    b, _ = asyncio.run(qdb.create_user("bob", approved=True))
    c, _ = asyncio.run(qdb.create_user("cim", approved=True))
    return qdb, a["id"], b["id"], c["id"]


def test_unapproved_votes_do_not_count_until_approved(voters):
    dbmod, a, b, c = voters
    d, _ = asyncio.run(dbmod.create_user("dora"))  # unapproved
    d = d["id"]
    aid_d = _seed_audit(dbmod, d, session="s9")
    asyncio.run(dbmod.record_feedback_vote(aid_d, d, "correct", "email"))
    sup = asyncio.run(dbmod.get_pattern_support(_sig("Ahmet'e mail at"), "email"))
    assert sup == {"supports": 0, "contradicts": 0}
    asyncio.run(dbmod.set_approved(d, True))
    sup = asyncio.run(dbmod.get_pattern_support(_sig("Ahmet'e mail at"), "email"))
    assert sup == {"supports": 1, "contradicts": 0}


def test_admin_counts_without_approval_flag(voters):
    dbmod, a, _, _ = voters
    r, _ = asyncio.run(dbmod.create_user("root", is_admin=True))
    asyncio.run(dbmod.set_approved(r["id"], False))  # admins count regardless
    aid_r = _seed_audit(dbmod, r["id"], session="s8")
    asyncio.run(dbmod.record_feedback_vote(aid_r, r["id"], "correct", "email"))
    sup = asyncio.run(dbmod.get_pattern_support(_sig("Ahmet'e mail at"), "email"))
    assert sup["supports"] == 1


def _seed_audit(dbmod, uid, text="Ahmet'e mail at", session="s1"):
    asyncio.run(dbmod.save_message(session, "user", text, user_id=uid))
    mid = asyncio.run(dbmod.save_message(session, "assistant", "ok", user_id=uid))
    aid = asyncio.run(dbmod.log_tool_call("send_email", {}, True, user_id=uid))
    asyncio.run(dbmod.link_audits_to_message(mid, [aid]))
    return aid


def test_vote_mirror_and_overwrite(voters):
    dbmod, a, b, _ = voters
    aid = _seed_audit(dbmod, a)
    assert asyncio.run(dbmod.record_feedback_vote(aid, a, "correct", "email")) is True
    assert asyncio.run(dbmod.record_feedback_vote(aid, a, "confirm", "email")) is True
    rows = asyncio.run(_rows(dbmod, "SELECT signal FROM feedback_votes"))
    assert rows == [("confirm",)]  # re-vote overwrites, no duplicate


def test_support_counts_distinct_users(voters):
    dbmod, a, b, c = voters
    aid_a = _seed_audit(dbmod, a, session="s1")
    aid_b = _seed_audit(dbmod, b, session="s2")
    aid_c = _seed_audit(dbmod, c, session="s3")
    asyncio.run(dbmod.record_feedback_vote(aid_a, a, "correct", "email"))
    asyncio.run(dbmod.record_feedback_vote(aid_b, b, "correct", "email"))
    asyncio.run(dbmod.record_feedback_vote(aid_c, c, "correct", "tasks"))
    sup = asyncio.run(dbmod.get_pattern_support(_sig("Ahmet'e mail at"), "email"))
    assert sup == {"supports": 2, "contradicts": 1}


def test_reputation_agreement_rate(voters):
    dbmod, a, b, c = voters
    for uid, sess in ((a, "s1"), (b, "s2"), (c, "s3")):
        aid = _seed_audit(dbmod, uid, session=sess)
        grp = "email" if uid in (a, b) else "tasks"
        asyncio.run(dbmod.record_feedback_vote(aid, uid, "correct", grp))
    assert asyncio.run(dbmod.user_reputation(a)) == 1.0
    assert asyncio.run(dbmod.user_reputation(b)) == 1.0
    assert asyncio.run(dbmod.user_reputation(c)) == 0.0
    assert asyncio.run(dbmod.user_reputation("nobody")) == 1.0  # neutral


def test_daily_cap_counter(voters):
    dbmod, a, _, _ = voters
    assert asyncio.run(dbmod.count_user_votes_today(a)) == 0
    aid = _seed_audit(dbmod, a)
    asyncio.run(dbmod.record_feedback_vote(aid, a, "correct", "email"))
    assert asyncio.run(dbmod.count_user_votes_today(a)) == 1


def test_correction_endpoint_enforces_cap_and_mirrors_vote(voters, monkeypatch):
    import db as dbmod
    from routers.chat import CorrectionRequest, set_tool_correction

    _, a, _, _ = voters
    monkeypatch.setattr(dbmod, "FEEDBACK_DAILY_CAP", 1)
    aid1 = _seed_audit(dbmod, a, session="s1")
    aid2 = _seed_audit(dbmod, a, session="s2")
    req_state = _state(a)
    asyncio.run(set_tool_correction(CorrectionRequest(audit_id=aid1, expected_group="calendar"), req_state))
    assert asyncio.run(_rows(dbmod, "SELECT COUNT(*) FROM feedback_votes")) == [(1,)]
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        asyncio.run(set_tool_correction(CorrectionRequest(audit_id=aid2, expected_group="calendar"), req_state))
    assert e.value.status_code == 429


def test_feeder_freezes_reputable_contradiction(tmp_path):
    import asyncio as _aio

    import corpus_feeder as cf

    db_path = tmp_path / "fz.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE conversations (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, user_id TEXT)")
    conn.execute("CREATE TABLE tool_audit_log (id INTEGER PRIMARY KEY, tool_name TEXT, conversation_id INTEGER, confirmed_at DATETIME, expected_group TEXT, user_id TEXT)")
    conn.execute("CREATE TABLE feedback_votes (audit_id INTEGER, user_id TEXT, signature TEXT, proposed_group TEXT, signal TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(audit_id, user_id))")
    conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY, is_admin INTEGER DEFAULT 0, is_approved INTEGER DEFAULT 0)")
    conn.execute("INSERT INTO users VALUES ('a', 0, 1)")
    conn.execute("INSERT INTO users VALUES ('b', 0, 1)")
    conn.execute("INSERT INTO conversations VALUES (1, 's', 'user', 'Ahmet e mail at', 'a')")
    conn.execute("INSERT INTO conversations VALUES (2, 's', 'assistant', 'ok', 'a')")
    conn.execute("INSERT INTO tool_audit_log VALUES (1, 'send_email', 2, NULL, 'tasks', 'a')")
    sig = _sig("Ahmet e mail at")
    conn.execute("INSERT INTO feedback_votes VALUES (1, 'a', ?, 'tasks', 'correct', datetime('now'))", (sig,))
    conn.execute("INSERT INTO feedback_votes VALUES (9, 'b', ?, 'email', 'correct', datetime('now'))", (sig,))
    conn.commit()
    row = {"id": 1, "tool_name": "send_email", "conversation_id": 2,
           "confirmed_at": None, "expected_group": "tasks"}
    out = _aio.run(cf._process_audit_row(
        row, {"send_email": "email"}, conn, [], None, [], None, dry_run=True))
    assert out["status"] == "frozen_contradiction"
    conn.close()


def _sig(text):
    from textnorm import normalize_signature

    return normalize_signature(text)


def _state(uid):
    from types import SimpleNamespace

    return SimpleNamespace(state=SimpleNamespace(user_id=uid, is_admin=False))


async def _rows(dbmod, sql):
    db = await dbmod.get_db()
    cur = await db.execute(sql)
    return await cur.fetchall()
