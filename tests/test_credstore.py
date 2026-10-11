"""credstore: credential encryption/decryption (security-critical, was 56%).

Credentials (Nextcloud, mail) rest encrypted via Fernet. This module had no
dedicated test file — only indirect reach — so the key-generation path, the
wrong-key path and the failure semantics were unverified.
"""
import os

import pytest
from cryptography.fernet import Fernet

import credstore


def _set_key(monkeypatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("MAIL_CREDS_KEY", key)
    return key


def test_roundtrip_preserves_payload(monkeypatch):
    _set_key(monkeypatch)
    payload = {"url": "https://cloud.example", "user": "alice", "password": "s3cret-token"}
    blob = credstore.encrypt_payload(payload)
    assert isinstance(blob, str)
    assert credstore.decrypt_payload(blob) == payload


def test_ciphertext_does_not_leak_plaintext(monkeypatch):
    _set_key(monkeypatch)
    blob = credstore.encrypt_payload({"password": "s3cret-token"})
    assert "s3cret-token" not in blob
    assert "password" not in blob


def test_wrong_key_decrypts_to_none(monkeypatch):
    _set_key(monkeypatch)
    blob = credstore.encrypt_payload({"password": "x"})
    monkeypatch.setenv("MAIL_CREDS_KEY", Fernet.generate_key().decode())
    assert credstore.decrypt_payload(blob) is None  # never raises


def test_tampered_blob_decrypts_to_none(monkeypatch):
    _set_key(monkeypatch)
    blob = credstore.encrypt_payload({"password": "x"})
    tampered = blob[:-3] + ("AAA" if not blob.endswith("AAA") else "BBB")
    assert credstore.decrypt_payload(tampered) is None


def test_garbage_blob_decrypts_to_none(monkeypatch):
    _set_key(monkeypatch)
    assert credstore.decrypt_payload("not-a-fernet-token") is None


def test_encrypt_with_invalid_key_raises_valueerror(monkeypatch):
    monkeypatch.setenv("MAIL_CREDS_KEY", "definitely-not-a-valid-fernet-key")
    with pytest.raises(ValueError):
        credstore.encrypt_payload({"password": "x"})


def test_get_key_uses_env_when_set(monkeypatch):
    key = _set_key(monkeypatch)
    assert credstore._get_key() == key.encode("utf-8")


def test_get_key_generates_and_persists_when_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("MAIL_CREDS_KEY", raising=False)
    envfile = tmp_path / ".env"
    import config

    monkeypatch.setattr(config, "ENV_PATH", str(envfile))
    try:
        key = credstore._get_key()
        Fernet(key)  # a valid Fernet key, or this raises
        assert envfile.read_text(encoding="utf-8").startswith("MAIL_CREDS_KEY=")
        assert os.environ.get("MAIL_CREDS_KEY") == key.decode("utf-8")
    finally:
        # _get_key sets os.environ directly (not via monkeypatch) — clean up.
        os.environ.pop("MAIL_CREDS_KEY", None)
