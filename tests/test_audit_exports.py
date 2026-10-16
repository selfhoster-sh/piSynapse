"""Audit archive-integrity pack (Phase B, 2026-10-12).

Industry comparison (orboto: manifest+hash-chain; Invoance: formula-injection
guard + determinism; Windmill: exports are the durable copy; Metis:
byte-identical re-exports) showed our CSV archive was unverifiable and
CSV-only. Phase B:

  - B1: every archived day ships a ``tool-audit-<day>.manifest.json``
    (sha256 + bytes per file, written LAST — its presence marks a COMPLETE
    archive; a crash before it is the detectable gap). ``verify_audit_export``
    re-hashes files against the manifest.
  - B2: NDJSON.gz sibling format (one JSON object per line, key order fixed
    by the column list, gzip mtime=0 → byte-deterministic); CSV gets the
    OWASP formula-injection guard ('=', '+', '@', TAB, CR — '-' deliberately
    kept so negatives survive); export query ORDER BY id.
  - B3: ``AUDIT_ARCHIVE_RETENTION_DAYS`` (default 0 = forever) prunes csv +
    ndjson.gz + manifest together; the archive is the only full-detail copy
    after a rollup, so it no longer dies with conversation retention.
"""

import asyncio
import gzip
import hashlib
import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
import db as dbmod


def _client(authenticated=True, is_admin=True):
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


async def _seed_old_day(day="2026-07-05", n=3):
    db = await dbmod.get_db()
    for i in range(n):
        await db.execute(
            "INSERT INTO tool_audit_log (tool_name, params, success, duration_ms, created_at) "
            "VALUES (?, '{}', ?, ?, ?)",
            ("get_time", 1 if i % 2 == 0 else 0, 10.0 + i, f"{day} 12:00:0{i}"),
        )
    await db.commit()


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _outdir():
    return dbmod.audit_export_dir()


# ── rollup produces the full artefact set ────────────────────────────────────

