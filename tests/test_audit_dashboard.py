"""Audit dashboard pack (Phase A, 2026-10-12).

Industry-comparison research (Windmill/ClickHouse/Sysdig/flywheel lessons)
showed our audit export was write-only: retention hardcoded, summaries too
thin (no latency, no per-user), nothing on screen, no alarm. This pack:
  - AUDIT_RETENTION_DAYS config drives the rollup window
  - summary rows carry stats_json (users / duration min-avg-max-p95 /
    verification breakdown) built by the same _build_day_stats the
    dashboard's live aggregation uses
  - GET /admin/audit/overview + /admin/audit/export/{day} make the data
    readable (admin-only; strict day regex blocks traversal)
  - audit_error_alert() checks the 24h error rate across details AND
    summaries (a rolled-up catastrophic day must not vanish from the window)
"""

import asyncio
import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
import db as dbmod


def _client(authenticated=True, is_admin=True):
    """Minimal app with the admin router + a stub auth middleware."""
    from routers.admin import router

    app = FastAPI()
    app.include_router(router)

    @app.middleware("http")
    async def _auth(request, call_next):
        if authenticated:
            request.state.user_id = "admin-uid" if is_admin else "plain-uid"
            request.state.is_admin = is_admin
        return await call_next(request)

    return TestClient(app)


async def _fetch_all(sql, params=()):
    db = await dbmod.get_db()
    cur = await db.execute(sql, params)
    return await cur.fetchall()


# ── _build_day_stats (pure) ───────────────────────────────────────────────────

def test_build_day_stats_groups_tools_users_and_durations():
    rows = [
        ("send_email", "alice", 1, 100.0, "verified"),
        ("send_email", "alice", 0, 300.0, "unverified"),
        ("get_time", "bob", 1, 200.0, None),
        ("get_time", None, 1, None, None),  # NULL user/duration skipped
    ]
    stats = dbmod._build_day_stats(rows)
    assert stats["tools"] == {"send_email": 2, "get_time": 2}
    assert stats["users"]["alice"] == {"total": 2, "success": 1, "error": 1}
    assert stats["users"]["bob"] == {"total": 1, "success": 1, "error": 0}
    assert stats["users"]["unknown"]["total"] == 1  # NULL user_id bucket
    # p95 nearest-rank of [100, 200, 300]: ceil(0.95*3)-1 = 2 → 300
    assert stats["dur_ms"] == {"n": 3, "min": 100.0, "avg": 200.0, "max": 300.0, "p95": 300.0}
    assert stats["verify"] == {"verified": 1, "unverified": 1}  # NULL omitted
    assert stats["success"] == 3


def test_build_day_stats_p95_nearest_rank_and_empty():
    # 20 durations 1..20: ceil(0.95*20)-1 = 18 → the 19th value.
    rows = [("t", "u", 1, float(i), None) for i in range(1, 21)]
    assert dbmod._build_day_stats(rows)["dur_ms"]["p95"] == 19.0
    # Single sample: p95 is the sample itself.
    assert dbmod._build_day_stats([("t", "u", 1, 7.0, None)])["dur_ms"]["p95"] == 7.0
    # No rows / no durations: no min/avg/max keys, n=0.
    assert dbmod._build_day_stats([])["dur_ms"] == {"n": 0}
    only_nulls = dbmod._build_day_stats([("t", "u", 1, None, None)])
    assert only_nulls["dur_ms"] == {"n": 0}
    assert only_nulls["tools"] == {"t": 1}


# ── rollup: rich summary + config retention ──────────────────────────────────

def test_rollup_summary_carries_stats_json():
    async def seed():
        db = await dbmod.get_db()
        await _seed_rows(db)

    asyncio.run(seed())
    assert asyncio.run(dbmod.rollup_tool_audit()) == 1
    rows = asyncio.run(_fetch_all(
        "SELECT tool_breakdown, stats_json FROM tool_audit_log WHERE is_summary = 1"
    ))
    assert len(rows) == 1
    breakdown = json.loads(rows[0][0])
    stats = json.loads(rows[0][1])
    # tool_breakdown stays flat (backward compat), stats_json is the rich one.
    assert breakdown == {"get_time": 2, "send_email": 2}
    assert stats["tools"] == breakdown
    assert stats["users"]["alice"]["total"] == 2
    assert stats["users"]["bob"]["total"] == 2
    assert stats["dur_ms"]["max"] == 350.0
    assert stats["dur_ms"]["p95"] == 350.0
    assert stats["verify"] == {"verified": 1, "verified_by_fallback": 1}


