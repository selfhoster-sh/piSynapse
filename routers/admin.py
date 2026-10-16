"""Admin review queue for collective learning (Phase 4 backend).

Frozen/contested routing patterns land here instead of auto-entering the
corpus. Approving unblocks a pattern (feeder skips the freeze); rejecting
bars it from auto-add. All endpoints admin-only.
"""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from auth import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])

_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PatternDecision(BaseModel):
    signature: str = Field(min_length=1, max_length=500)
    group: str = Field(min_length=1, max_length=100)


@router.get("/patterns/review")
async def review_patterns(request: Request):
    """List frozen candidates with supports/contradicts + reputations."""
    from db import get_review_queue

    require_admin(request)
    return {"patterns": await get_review_queue()}


@router.post("/patterns/approve")
async def approve_pattern(req: PatternDecision, request: Request):
    """Approve a routing pattern (admin): feeder freeze no longer applies."""
    from db import record_pattern_decision

    admin = require_admin(request)
    await record_pattern_decision(req.signature, req.group, "approved", admin)
    return {"ok": True, "signature": req.signature, "status": "approved"}


@router.post("/patterns/reject")
async def reject_pattern(req: PatternDecision, request: Request):
    """Reject a routing pattern (admin): it is never auto-added."""
    from db import record_pattern_decision

    admin = require_admin(request)
    await record_pattern_decision(req.signature, req.group, "rejected", admin)
    return {"ok": True, "signature": req.signature, "status": "rejected"}


@router.get("/patterns/decisions")
async def list_decisions(request: Request):
    """List all recorded pattern decisions."""
    require_admin(request)
    from db import get_db

    db = await get_db()
    cur = await db.execute(
        "SELECT signature, proposed_group, status, decided_by, decided_at "
        "FROM pattern_approvals ORDER BY decided_at DESC"
    )
    return {
        "decisions": [
            {"signature": r[0], "group": r[1], "status": r[2],
             "decided_by": r[3], "decided_at": r[4]}
            for r in await cur.fetchall()
        ]
    }


@router.get("/audit/overview")
async def audit_overview(request: Request, days: int = 14):
    """Per-day tool-audit stats + the 24h error-rate alert, admin-only.

    `days` is clamped to [1, 3650]; the default follows config
    AUDIT_RETENTION_DAYS so the trend window matches the retention policy.
    """
    from db import get_audit_overview, audit_error_alert
    from config import AUDIT_RETENTION_DAYS

    require_admin(request)
    days = max(1, min(3650, days if days else AUDIT_RETENTION_DAYS))
    overview = await get_audit_overview(days)
    overview["alert"] = await audit_error_alert()
    return overview


@router.get("/audit/export/{day}")
async def audit_export_day(day: str, request: Request):
    """Download the archived pre-rollup CSV for one day, admin-only.

    The day is validated against a strict YYYY-MM-DD pattern before any path
    is built — no traversal reaches the filesystem. 404 when the day was never
    exported (still inside retention, or pruned).
    """
    from db import audit_export_dir

    require_admin(request)
    if not _DAY_RE.match(day):
        raise HTTPException(status_code=404, detail="No export for that day")
    path = Path(audit_export_dir()) / f"tool-audit-{day}.csv"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No export for that day")
    return FileResponse(path, media_type="text/csv; charset=utf-8",
                        filename=path.name)
