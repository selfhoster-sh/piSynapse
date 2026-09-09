"""User identity endpoints (multi-user M1c).

Registration is open by default and closable by the admin via the
REGISTRATION_OPEN env toggle (standard self-hosted pattern). The first
registered user becomes admin; on upgraded single-user installs the
pre-existing `.env` key holder is already admin via bootstrap.
API keys are returned exactly once (creation/rotation) and stored hashed.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from auth import current_user as _authed_user_id
from auth import require_admin as _require_admin


def _set_session_cookie(response: Response, raw_token: str) -> None:
    """Attach the session cookie: HttpOnly + Lax, Secure only behind HTTPS."""
    from config import SESSION_COOKIE_SECURE
    from db import SESSION_COOKIE_NAME, SESSION_TTL_DAYS

    response.set_cookie(
        SESSION_COOKIE_NAME, raw_token,
        max_age=SESSION_TTL_DAYS * 86400, httponly=True, samesite="lax",
        secure=SESSION_COOKIE_SECURE, path="/",
    )

router = APIRouter(prefix="/users", tags=["users"])


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    device: str | None = Field(default=None, max_length=100)


class LoginRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)
    device: str | None = Field(default=None, max_length=100)


class PasswordRequest(BaseModel):
    current: str | None = Field(default=None, max_length=200)
    new: str = Field(min_length=8, max_length=200)


@router.post("/register", status_code=201)
async def register_user(req: RegisterRequest, response: Response):
    """Create a user + API key. First user becomes admin."""
    from config import get

    if str(get("REGISTRATION_OPEN", "on")).strip().lower() != "on":
        raise HTTPException(status_code=403, detail="Registration is closed by the admin")
    from db import count_users, create_session, create_user, set_password

    is_first = await count_users() == 0
    try:
        user, raw_key = await create_user(req.name, is_admin=is_first, approved=is_first)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=409, detail="User ID collision, retry registration")
        raise
    if req.password:
        await set_password(user["id"], req.password)
    # Signup auto-login: the browser never needs the API key afterwards.
    _, raw_session = await create_session(user["id"], req.device or "browser")
    _set_session_cookie(response, raw_session)
    return {"user": user, "api_key": raw_key}


@router.post("/login")
async def login_user(req: LoginRequest):
    """Verify name+password and issue a per-device API key.

    Identical 401 for unknown name vs wrong password (no enumeration).
    The returned key is shown once; other devices are unaffected.
    """
    from db import create_device_key, get_user_by_name, verify_password

    user = await get_user_by_name(req.name)
    ok = await verify_password(user["id"], req.password) if user else False
    if not user or not ok:
        raise HTTPException(status_code=401, detail="Invalid name or password")
    row, raw_key = await create_device_key(
        user["id"], req.device or f"login {date.today().isoformat()}")
    public = await _public_user(user["id"])
    return {"user": public, "api_key": raw_key, "key_id": row["id"]}


@router.post("/session")
async def open_session(req: LoginRequest, response: Response):
    """Password login for browsers: session cookie, NO key material returned.

    Identical 401 for unknown name vs wrong password (no enumeration).
    The API key stays server-side; the browser authenticates with the
    HttpOnly session cookie from here on.
    """
    from db import create_session, get_user_by_name, verify_password

    user = await get_user_by_name(req.name)
    ok = await verify_password(user["id"], req.password) if user else False
    if not user or not ok:
        raise HTTPException(status_code=401, detail="Invalid name or password")
    _, raw = await create_session(user["id"], req.device or "browser")
    _set_session_cookie(response, raw)
    return {"user": await _public_user(user["id"])}


@router.post("/logout")
async def close_session(request: Request, response: Response):
    """Revoke the current browser session and clear the cookie.

    Always succeeds (idempotent) so a dead session can never trap the UI.
    """
    from db import SESSION_COOKIE_NAME, revoke_session

    await revoke_session(request.cookies.get(SESSION_COOKIE_NAME, ""))
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


async def _public_user(user_id: str) -> dict:
    from db import get_user

    user = await get_user(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return user


@router.post("/password")
async def set_own_password(body: PasswordRequest, request: Request):
    """Set (first time) or change the account password (min 8 chars).

    Changing the password revokes all other browser sessions.
    """
    from db import SESSION_COOKIE_NAME, revoke_other_sessions, set_password, verify_password

    uid = _authed_user_id(request)
    user = await _public_user(uid)
    if user.get("has_password"):
        if not body.current or not await verify_password(uid, body.current):
            raise HTTPException(status_code=401, detail="Current password is wrong")
    await set_password(uid, body.new)
    await revoke_other_sessions(uid, request.cookies.get(SESSION_COOKIE_NAME, ""))
    return {"ok": True}


@router.get("/me/keys")
async def list_own_keys(request: Request):
    """List this account's device keys (no key material)."""
    from db import list_device_keys

    return {"keys": await list_device_keys(_authed_user_id(request))}