async def _seed_rows(db):
    """One old day, 4 calls, mixed users/durations/verification."""
    day = "2026-07-05 12:00:00"
    for tool, user, success, dur, vstatus in [
        ("get_time", "alice", 1, 10.0, "verified"),
        ("get_time", "bob", 1, 20.0, None),
        ("send_email", "alice", 0, 350.0, "verified_by_fallback"),
        ("send_email", "bob", 1, 30.0, None),
    ]:
        await db.execute(
            "INSERT INTO tool_audit_log "
            "(tool_name, params, success, duration_ms, user_id, verification_status, created_at) "
            "VALUES (?, '{}', ?, ?, ?, ?, ?)",
            (tool, success, dur, user, vstatus, day),
        )
    await db.commit()


def test_rollup_retention_comes_from_config(monkeypatch):
    from datetime import datetime, timedelta
    old = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    db = asyncio.run(dbmod.get_db())
    asyncio.run(_insert_call(db, old))
    # Default 14d: a 5-day-old row stays detailed.
    assert asyncio.run(dbmod.rollup_tool_audit()) == 0
    # Config says 3d: the same row is now old enough to compress.
    monkeypatch.setattr(config, "AUDIT_RETENTION_DAYS", 3)
    assert asyncio.run(dbmod.rollup_tool_audit()) == 1


async def _insert_call(db, created_at):
    await db.execute(
        "INSERT INTO tool_audit_log (tool_name, params, success, created_at) "
        "VALUES ('get_time', '{}', 1, ?)",
        (created_at,),
    )
    await db.commit()


# ── get_audit_overview ───────────────────────────────────────────────────────

def test_overview_merges_summary_and_live_days():
    async def seed():
        db = await dbmod.get_db()
        await _seed_rows(db)

    asyncio.run(seed())
    asyncio.run(dbmod.rollup_tool_audit())  # 2026-07-05 → summary

    # A live (recent) day that must NOT be rolled up.
    db = asyncio.run(dbmod.get_db())
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    asyncio.run(_insert_call(db, now))

    overview = asyncio.run(dbmod.get_audit_overview(days=30))
    days = overview["days"]
    assert [d["day"] for d in days] == sorted(
        [d["day"] for d in days], reverse=True
    )  # newest first
    by_day = {d["day"]: d for d in days}
    live_day = now[:10]
    rolled_day = "2026-07-05"
    assert rolled_day in by_day and live_day in by_day
    assert by_day[rolled_day]["source"] == "summary"
    assert by_day[rolled_day]["total"] == 4
    assert by_day[rolled_day]["dur_ms"]["p95"] == 350.0
    assert by_day[rolled_day]["users"]["alice"]["total"] == 2
    assert by_day[live_day]["source"] == "detail"
    assert by_day[live_day]["total"] == 1
    assert by_day[live_day]["error_rate"] == 0.0
    assert overview["retention_days"] == 30


def test_overview_legacy_summary_without_stats_json_parses():
    # Pre-upgrade summary rows have tool_breakdown but NULL stats_json.
    db = asyncio.run(dbmod.get_db())
    asyncio.run(db.execute(
        "INSERT INTO tool_audit_log "
        "(is_summary, day, total_calls, success_count, error_count, "
        " tool_breakdown, tool_name, success, created_at) "
        "VALUES (1, '2026-01-01', 5, 3, 2, '{\"get_time\": 5}', 'rollup', 1, '2026-01-01')",
    ))
    asyncio.run(db.commit())
    overview = asyncio.run(dbmod.get_audit_overview(days=3650))
    (d,) = overview["days"]
    assert d["tools"] == {"get_time": 5}  # falls back to tool_breakdown
    assert d["users"] == {} and d["dur_ms"] == {} and d["verify"] == {}
    assert d["error_rate"] == 0.4


def test_overview_never_raises_when_db_fails(monkeypatch):
    async def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(dbmod, "get_db", _boom)
    overview = asyncio.run(dbmod.get_audit_overview())
    assert overview["days"] == [] and overview["retention_days"] == 14


# ── audit_error_alert ────────────────────────────────────────────────────────

def test_alert_breaches_on_failing_details():
    db = asyncio.run(dbmod.get_db())
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for i in range(10):
        asyncio.run(_insert_call_fail(db, now))
    asyncio.run(_insert_call(db, now))
    alert = asyncio.run(dbmod.audit_error_alert())
    assert alert["total"] == 11 and alert["errors"] == 10
    assert alert["error_rate"] == pytest.approx(10 / 11, abs=1e-3)
    assert alert["breached"] is True


