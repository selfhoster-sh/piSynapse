"""Provision the first (owner admin) account. Used by install.py only.

Reads one JSON object from stdin:
  {"name": ..., "password": ..., "city": "",
   "mail": {"provider": "gmail|proton", "account": ..., "secret": ...} | null,
   "nc": {"url": ..., "account": ..., "secret": ...} | null,
   "db_path": "/tmp/test.db" (tests only; production uses the default DB)}

Writes one JSON object to stdout: {"ok": true, "user_id": ..., "api_key": ...}
(or {"error": ...} with exit 1). Secrets never hit logs — only the returned
api_key, which the installer displays exactly once.
"""

import asyncio
import json
import sys


def _fail(msg: str) -> int:
    print(json.dumps({"error": msg}))
    return 1


async def _run(payload: dict) -> dict:
    import db as dbmod

    try:
        if payload.get("db_path"):
            dbmod.DB_PATH = payload["db_path"]
        await dbmod.close_db()
        await dbmod.init_db()

        name = str(payload.get("name") or "").strip()
        password = str(payload.get("password") or "")
        if not name:
            return {"error": "Name must not be empty"}
        if len(password) < 8:
            return {"error": "Password must be at least 8 characters"}
        if await dbmod.count_users() > 0:
            return {"error": "Users already exist — refusing to provision a second owner"}

        try:
            user, raw_key = await dbmod.create_user(name, is_admin=True, approved=True)
        except ValueError as e:
            return {"error": str(e)}
        await dbmod.set_password(user["id"], password)
        warnings = []
        try:
            await dbmod.set_user_setting(user["id"], "ASSISTANT_USER", name[:100])
            city = str(payload.get("city") or "").strip()
            if city:
                await dbmod.set_user_setting(user["id"], "DEFAULT_CITY", city[:100])
        except ValueError as e:
            warnings.append(f"personal setting not saved: {e}")

        mail = payload.get("mail") or {}
        if mail.get("provider"):
            provider = str(mail["provider"]).strip().lower()
            secret = str(mail.get("secret") or "")
            if provider == "gmail":
                cred = {"address": str(mail.get("account") or ""), "app_password": secret}
            else:
                cred = {"address": str(mail.get("account") or ""), "bridge_password": secret}
            if not await dbmod.save_credential(user["id"], provider, cred):
                warnings.append("mail credential not saved (check values in browser later)")
        nc = payload.get("nc") or {}
        if nc.get("url"):
            cred = {"url": str(nc.get("url") or ""), "user": str(nc.get("account") or ""),
                    "password": str(nc.get("secret") or "")}
            if not await dbmod.save_credential(user["id"], "nextcloud", cred):
                warnings.append("nextcloud credential not saved (check values in browser later)")

        out = {"ok": True, "user_id": user["id"], "api_key": raw_key}
        if warnings:
            out["warnings"] = warnings
        return out
    finally:
        # aiosqlite's worker thread is non-daemon: without this the process
        # never exits and callers (installer/tests) hang forever.
        try:
            await dbmod.close_db()
        except Exception:
            pass


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return _fail("Invalid JSON on stdin")
    result = asyncio.run(_run(payload if isinstance(payload, dict) else {}))
    if isinstance(result, dict) and result.get("ok"):
        print(json.dumps(result))
        return 0
    return _fail(result.get("error", "provisioning failed") if isinstance(result, dict) else "provisioning failed")


if __name__ == "__main__":
    raise SystemExit(main())