def test_rollup_writes_csv_ndjson_and_manifest():
    asyncio.run(_seed_old_day())
    assert asyncio.run(dbmod.rollup_tool_audit()) == 1

    out = _outdir()
    day = "2026-07-05"
    csv_p = os.path.join(out, f"tool-audit-{day}.csv")
    ndjson_p = os.path.join(out, f"tool-audit-{day}.ndjson.gz")
    manifest_p = os.path.join(out, f"tool-audit-{day}.manifest.json")
    for p in (csv_p, ndjson_p, manifest_p):
        assert os.path.isfile(p), p

    with open(manifest_p, encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["format"] == "pisynapse-audit-export" and manifest["version"] == 1
    assert manifest["day"] == day
    assert set(manifest["files"]) == {
        f"tool-audit-{day}.csv", f"tool-audit-{day}.ndjson.gz"}
    assert manifest["files"][f"tool-audit-{day}.csv"]["sha256"] == _sha(csv_p)
    assert manifest["files"][f"tool-audit-{day}.ndjson.gz"]["sha256"] == _sha(ndjson_p)
    assert manifest["files"][f"tool-audit-{day}.csv"]["bytes"] == os.path.getsize(csv_p)


# ── determinism ──────────────────────────────────────────────────────────────

def _export_rows():
    # 20 values matching AUDIT_EXPORT_COLUMNS order.
    return [
        (1, "get_time", "{}", 1, 10.0, None, 0, None, None, None, None,
         None, "2026-07-05 12:00:00", None, None, None, None, None, None, "s1"),
        (2, "send_email", "{}", 0, 99.9, "boom", 0, None, None, None, None,
         None, "2026-07-05 12:00:01", None, None, None, None, None, None, "s1"),
    ]


def test_exports_are_byte_deterministic():
    rows = _export_rows()
    day = "2026-07-05"
    dbmod._write_audit_exports(day, rows)
    first = {
        name: _sha(os.path.join(_outdir(), name))
        for name in (f"tool-audit-{day}.csv", f"tool-audit-{day}.ndjson.gz")
    }
    dbmod._write_audit_exports(day, rows)  # re-export, same rows
    second = {
        name: _sha(os.path.join(_outdir(), name))
        for name in first
    }
    assert first == second  # csv AND gzip bytes identical across runs


def test_ndjson_lines_parse_to_column_dicts():
    day = "2026-07-05"
    dbmod._write_audit_exports(day, _export_rows())
    p = os.path.join(_outdir(), f"tool-audit-{day}.ndjson.gz")
    with gzip.open(p, "rt", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 2
    assert list(lines[0].keys()) == dbmod.AUDIT_EXPORT_COLUMNS
    assert lines[0]["tool_name"] == "get_time" and lines[1]["error"] == "boom"


# ── CSV formula-injection guard ──────────────────────────────────────────────

def test_csv_formula_injection_guarded_but_numbers_survive():
    day = "2026-07-05"
    rows = [
        # error column carries an executable formula (the realistic vector:
        # free-text tool errors); duration is negative-ish to prove '-' stays.
        (1, "get_time", '{"x": "=SUM(A1)"}', 0, -5.0, "=cmd|'/c calc'!A0", 0,
         None, None, None, None, None, "2026-07-05 12:00:00", None, None,
         None, None, None, None, None),
    ]
    dbmod._write_audit_csv(day, rows)
    with open(os.path.join(_outdir(), f"tool-audit-{day}.csv"),
              encoding="utf-8") as f:
        content = f.read()
    assert "'=cmd|'/c calc'!A0" in content  # guarded with leading apostrophe
    assert "-5.0" in content  # '-' NOT mangled: negatives stay numbers
    assert "=SUM(A1)" in content  # params JSON preserved (csv handles quoting)


# ── verify ───────────────────────────────────────────────────────────────────

def test_verify_detects_intact_and_tampered_archives():
    asyncio.run(_seed_old_day())
    asyncio.run(dbmod.rollup_tool_audit())
    day = "2026-07-05"

    ok = asyncio.run(dbmod.verify_audit_export(day))
    assert ok["exists"] and ok["ok"]
    assert all(f["sha256_ok"] and f["bytes_ok"] for f in ok["files"].values())

    # Tamper with the CSV: bytes change, manifest does not.
    csv_p = os.path.join(_outdir(), f"tool-audit-{day}.csv")
    with open(csv_p, "a", encoding="utf-8") as f:
        f.write("999,evil\n")
    bad = asyncio.run(dbmod.verify_audit_export(day))
    assert bad["exists"] and not bad["ok"]
    assert bad["files"][f"tool-audit-{day}.csv"]["sha256_ok"] is False
    assert bad["files"][f"tool-audit-{day}.ndjson.gz"]["sha256_ok"] is True


def test_verify_handles_missing_and_corrupt_manifest():
    # Never-archived day.
    r = asyncio.run(dbmod.verify_audit_export("2026-07-05"))
    assert r == {"day": "2026-07-05", "exists": False, "ok": False, "files": {}}
    # Corrupt manifest: never raises, reports not-ok.
    out = _outdir()
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "tool-audit-2026-07-05.manifest.json"), "w") as f:
        f.write("{not json")
    r = asyncio.run(dbmod.verify_audit_export("2026-07-05"))
    assert r["exists"] is False and r["ok"] is False


# ── archive retention (B3) ───────────────────────────────────────────────────

def test_cleanup_prunes_archive_with_its_own_policy(monkeypatch):
    import datetime as _dt

    out = _outdir()
    os.makedirs(out, exist_ok=True)
    old = (_dt.date.today() - _dt.timedelta(days=40)).isoformat()
    for suffix in (".csv", ".ndjson.gz", ".manifest.json"):
        open(os.path.join(out, f"tool-audit-{old}{suffix}"), "w").close()
    # Default policy: keep forever → nothing goes.
    asyncio.run(dbmod.cleanup_expired_data())
    assert os.path.exists(os.path.join(out, f"tool-audit-{old}.csv"))
    # Operator opts into a 30-day archive window.
    monkeypatch.setattr(config, "AUDIT_ARCHIVE_RETENTION_DAYS", 30)
    asyncio.run(dbmod.cleanup_expired_data())
    assert not any(name.startswith(f"tool-audit-{old}") for name in os.listdir(out))


# ── admin verify endpoint ────────────────────────────────────────────────────

def test_verify_endpoint_auth_and_day_gate():
    client = _client()
    assert client.get("/admin/audit/verify/2026-07-05").status_code == 200
    assert client.get("/admin/audit/verify/not-a-day").status_code == 404
    assert _client(authenticated=False).get("/admin/audit/verify/2026-07-05").status_code == 401
    assert _client(is_admin=False).get("/admin/audit/verify/2026-07-05").status_code == 403


def test_verify_endpoint_returns_manifest_check():
    asyncio.run(_seed_old_day())
    asyncio.run(dbmod.rollup_tool_audit())
    body = _client().get("/admin/audit/verify/2026-07-05").json()
    assert body["ok"] is True and body["exists"] is True
    assert set(body["files"]) == {
        "tool-audit-2026-07-05.csv", "tool-audit-2026-07-05.ndjson.gz"}