async def _insert_call_fail(db, created_at):
    await db.execute(
        "INSERT INTO tool_audit_log (tool_name, params, success, error, created_at) "
        "VALUES ('send_mail', '{}', 0, 'SMTP refused', ?)",
        (created_at,),
    )
    await db.commit()


def test_alert_stays_calm_below_min_calls():
    db = asyncio.run(dbmod.get_db())
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for _ in range(3):  # 100% error, but only 3 calls — noise, not signal
        asyncio.run(_insert_call_fail(db, now))
    alert = asyncio.run(dbmod.audit_error_alert())
    assert alert["total"] == 3 and alert["breached"] is False


def test_alert_counts_summaries_so_rolled_up_days_stay_visible():
    db = asyncio.run(dbmod.get_db())
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    asyncio.run(db.execute(
        "INSERT INTO tool_audit_log "
        "(is_summary, day, total_calls, success_count, error_count, "
        " tool_name, success, created_at) "
        "VALUES (1, ?, 50, 10, 40, 'rollup', 1, ?)",
        (today, today),
    ))
    asyncio.run(db.commit())
    alert = asyncio.run(dbmod.audit_error_alert())
    assert alert["total"] == 50 and alert["errors"] == 40
    assert alert["breached"] is True  # details are empty; the summary still speaks


def test_alert_disabled_when_threshold_zero(monkeypatch):
    db = asyncio.run(dbmod.get_db())
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for _ in range(10):
        asyncio.run(_insert_call_fail(db, now))
    monkeypatch.setattr(config, "AUDIT_ERROR_RATE_ALERT", 0.0)
    alert = asyncio.run(dbmod.audit_error_alert())
    assert alert["breached"] is False and alert["threshold"] == 0.0


def test_alert_never_raises_when_db_fails(monkeypatch):
    async def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(dbmod, "get_db", _boom)
    alert = asyncio.run(dbmod.audit_error_alert())
    assert alert["breached"] is False and alert["total"] == 0


# ── admin endpoints ──────────────────────────────────────────────────────────

def test_overview_endpoint_requires_auth():
    resp = _client(authenticated=False).get("/admin/audit/overview")
    assert resp.status_code == 401


def test_overview_endpoint_requires_admin():
    resp = _client(is_admin=False).get("/admin/audit/overview")
    assert resp.status_code == 403


def test_overview_endpoint_returns_days_alert_and_clamps_days():
    db = asyncio.run(dbmod.get_db())
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    asyncio.run(_insert_call(db, now))

    client = _client()
    resp = client.get("/admin/audit/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["days"]) == 1 and body["days"][0]["source"] == "detail"
    assert "alert" in body and body["alert"]["breached"] is False

    # days=0 falls back to config; huge values clamp to 3650.
    assert client.get("/admin/audit/overview?days=0").json()["window_days"] == 14
    assert client.get("/admin/audit/overview?days=99999").json()["window_days"] == 3650
    assert client.get("/admin/audit/overview?days=-5").json()["window_days"] == 1


def test_export_endpoint_serves_csv_for_archived_day(tmp_path):
    outdir = dbmod.audit_export_dir()
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "tool-audit-2026-07-05.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("id,tool_name\n1,get_time\n")

    resp = _client().get("/admin/audit/export/2026-07-05")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "tool-audit-2026-07-05.csv" in resp.headers["content-disposition"]
    assert resp.text == "id,tool_name\n1,get_time\n"


def test_export_endpoint_404s_on_missing_or_malformed_day():
    client = _client()
    assert client.get("/admin/audit/export/2026-07-05").status_code == 404
    assert client.get("/admin/audit/export/not-a-day").status_code == 404
    assert client.get("/admin/audit/export/2026-13-99").status_code == 404


def test_export_endpoint_blocks_path_traversal():
    client = _client()
    # Encoded traversal reaches the handler decoded; the strict day regex
    # must reject it before any filesystem path is built.
    resp = client.get("/admin/audit/export/..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code == 404
    resp = client.get("/admin/audit/export/%2e%2e%2fsecrets.env")
    assert resp.status_code == 404


def test_export_endpoint_requires_admin(tmp_path):
    outdir = dbmod.audit_export_dir()
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "tool-audit-2026-07-05.csv"), "w") as f:
        f.write("x\n")
    assert _client(authenticated=False).get("/admin/audit/export/2026-07-05").status_code == 401
    assert _client(is_admin=False).get("/admin/audit/export/2026-07-05").status_code == 403
