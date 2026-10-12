"""routers/chat.py thin endpoints + POST /sync (were uncovered).

Session/history/memory/sync wrappers exercised against a real tmp DB (they
delegate to db.* which read DB_PATH at call time), and the batched offline
command replay (POST /sync) against fakes: needs_confirm, ok, noop, error.
"""
import asyncio
import types

import pytest
from fastapi import BackgroundTasks, HTTPException

import db as dbmod
import routers.chat as rc


@pytest.fixture
def own_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "chat.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


def _req(uid="u1"):
    return types.SimpleNamespace(state=types.SimpleNamespace(user_id=uid, is_admin=False))


def _run(coro):
    return asyncio.run(coro)


# ── Session / history / memory endpoints (real tmp DB) ──────────────────────

def test_create_rename_list_delete_session(own_db):
    created = _run(rc.create_session(rc.RenameRequest(name="İlk"), _req()))
    sid = created["session_id"]
    assert created["ok"] and created["name"] == "İlk"

    assert _run(rc.rename_session(sid, rc.RenameRequest(name="Yeni"), _req()))["ok"] is True
    names = {s["session_id"]: s["name"] for s in _run(rc.list_sessions(_req()))["sessions"]}
    assert names[sid] == "Yeni"

    assert _run(rc.delete_session(sid, _req()))["ok"] is True
    assert sid not in {s["session_id"] for s in _run(rc.list_sessions(_req()))["sessions"]}


def test_create_session_default_name(own_db):
    created = _run(rc.create_session(None, _req()))
    assert created["name"] == "New Chat"


def test_history_endpoints(own_db):
    sid = "s1"
    _run(dbmod.save_message(sid, "user", "merhaba", user_id="u1"))
    _run(dbmod.save_message(sid, "assistant", "selam", user_id="u1"))

    hist = _run(rc.get_chat_history(sid, _req()))
    assert [m["content"] for m in hist["messages"]] == ["merhaba", "selam"]

    last = _run(rc.delete_last_msg(sid, _req()))
    assert last["ok"] is True

    assert _run(rc.clear_chat_history(sid, _req()))["status"] == "success"


def test_delete_branch_endpoint(own_db):
    sid = "sb"
    _run(dbmod.save_message(sid, "user", "a", user_id="u1"))
    mid = _run(dbmod.save_message(sid, "assistant", "b", user_id="u1"))
    out = _run(rc.delete_branch_msg(sid, rc.BranchRequest(message_id=mid), _req()))
    assert out["ok"] is True


def test_search_messages_endpoint(own_db):
    _run(dbmod.save_message("s1", "user", "zümrüt teleskop notu", user_id="u1"))
    res = _run(rc.search_messages("zümrüt", _req()))
    assert res["ok"] is True and any(r["session_id"] == "s1" for r in res["results"])


def test_import_and_pull_history(own_db):
    req = rc.ImportHistoryRequest(
        session_id="simp", client_key="phone-1",
        messages=[{"role": "user", "content": "offline msg"}],
    )
    imported = _run(rc.import_chat_history(req, _req()))
    assert imported["ok"] is True

    pulled = _run(rc.pull_chat_history(_req()))
    assert pulled["ok"] is True and "session_history" in pulled


def test_memories_list_and_delete(own_db):
    async def seed():
        db = await dbmod.get_db()
        await db.execute(
            "INSERT INTO memories (user_id, content, category, importance) VALUES ('u1','not','general',5)"
        )
        await db.commit()

    _run(seed())
    listed = _run(rc.list_memories(_req(), limit=10, offset=0))
    assert listed["count"] == 1 and listed["user_id"] == "u1"
    mem_id = listed["memories"][0]["id"]

    assert _run(rc.delete_memory_endpoint(_req(), id=str(mem_id)))["status"] == "success"

    with pytest.raises(HTTPException) as exc:
        _run(rc.delete_memory_endpoint(_req(), id="not-a-number"))
    assert exc.value.status_code == 400


def test_export_data(own_db):
    _run(dbmod.save_message("s1", "user", "x", user_id="u1"))
    out = _run(rc.export_data(_req()))
    assert out["user_id"] == "u1" and "memories" in out and "sessions" in out


# ── Two-way sync items endpoints (real tmp DB) ─────────────────────────────

def test_sync_items_post_and_get(own_db):
    body = rc.SyncItemsRequest(items=[rc.SyncItem(
        uuid="u-1", entity_type="task", data={"v": 1},
        updated_at="2026-10-11T10:00:00Z", origin="phone-1",
    )])
    posted = _run(rc.post_sync_items_local(body, _req()))
    assert posted["applied"] == 1

    got = _run(rc.get_sync_items_local(_req(), entity_type=None, since=None))
    assert got["items"][0]["uuid"] == "u-1"
    assert got["items"][0]["origin"] == "phone-1"


# ── POST /sync (batched offline command replay) ────────────────────────────

def _install_sync(monkeypatch, results):
    """results: list of (value_or_exception) per run_tool call."""
    seq = list(results)

    async def fake_run_tool(name, params, context=None):
        nxt = seq.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    import tool_verification
    import tools

    monkeypatch.setattr(tools, "run_tool", fake_run_tool)
    monkeypatch.setattr(tools, "is_tool_success", lambda r: not str(r).startswith(("ERROR", "NOOP")))
    monkeypatch.setattr(tools, "CONFIRM_TOOLS", {"send_email", "delete_task"})
    monkeypatch.setattr(tools, "OFFLINE_SAFE_TOOLS", {"save_memory"})

    async def fake_verify(tool, params, result, success, **kw):
        return (None, "verified" if success else None)

    monkeypatch.setattr(tool_verification, "run_verification", fake_verify)


def _sync(commands):
    body = rc.SyncRequest(commands=[
        rc.SyncCommand(tool=t, params=p, timestamp="2026-10-11T10:00:00Z") for t, p in commands
    ])
    return asyncio.run(rc.sync_commands(body, BackgroundTasks(), _req()))


def test_sync_needs_confirm_for_gated_tool(monkeypatch):
    _install_sync(monkeypatch, [])
    out = _sync([("send_email", {})])
    assert out["needs_confirm"] == 1
    assert out["results"][0]["status"] == "needs_confirm"


def test_sync_ok_noop_and_error(monkeypatch):
    _install_sync(monkeypatch, [("sent ok", None), ("NOOP: already done", None), RuntimeError("boom")])
    out = _sync([("save_memory", {}), ("save_memory", {}), ("save_memory", {})])
    statuses = [r["status"] for r in out["results"]]
    assert statuses == ["ok", "noop", "error"]
    assert out["executed"] == 1 and out["errors"] == 1
