"""User identity endpoints (multi-user M1c).

Registration is open by default and closable by the admin via the
REGISTRATION_OPEN env toggle (standard self-hosted pattern). The first
registered user becomes admin; on upgraded single-user installs the
pre-existing `.env` key holder is already admin via bootstrap.
API keys are returned exactly once (creation/rotation) and stored hashed.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

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


def _authed_user_id(request: Request) -> str:
    uid = getattr(request.state, "user_id", None) or ""
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return uid


def _require_admin(request: Request) -> str:
    uid = _authed_user_id(request)
    if not bool(getattr(request.state, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Admin only")
    return uid


@router.post("/register", status_code=201)
async def register_user(req: RegisterRequest):
    """Create a user + API key. First user becomes admin."""
    from config import get

    if str(get("REGISTRATION_OPEN", "on")).strip().lower() != "on":
        raise HTTPException(status_code=403, detail="Registration is closed by the admin")
    from db import count_users, create_user, set_password

    is_first = await count_users() == 0
    try:
        user, raw_key = await create_user(req.name, is_admin=is_first)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=409, detail="User ID collision, retry registration")
        raise
    if req.password:
        await set_password(user["id"], req.password)
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


async def _public_user(user_id: str) -> dict:
    from db import get_user

    user = await get_user(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return user


@router.post("/password")
async def set_own_password(body: PasswordRequest, request: Request):
    """Set (first time) or change the account password (min 8 chars)."""
    from db import set_password, verify_password

    uid = _authed_user_id(request)
    user = await _public_user(uid)
    if user.get("has_password"):
        if not body.current or not await verify_password(uid, body.current):
            raise HTTPException(status_code=401, detail="Current password is wrong")
    await set_password(uid, body.new)
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
    from db import get_user

    user = await get_user(_authed_user_id(request))
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return {"user": user}


@router.get("")
async def list_all_users(request: Request):
    """List users (admin only; no key material)."""
    from db import count_users, list_users

    _require_admin(request)
    return {"users": await list_users(), "count": await count_users()}
