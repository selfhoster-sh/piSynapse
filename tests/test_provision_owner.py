"""Owner provisioning script (install.py first-admin path)."""
import asyncio
import json
import os
import subprocess
import sys

import pytest
from cryptography.fernet import Fernet

import db as dbmod

ROOT = os.path.join(os.path.dirname(__file__), "..")
SCRIPT = os.path.join(ROOT, "provision_owner.py")


def _run_provision(payload, tmp_path, creds_key):
    db_path = str(tmp_path / "prov.db")
    payload = dict(payload, db_path=db_path)
    env = dict(os.environ)
    env["MAIL_CREDS_KEY"] = creds_key
    proc = subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps(payload), capture_output=True, text=True,
        timeout=120, env=env,
    )
    return proc, db_path


@pytest.fixture
def prov_env(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "x.db"))
    # One key shared by the subprocess AND this process (decrypt must agree).
    # Never rely on credstore auto-generate here — it would append junk to
    # the developer's real .env.
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("MAIL_CREDS_KEY", key)
    asyncio.run(dbmod.close_db())
    yield tmp_path, key
    asyncio.run(dbmod.close_db())


def test_full_provision(prov_env, monkeypatch):
    tmp_path, creds_key = prov_env
    proc, db_path = _run_provision({
        "name": "Owner", "password": "secret123", "city": "Istanbul",
        "mail": {"provider": "gmail", "account": "o@x.com", "secret": "appw"},
        "nc": {"url": "https://cloud.example.com", "account": "o", "secret": "ncpw"},
    }, tmp_path, creds_key)
    assert proc.returncode == 0, proc.stderr[-500:]
    out = json.loads(proc.stdout)
    assert out["ok"] is True and len(out["api_key"]) >= 32
    assert "secret123" not in proc.stdout  # password never echoed

    monkeypatch.setattr(dbmod, "DB_PATH", db_path)
    user = asyncio.run(dbmod.get_user(out["user_id"]))
    assert user["is_admin"] is True and user["is_approved"] is True
    assert asyncio.run(dbmod.verify_password(user["id"], "secret123")) is True
    stored = asyncio.run(dbmod.get_user_settings(user["id"]))
    assert stored.get("ASSISTANT_USER") == "Owner"
    assert stored.get("DEFAULT_CITY") == "Istanbul"
    gmail = asyncio.run(dbmod.get_credential(user["id"], "gmail"))
    assert gmail == {"address": "o@x.com", "app_password": "appw"}
    nc = asyncio.run(dbmod.get_credential(user["id"], "nextcloud"))
    assert nc["url"] == "https://cloud.example.com"


def test_second_run_refused(prov_env):
    tmp_path, creds_key = prov_env
    _run_provision({"name": "Owner", "password": "secret123"}, tmp_path, creds_key)
    # Same db file (same tmp dir) now holds a user → must refuse.
    proc, _ = _run_provision({"name": "Second", "password": "secret123"}, tmp_path, creds_key)
    assert proc.returncode == 1
    assert "already exist" in proc.stdout


def test_bad_inputs_rejected(prov_env):
    tmp_path, creds_key = prov_env
    proc, _ = _run_provision({"name": "X", "password": "short"}, tmp_path, creds_key)
    assert proc.returncode == 1 and "8 characters" in proc.stdout
    proc, _ = _run_provision({"name": "Admin", "password": "secret123"}, tmp_path, creds_key)
    assert proc.returncode == 1 and "reserved" in proc.stdout.lower()
