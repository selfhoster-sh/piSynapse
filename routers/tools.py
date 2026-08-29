"""piSynapse Tool Taxonomy Endpoints

Machine-readable metadata about the tool groups the dispatcher can route
to. Human-readable labels are NOT served from here — they live in the
frontend i18n (static/index.html GROUP_LABELS) so the backend never
hardcodes localized strings.
"""

from fastapi import APIRouter

from llm.intent import tool_group_keys

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("/groups")
async def list_tool_groups() -> dict:
    """Return the canonical machine-readable group keys of the tool taxonomy.

    Keys are derived from the intent classifier's keyword-check table, the
    single source of truth for which groups an action can be routed to.
    """
    return {"groups": list(tool_group_keys())}