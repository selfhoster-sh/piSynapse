"""Audit flywheel pack (Phase C, 2026-10-16).

Closes the correction loop mined by corpus_feeder:
  - deterministic holdout split (sha256(signature) % 10 → ~10% eval) written
    by the feeder, EXCLUDED from live intent routing so the eval set stays
    an honest test set (never trains what it measures)
  - sandboxed weekly automation: periodic_feeder_loop spawns corpus_feeder.py
    as its own process (event-loop safety, crash containment, timeout kill)
  - weekly failure digest: clustered error report (digits stripped so
    "timeout after 12s"/"timeout after 40s" count once) for the human review
    half of the flywheel — surfaced in /admin/audit/overview + weekly log
"""

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
import corpus_feeder as cf
import db as dbmod
import llm.intent as intentmod
import main as mainmod


# ── deterministic split (pure) ────────────────────────────────────────────────

def test_deterministic_split_is_stable_per_signature():
    for i in range(50):
        sig = f"message-{i}-stable"
        first = cf._deterministic_split(sig)
        assert first in ("train", "eval")
        assert cf._deterministic_split(sig) == first  # re-runs never reshuffle


def test_deterministic_split_distribution_around_ten_percent():
    rows = [cf._deterministic_split(f"sig-{i}") for i in range(1000)]
    evals = rows.count("eval")
    # binomial(1000, 0.1) σ≈9.5; ±40 is ~4σ — catches a broken modulo/entropy.
    assert 60 <= evals <= 140
    assert rows.count("train") == 1000 - evals


def test_error_cluster_key_strips_digits_but_keeps_shape():
    assert dbmod._error_cluster_key("timeout after 12s") == \
        dbmod._error_cluster_key("timeout after 40s")
    assert dbmod._error_cluster_key("ECONNREFUSED 192.0.2.5") == \
        dbmod._error_cluster_key("ECONNREFUSED 198.51.100.20")
    assert dbmod._error_cluster_key("timeout after 12s") != \
        dbmod._error_cluster_key("permission denied")
    assert dbmod._error_cluster_key("") == ""


# ── feeder writes the split field ─────────────────────────────────────────────

