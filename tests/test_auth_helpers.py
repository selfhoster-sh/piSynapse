"""Shared auth helpers: current_user()/require_admin() + router wiring."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import auth
from auth import current_user, require_admin


def _req(uid=None, admin=False):
    state = SimpleNamespace()
    if uid is not None:
        state.user_id = uid
    state.is_admin = admin
    return SimpleNamespace(state=state)


def test_current_user_ok():
    assert current_user(_req("u1")) == "u1"


def test_current_user_missing_401():
    with pytest.raises(HTTPException) as e:
        current_user(SimpleNamespace(state=SimpleNamespace()))
    assert e.value.status_code == 401


def test_require_admin_ok():
    assert require_admin(_req("root", admin=True)) == "root"


def test_require_admin_forbids_non_admin():
    with pytest.raises(HTTPException) as e:
        require_admin(_req("u1", admin=False))
    assert e.value.status_code == 403


def test_require_admin_401_when_anonymous():
    with pytest.raises(HTTPException) as e:
        require_admin(SimpleNamespace(state=SimpleNamespace()))
    assert e.value.status_code == 401


def test_require_admin_custom_detail():
    with pytest.raises(HTTPException) as e:
        require_admin(_req("u1"), detail="System settings are admin-only")
    assert e.value.status_code == 403
    assert e.value.detail == "System settings are admin-only"


def test_routers_share_helpers():
    import routers.chat as chat
    import routers.config as cfg
    import routers.users as users

    assert users._authed_user_id is current_user
    assert users._require_admin is require_admin
    assert cfg._authed_uid is current_user
    # chat keeps legacy "default" fallback for exempt paths
    assert chat._uid(SimpleNamespace(state=SimpleNamespace())) == "default"
    assert chat._uid(_req("u9")) == "u9"


@pytest.fixture
def mail_gate_db(tmp_path, monkeypatch):
    import asyncio

    import db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "gate.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


def test_mail_gate_denies_non_admin(mail_gate_db, monkeypatch):
    import asyncio

    import mail as mailmod
    from tools.dispatcher import _run_mail_tool

    monkeypatch.setattr(mailmod, "_mail_clients", {})
    user, _key = asyncio.run(mail_gate_db.create_user("pleb"))
    result, _ = asyncio.run(_run_mail_tool("list_emails", {}, user_id=user["id"]))
    assert result == "ERROR: Email is available to the server admin only."


def test_mail_gate_denies_anonymous(mail_gate_db):
    import asyncio

    from tools.dispatcher import _run_mail_tool

    result, _ = asyncio.run(_run_mail_tool("list_emails", {}, user_id=None))
    assert result == "ERROR: Email is available to the server admin only."


def test_mail_gate_allows_unknown_id_compat(mail_gate_db, monkeypatch):
    """Opaque legacy/test ids fall through to the mail client (mocked)."""
    import asyncio

    import mail as mailmod
    from tools.dispatcher import _run_mail_tool

    monkeypatch.setattr(mailmod, "_mail_clients", {})
    monkeypatch.setenv("MAIL_PROVIDER", "")
    result, _ = asyncio.run(_run_mail_tool("list_emails", {}, user_id="alice"))
    assert result.startswith("ERROR: Mail connection failed")
