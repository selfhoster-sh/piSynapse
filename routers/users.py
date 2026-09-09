"""User identity endpoints (multi-user M1c).

Registration is open by default and closable by the admin via the
REGISTRATION_OPEN env toggle (standard self-hosted pattern). The first
registered user becomes admin; on upgraded single-user installs the
pre-existing `.env` key holder is already admin via bootstrap.
API keys are returned exactly once (creation/rotation) and stored hashed.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/users", tags=["users"])


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


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
    from db import count_users, create_user

    is_first = await count_users() == 0
    try:
        user, raw_key = await create_user(req.name, is_admin=is_first)
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=409, detail="User ID collision, retry registration")
        raise
    return {"user": user, "api_key": raw_key}


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