def _seed_audit_db(conn):
    conn.execute("""
        CREATE TABLE tool_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL, params TEXT, success INTEGER NOT NULL,
            duration_ms REAL, error TEXT, is_summary INTEGER NOT NULL DEFAULT 0,
            day TEXT, total_calls INTEGER, success_count INTEGER,
            error_count INTEGER, tool_breakdown TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expected_tool TEXT, corrected_at DATETIME,
            expected_group TEXT, verification_status TEXT,
            confirmed_at DATETIME, conversation_id INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL, role TEXT NOT NULL,
            content TEXT, images TEXT, reasoning TEXT,
            embedding BLOB, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


@pytest.fixture
def audit_db(tmp_path):
    import sqlite3
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    _seed_audit_db(conn)
    conn.close()
    return db_path


@pytest.fixture
def corpus_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "DATA_DIR", tmp_path / "corpus_data")
    monkeypatch.setattr(cf, "STATE_FILE", tmp_path / "corpus_data" / "state.json")
    monkeypatch.setattr(cf, "ADDITIONS_FILE", tmp_path / "corpus_data" / "additions.jsonl")
    monkeypatch.setattr(cf, "EMBEDDINGS_FILE", tmp_path / "corpus_data" / "additions_embeddings.npy")
    monkeypatch.setattr(cf, "PENDING_REVIEW_FILE", tmp_path / "corpus_data" / "pending_review.json")
    monkeypatch.setattr(cf, "GENUINELY_AMBIGUOUS_FILE", tmp_path / "corpus_data" / "genuinely_ambiguous.json")
    (tmp_path / "corpus_data").mkdir(exist_ok=True)
    return tmp_path / "corpus_data"


def test_feeder_addition_records_split(audit_db, corpus_data_dir, monkeypatch):
    """A positive addition must carry the deterministic split field."""
    import sqlite3
    import numpy as np

    conn = sqlite3.connect(audit_db)
    conn.execute("INSERT INTO conversations (id, session_id, role, content) "
                 "VALUES (1, 't', 'user', 'hava durumu nasıl')")
    conn.execute("INSERT INTO conversations (id, session_id, role, content) "
                 "VALUES (2, 't', 'assistant', 'İşte sonuçlar: 1. deneme')")
    conn.execute("""INSERT INTO tool_audit_log
                    (tool_name, conversation_id, confirmed_at, success)
                    VALUES ('get_weather', 2, '2026-08-31T12:00:00', 1)""")
    conn.commit()
    conn.close()

    def _fake_embed(text):
        rng = np.random.RandomState(hash(text) % (2 ** 31))
        vec = rng.randn(384).astype("float32")
        return (vec / (np.linalg.norm(vec) + 1e-9)).tobytes()

    async def _fake_base():
        return (["weather"], np.array([_fake_embed("weather")]))

    monkeypatch.setattr(cf, "_load_base_corpus_embeddings", _fake_base)
    monkeypatch.setattr(cf, "_load_addition_embeddings", lambda: ([], None))
    monkeypatch.setattr(cf, "_is_duplicate", lambda *a, **kw: False)
    monkeypatch.setattr(cf, "_check_conflict", lambda *a, **kw: None)
    import tools.definitions as td
    monkeypatch.setattr(td, "TOOL_TO_GROUP", {"get_weather": "weather"})
    import embedding as emb
    monkeypatch.setattr(emb, "embed", _fake_embed)

    summary = asyncio.run(cf.run(db_path=audit_db))
    assert summary["added"] == 1

    additions = cf._load_jsonl(cf.ADDITIONS_FILE)
    assert len(additions) == 1
    rec = additions[0]
    assert rec["split"] in ("train", "eval")
    assert rec["split"] == cf._deterministic_split(rec["signature"])
    assert rec["audit_id"] == 1


# ── live routing excludes eval rows ───────────────────────────────────────────

def test_additional_corpus_skips_eval_keeps_train_and_legacy(tmp_path, monkeypatch):
    path = tmp_path / "additions.jsonl"
    rows = [
        {"text": "train example", "group": "notes", "split": "train"},
        {"text": "eval example", "group": "notes", "split": "eval"},
        {"text": "legacy example", "group": "weather"},  # pre-split era: train
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(intentmod, "_ADDITIONS_PATH", path)

    out = intentmod._additional_corpus()
    texts = [t for _, t in out]
    assert "train example" in texts
    assert "legacy example" in texts
    assert "eval example" not in texts  # held out from live routing


def test_additional_corpus_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(intentmod, "_ADDITIONS_PATH", tmp_path / "absent.jsonl")
    assert intentmod._additional_corpus() == []


# ── periodic feeder loop (timer logic, mocked time) ───────────────────────────

def test_feeder_loop_sleeps_first_then_runs(monkeypatch):
    slept, ran = [], []

    async def fake_sleep(hours):
        slept.append(hours)
        if len(slept) == 2:
            raise asyncio.CancelledError

    async def fake_run():
        ran.append(1)
        return True, "ok tail"

    async def go():
        await mainmod.periodic_feeder_loop(interval_hours=24, run_feeder=fake_run,
                                           sleep=fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(go())

    assert slept == [24 * 3600, 24 * 3600]  # full interval per cycle
    assert ran == [1]  # ran once after the first sleep, not at startup


def test_feeder_loop_retries_after_error(monkeypatch):
    attempts, slept = [], []

    async def failing_run():
        attempts.append(1)
        raise RuntimeError("model server hung")

    async def fake_sleep(hours):
        slept.append(hours)
        if len(slept) == 3:
            raise asyncio.CancelledError

    async def go():
        await mainmod.periodic_feeder_loop(interval_hours=1, run_feeder=failing_run,
                                           sleep=fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(go())

    assert attempts == [1, 1]  # both failures logged, loop survived


def test_feeder_loop_reports_failed_subprocess_without_raising(monkeypatch):
    slept, ran = [], []

    async def fake_sleep(hours):
        slept.append(hours)
        if len(slept) == 2:
            raise asyncio.CancelledError

    async def fake_run():
        ran.append(1)
        return False, "Traceback: boom"  # non-zero exit, tail captured

    async def go():
        await mainmod.periodic_feeder_loop(interval_hours=1, run_feeder=fake_run,
                                           sleep=fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(go())

    assert ran == [1]  # warning logged, loop continued


def test_feeder_loop_disabled_by_zero_config(monkeypatch):
    """FEEDER_AUTO_INTERVAL_HOURS=0 must keep the loop from starting in lifespan;
    the loop itself defaults to weekly when interval_hours is None."""
    monkeypatch.setattr(config, "FEEDER_AUTO_INTERVAL_HOURS", 0)
    slept = []

    async def fake_sleep(hours):
        slept.append(hours)
        raise asyncio.CancelledError

    async def go():
        await mainmod.periodic_feeder_loop(interval_hours=None,
                                           run_feeder=None, sleep=fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(go())

    # interval_hours resolved from config (0 → 168h weekly fallback)
    assert slept == [168 * 3600]


# ── failure digest ────────────────────────────────────────────────────────────

async def _seed_audit(*rows):
    db = await dbmod.get_db()
    for r in rows:
        await db.execute(
            """INSERT INTO tool_audit_log
               (tool_name, success, error, expected_group, confirmed_at,
                verification_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (r["tool"], r.get("success", 1), r.get("error"),
             r.get("expected_group"), r.get("confirmed_at"),
             r.get("verify"), r.get("created_at", "2026-10-16T00:00:00")),
        )
    await db.commit()


def test_failure_digest_clusters_and_counts(monkeypatch):
    asyncio.run(_seed_audit(
        {"tool": "get_weather", "success": 0, "error": "timeout after 12s"},
        {"tool": "get_weather", "success": 0, "error": "timeout after 40s"},
        {"tool": "send_email", "success": 0, "error": "SMTP 550 rejected"},
        {"tool": "send_email", "success": 0, "error": "SMTP 550 rejected",
         "expected_group": "email", "confirmed_at": "2026-10-15T10:00:00",
         "verify": "verification_failed"},
        {"tool": "list_notes", "success": 1},
    ))
    dg = asyncio.run(dbmod.audit_failure_digest(days=7))

    assert dg["total_calls"] == 5
    assert dg["errors"] == 4  # 4 failures, 1 success
    assert dg["corrections"] == 1
    assert dg["confirmations"] == 1
    assert dg["verify_failed"] == 1
    # digit variants merged into one cluster
    by_err = {e["error"]: e["count"] for e in dg["top_errors"]}
    assert by_err[dbmod._error_cluster_key("timeout after 12s")] == 2
    assert by_err[dbmod._error_cluster_key("SMTP 550 rejected")] == 2
    # top tools sorted by error count
    assert dg["top_tools"][0]["tool"] == "get_weather"
    assert dg["top_tools"][0]["errors"] == 2
    assert dg["top_tools"][0]["total"] == 2


def test_failure_digest_respects_window_and_never_raises(monkeypatch):
    asyncio.run(_seed_audit(
        {"tool": "get_weather", "success": 0, "error": "old failure",
         "created_at": "2026-01-01T00:00:00"},
        {"tool": "get_weather", "success": 0, "error": "fresh failure",
         "created_at": "2099-01-01T00:00:00"},  # future-proof: inside window
    ))
    dg = asyncio.run(dbmod.audit_failure_digest(days=7))
    assert dg["errors"] == 1  # the 2026-01-01 row is outside the window
    assert dbmod._error_cluster_key("fresh failure") in \
        {e["error"] for e in dg["top_errors"]}

    async def boom():
        raise RuntimeError("db locked")
    monkeypatch.setattr(dbmod, "get_db", boom)
    dg2 = asyncio.run(dbmod.audit_failure_digest(days=7))
    assert dg2["total_calls"] == 0 and dg2["top_errors"] == []  # degrades, no raise


# ── overview endpoint carries the digest ──────────────────────────────────────

def _client():
    from routers.admin import router
    app = FastAPI()
    app.include_router(router)

    @app.middleware("http")
    async def _auth(request, call_next):
        request.state.user_id = "admin-uid"
        request.state.is_admin = True
        return await call_next(request)

    return TestClient(app)


def test_overview_includes_digest():
    asyncio.run(_seed_audit(
        {"tool": "get_weather", "success": 0, "error": "timeout after 12s"},
    ))
    payload = _client().get("/admin/audit/overview?days=7").json()
    assert "digest" in payload
    assert payload["digest"]["errors"] == 1
    assert payload["digest"]["window_days"] == 7


# ── config wiring ─────────────────────────────────────────────────────────────

def test_feeder_interval_config_defaults_and_settings_entry():
    assert config.FEEDER_AUTO_INTERVAL_HOURS == 168
    entry = config.SETTINGS_SCHEMA["FEEDER_AUTO_INTERVAL_HOURS"]
    assert entry["default"] == "168" and entry["type"] == "int"
    assert entry["min"] == 0
    assert "tr" in entry["label"] and "en" in entry["label"]
    assert "FEEDER_AUTO_INTERVAL_HOURS" in config._NUMERIC_KEYS
