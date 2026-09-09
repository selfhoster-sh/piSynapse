"""Collective-learning Phase 1: feedback writes are owner-scoped.

A user may correct/confirm/thumb only their own audit rows and messages.
Cross-user attempts fail closed (False / 404), indistinguishable from
not-found — no ownership oracle.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@pytest.fixture
def own_db(tmp_path, monkeypatch):
    import db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "own.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


@pytest.fixture
def two_users(own_db):
    import db as dbmod

    owner, _ = asyncio.run(dbmod.create_user("owner"))
    intruder, _ = asyncio.run(dbmod.create_user("intruder"))
    return own_db, owner["id"], intruder["id"]


def _req(uid):
    return SimpleNamespace(state=SimpleNamespace(user_id=uid, is_admin=False))


def test_correction_owner_ok_intruder_denied(two_users):
    dbmod, owner, intruder = two_users
    aid = asyncio.run(dbmod.log_tool_call("list_notes", {}, True, user_id=owner))
    assert asyncio.run(dbmod.set_tool_correction(aid, "list_notes", user_id=owner)) is True
    assert asyncio.run(dbmod.set_tool_correction(aid, "list_notes", user_id=intruder)) is False
    # Unscoped legacy path still works (offline scripts only).
    assert asyncio.run(dbmod.set_tool_correction(aid, "list_notes")) is True


def test_confirmation_owner_ok_intruder_denied(two_users):
    dbmod, owner, intruder = two_users
    aid = asyncio.run(dbmod.log_tool_call("list_notes", {}, True, user_id=owner))
    assert asyncio.run(dbmod.set_tool_confirmation(aid, user_id=intruder)) is False
    assert asyncio.run(dbmod.set_tool_confirmation(aid, user_id=owner)) is True
    assert asyncio.run(dbmod.get_audit_tool_name(aid, user_id=intruder)) is None
    assert asyncio.run(dbmod.get_audit_tool_name(aid, user_id=owner)) == "list_notes"


def test_message_feedback_owner_ok_intruder_denied(two_users):
    dbmod, owner, intruder = two_users
    mid = asyncio.run(dbmod.save_message("s1", "assistant", "hi", user_id=owner))
    assert asyncio.run(dbmod.upsert_message_feedback(mid, "up", user_id=intruder)) is False
    assert asyncio.run(dbmod.upsert_message_feedback(mid, "up", user_id=owner)) is True


def test_endpoints_scope_to_caller(two_users):
    import db as dbmod
    from routers.chat import (
        ConfirmRequest,
        CorrectionRequest,
        MessageFeedbackRequest,
        post_message_feedback,
        set_tool_confirmation,
        set_tool_correction,
    )

    _, owner, intruder = two_users
    aid = asyncio.run(dbmod.log_tool_call("list_notes", {}, True, user_id=owner))
    mid = asyncio.run(dbmod.save_message("s1", "assistant", "hi", user_id=owner))

    # Intruder gets 404 on another user's rows (no oracle: same as not-found).
    with pytest.raises(HTTPException) as e:
        asyncio.run(set_tool_correction(
            CorrectionRequest(audit_id=aid, expected_tool="list_notes"), _req(intruder)))
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        asyncio.run(set_tool_confirmation(ConfirmRequest(audit_id=aid), _req(intruder)))
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        asyncio.run(post_message_feedback(
            MessageFeedbackRequest(message_id=mid, value="up"), _req(intruder)))
    assert e.value.status_code == 404

    # Owner succeeds on all three.
    asyncio.run(set_tool_correction(
        CorrectionRequest(audit_id=aid, expected_tool="list_notes"), _req(owner)))
    asyncio.run(set_tool_confirmation(ConfirmRequest(audit_id=aid), _req(owner)))
    resp = asyncio.run(post_message_feedback(
        MessageFeedbackRequest(message_id=mid, value="up"), _req(owner)))
    assert resp["ok"] is True


def test_endpoints_reject_anonymous(two_users):
    from routers.chat import ConfirmRequest, set_tool_confirmation

    anon = SimpleNamespace(state=SimpleNamespace())
    with pytest.raises(HTTPException) as e:
        asyncio.run(set_tool_confirmation(ConfirmRequest(audit_id=1), anon))
    assert e.value.status_code == 401
