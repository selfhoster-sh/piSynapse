"""Admin review queue for collective learning (Phase 4 backend).

Frozen/contested routing patterns land here instead of auto-entering the
corpus. Approving unblocks a pattern (feeder skips the freeze); rejecting
bars it from auto-add. All endpoints admin-only.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from auth import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


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