@router.delete("/me/keys/{key_id}")
async def revoke_own_key(key_id: str, request: Request):
    """Revoke one of this account's device keys."""
    from db import revoke_device_key

    if not await revoke_device_key(_authed_user_id(request), key_id):
        raise HTTPException(status_code=404, detail="Key not found")
    return {"ok": True}


class CredentialRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=20)
    account: str = Field(min_length=1, max_length=500)
    secret: str = Field(min_length=1, max_length=500)
    url: str | None = Field(default=None, max_length=500)


@router.post("/me/credentials")
async def save_own_credential(req: CredentialRequest, request: Request):
    """Save a per-user service credential (mail/Nextcloud), encrypted at rest.

    Secrets are Fernet-encrypted before storage and never returned by any
    endpoint. Overwrites the previous credential for the same provider.
    """
    from db import save_credential

    provider = req.provider.strip().lower()
    payload: dict[str, str] = {"account": req.account.strip(), "secret": req.secret}
    if provider == "nextcloud":
        if not req.url or not req.url.strip():
            raise HTTPException(status_code=400, detail="Nextcloud needs a server URL")
        payload = {"url": req.url.strip(), "user": req.account.strip(), "password": req.secret}
    elif provider == "gmail":
        payload = {"address": req.account.strip(), "app_password": req.secret}
    elif provider == "proton":
        payload = {"address": req.account.strip(), "bridge_password": req.secret}
    else:
        raise HTTPException(status_code=400, detail="Unknown provider (gmail, proton, nextcloud)")
    if not await save_credential(_authed_user_id(request), provider, payload):
        raise HTTPException(status_code=400, detail="Invalid credential values")
    return {"ok": True, "provider": provider}


@router.get("/me/credentials")
async def list_own_credentials(request: Request):
    """List saved credential providers with public labels (no secrets)."""
    from db import list_credentials

    return {"credentials": await list_credentials(_authed_user_id(request))}


@router.delete("/me/credentials/{provider}")
async def delete_own_credential(provider: str, request: Request):
    """Remove a saved credential."""
    from db import delete_credential

    if not await delete_credential(_authed_user_id(request), provider.strip().lower()):
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"ok": True}


@router.post("/key/rotate")
async def rotate_own_key(request: Request):
    """Replace the caller's API key. Returns the new key exactly once."""
    from db import rotate_user_key

    uid = _authed_user_id(request)
    raw_key = await rotate_user_key(uid)
    if raw_key is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": uid, "api_key": raw_key}


@router.get("/me")
async def read_own_user(request: Request):
    """Return the caller's user record (never includes key material)."""
    from db import DEFAULT_USER_ID, get_user

    uid = _authed_user_id(request)
    user = await get_user(uid)
    if user is None:
        # Legacy single-user key with no users row yet (pre-bootstrap): the
        # server owner looking at their own instance. Mirrors what
        # ensure_default_admin would create — without it, the owner's only
        # known key fails validation in the login UI.
        if uid == DEFAULT_USER_ID:
            return {"user": {"id": DEFAULT_USER_ID, "name": "admin", "is_admin": True,
                             "is_approved": True, "has_password": False, "created_at": None}}
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return {"user": user}


@router.get("")
async def list_all_users(request: Request):
    """List users (admin only; no key material)."""
    from db import count_users, list_users

    _require_admin(request)
    return {"users": await list_users(), "count": await count_users()}


@router.delete("/{user_id}")
async def delete_one_user(user_id: str, request: Request):
    """Delete a user and all of their data (admin only).

    Refuses self-deletion and deleting the last admin — the instance must
    always keep exactly one way in.
    """
    from db import delete_user, get_user

    me = _require_admin(request)
    if user_id == me:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    target = await get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("is_admin"):
        from db import list_users

        admins = [u for u in await list_users() if u.get("is_admin")]
        if len(admins) <= 1:
            raise HTTPException(status_code=409, detail="Cannot delete the last admin")
    await delete_user(user_id)
    return {"ok": True, "deleted": user_id}


@router.post("/{user_id}/approve")
async def approve_one_user(user_id: str, request: Request):
    """Mark a user quorum-approved (admin only).

    Approval gates collective-learning quorum counting only — chat, tools,
    settings and feedback work identically for unapproved users. Admins
    always count regardless of the flag.
    """
    from db import get_user, set_approved

    _require_admin(request)
    if await get_user(user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    await set_approved(user_id, True)
    return {"ok": True, "user_id": user_id, "is_approved": True}


@router.post("/{user_id}/unapprove")
async def unapprove_one_user(user_id: str, request: Request):
    """Revoke a user's quorum approval (admin only)."""
    from db import get_user, set_approved

    _require_admin(request)
    if await get_user(user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    await set_approved(user_id, False)
    return {"ok": True, "user_id": user_id, "is_approved": False}
