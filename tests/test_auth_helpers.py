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
