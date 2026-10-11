"""Ownership guards added 2026-10-11 (week-1 security pack).

1. POST /abort/{session_id} is owner-only. Before this fix any authenticated
   user could stop any other user's live generation, and the aborted:True
   answer doubled as a liveness oracle. A foreign session now answers
   exactly like an idle one (aborted:False, event untouched).
2. POST /reload-corpus is admin-only. The intent corpus is shared by every
   user; a normal session could force a rebuild (cache-bust + CPU spike).
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@pytest.fixture
def own_db(tmp_path, monkeypatch):
    import db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "abort.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


@pytest.fixture
def two_users(own_db):
    import db as dbmod

    owner, _ = asyncio.run(dbmod.create_user("owner"))
    intruder, _ = asyncio.run(dbmod.create_user("intruder"))
    return dbmod, owner["id"], intruder["id"]


@pytest.fixture
def chatmod():
    import routers.chat as chatmod

    yield chatmod
    chatmod._abort_events.clear()


def _req(uid, is_admin=False):
    return SimpleNamespace(state=SimpleNamespace(user_id=uid, is_admin=is_admin))


def test_abort_intruder_denied_owner_ok(two_users, chatmod):
    dbmod, owner, intruder = two_users
    asyncio.run(dbmod.save_message("s1", "user", "hi", user_id=owner))
    assert asyncio.run(dbmod.session_owned_by("s1", owner)) is True
    assert asyncio.run(dbmod.session_owned_by("s1", intruder)) is False

    abort = asyncio.Event()
    chatmod._abort_events["s1"] = abort

    result = asyncio.run(chatmod.abort_generation("s1", _req(intruder)))
    assert result == {"ok": True, "aborted": False}
    assert abort.is_set() is False  # generation not touched

    result = asyncio.run(chatmod.abort_generation("s1", _req(owner)))
    assert result == {"ok": True, "aborted": True}
    assert abort.is_set() is True


def test_abort_without_event_is_noop_even_for_owner(two_users, chatmod):
    _dbmod, owner, _intruder = two_users
    result = asyncio.run(chatmod.abort_generation("s2", _req(owner)))
    assert result == {"ok": True, "aborted": False}


def test_abort_event_without_session_row_denied_even_for_owner(two_users, chatmod):
    # Prod cannot reach this state (/stream saves the row before creating
    # the event); if it ever happens, deny is the safe answer.
    _dbmod, owner, _intruder = two_users
    abort = asyncio.Event()
    chatmod._abort_events["ghost"] = abort
    result = asyncio.run(chatmod.abort_generation("ghost", _req(owner)))
    assert result == {"ok": True, "aborted": False}
    assert abort.is_set() is False


def test_reload_corpus_admin_only(two_users, chatmod):
    _dbmod, owner, _intruder = two_users

    with pytest.raises(HTTPException) as exc:
        asyncio.run(chatmod.reload_corpus(_req(owner)))
    assert exc.value.status_code == 403

    result = asyncio.run(chatmod.reload_corpus(_req(owner, is_admin=True)))
    assert result == {"ok": True, "reloaded": True}


def test_reload_corpus_unauthenticated_401(chatmod):
    anon = SimpleNamespace(state=SimpleNamespace())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chatmod.reload_corpus(anon))
    assert exc.value.status_code == 401
