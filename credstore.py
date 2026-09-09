"""Per-user encrypted credential store (collective-services backend).

Mail/Nextcloud passwords live here — Fernet-encrypted, one row per
(user, provider). The key lives ONLY in `.env` (MAIL_CREDS_KEY), never in
the DB and never in logs. Plaintext exists solely in-process between
decrypt and the IMAP/HTTP login call.
"""

VALID_PROVIDERS = ("gmail", "proton", "nextcloud")

# Required payload keys per provider (account = address/username, shown back
# in listings; secret = never returned by any endpoint).
PROVIDER_FIELDS = {
    "gmail": ("address", "app_password"),
    "proton": ("address", "bridge_password"),
    "nextcloud": ("url", "user", "password"),
}


def _get_key() -> bytes:
    """Load MAIL_CREDS_KEY, generating + persisting it on first use."""
    import os

    raw = (os.getenv("MAIL_CREDS_KEY") or "").strip()
    if raw:
        return raw.encode("utf-8")
    from cryptography.fernet import Fernet

    fresh = Fernet.generate_key()
    try:
        from config import ENV_PATH

        line = f"MAIL_CREDS_KEY={fresh.decode('utf-8')}\n"
        with open(ENV_PATH, "a", encoding="utf-8") as f:
            f.write(line)
        os.environ["MAIL_CREDS_KEY"] = fresh.decode("utf-8")
    except Exception:
        pass
    import logging as _logging

    _logging.getLogger("piSynapse").warning(
        "MAIL_CREDS_KEY was missing; a fresh key was generated. "
        "Previously stored credentials (if any) are unreadable."
    )
    return fresh


def encrypt_payload(payload: dict) -> str:
    """Encrypt a JSON-serializable payload. Never raises (ValueError instead)."""
    import json as _json

    from cryptography.fernet import Fernet

    try:
        return Fernet(_get_key()).encrypt(_json.dumps(payload).encode("utf-8")).decode("utf-8")
    except Exception as e:
        raise ValueError(f"credential encrypt failed: {e}") from e


def decrypt_payload(blob: str) -> dict | None:
    """Decrypt, or None on any failure (wrong key, tampered row). Never raises."""
    import json as _json

    from cryptography.fernet import Fernet

    try:
        return _json.loads(Fernet(_get_key()).decrypt(blob.encode("utf-8")).decode("utf-8"))
    except Exception:
        return None
