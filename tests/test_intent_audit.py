"""Intent audit log: insert, retention purge, fail-safe guarantee."""

import asyncio

import pytest

import db as dbmod
import llm.intent as li_mod


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "iaudit.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


def test_log_intent_audit_writes_row(audit_db):
    asyncio.run(dbmod.log_intent_audit(
        "yarın toplantıya katılacağım not düş", "calendar", 0.53, 0.02, "thin_margin"))
    rows = asyncio.run(_fetch("SELECT message, chosen_group, best_sim, margin, source "
                              "FROM intent_audit_log"))
    assert len(rows) == 1
    msg, grp, sim, marg, src = rows[0]
    assert grp == "calendar" and src == "thin_margin" and abs(marg - 0.02) < 1e-6


async def _fetch(sql):
    db = await dbmod.get_db()
    cur = await db.execute(sql)
    return await cur.fetchall()


def test_purge_deletes_only_old_rows(audit_db):
    from datetime import datetime, timedelta
    old = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
    recent = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def seed():
        db = await dbmod.get_db()
        for ts in (old, recent):
            await db.execute(
                "INSERT INTO intent_audit_log (message, chosen_group, best_sim, margin, source, created_at) "
                "VALUES ('m', 'tasks', 0.6, 0.02, 'thin_margin', ?)", (ts,))
        await db.commit()

    asyncio.run(seed())
    deleted = asyncio.run(dbmod.purge_intent_audit(days=30))
    assert deleted == 1
    left = asyncio.run(_fetch("SELECT created_at FROM intent_audit_log"))
    assert len(left) == 1


def test_classify_keyword_fallback_logs_row(audit_db, monkeypatch):
    monkeypatch.setattr(li_mod, "_tool_embed_cache", [])
    monkeypatch.setattr(li_mod, "get", lambda k, d=None: {"INTENT_LLM_FALLBACK": "off"}.get(k, d))

    result = asyncio.run(li_mod._classify_intent("not düş"))
    assert result == ("action", "notes")

    rows = asyncio.run(_fetch("SELECT source, chosen_group FROM intent_audit_log"))
    assert ("keyword_fallback", "notes") in [tuple(r) for r in rows]


def test_audit_failure_never_breaks_classification(audit_db, monkeypatch):
    import llm.intent as li_mod
    monkeypatch.setattr(li_mod, "_tool_embed_cache", [])
    monkeypatch.setattr(li_mod, "get", lambda k, d=None: {"INTENT_LLM_FALLBACK": "off"}.get(k, d))

    async def broken_log(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(dbmod, "log_intent_audit", broken_log)

    result = asyncio.run(li_mod._classify_intent("not düş"))
    assert result == ("action", "notes")   # sınıflandırma yaşadı
