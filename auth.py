"""Shared request-auth helpers (multi-user).

The middleware in main.py resolves the caller's API key to a user and
stores ``request.state.user_id`` / ``request.state.is_admin``. Routers must
read that state through these helpers — never trust a client-supplied
user_id — so all endpoints share one fail-closed code path.
"""

from fastapi import HTTPException, Request


def current_user(request: Request) -> str:
    """Return the authenticated user id, 401 when missing."""
    uid = getattr(request.state, "user_id", None) or ""
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return uid


def require_admin(request: Request, detail: str = "Admin only") -> str:
    """Return the user id; 401 when unauthenticated, 403 when not admin."""
    uid = current_user(request)
    if not bool(getattr(request.state, "is_admin", False)):
        raise HTTPException(status_code=403, detail=detail)
    return uid
