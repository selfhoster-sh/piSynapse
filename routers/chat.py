#!/usr/bin/env python3
"""piSynapse Chat API Router
Handles chat messages, streaming responses, session management, and memory.
"""

import asyncio
import json
import logging
import re
import traceback

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from config import get
from db import (
    clear_history,
    delete_branch,
    delete_last_assistant,
    delete_memory,
    get_all_memories,
    get_all_sessions,
    get_db,
    get_history,
    get_memories,
    get_messages_to_summarize,
    get_session_meta,
    link_audits_to_message,
    save_message,
    search_memories,
    update_session_name,
    update_session_summary,
)
from llm import chat_with_ollama, chat_with_ollama_stream, strip_prefix, summarize_conversation
from retrieval import merge_history, retrieve_relevant_history

logger = logging.getLogger("piSynapse")


def _clean_assistant_reply(text: str) -> str:
    """Sanitize an assistant reply before it reaches history.

    Strips leaked tool-call fragments (`call:name{{...}}`, mangled channel
    tags) so the model can never imitate its own leaked syntax on later
    turns — that self-poisoning caused a tool-call loop (2026-08-22).
    Returns "" when nothing but leak fragments remain, signalling callers
    to skip persisting entirely.
    """
    from llm.utils import strip_tool_leaks

    return strip_tool_leaks(strip_prefix(text or ""))

router = APIRouter(prefix="/chat", tags=["chat", "sessions", "memories"])

# Per-session abort flags: session_id -> asyncio.Event (set = abort requested).
# Known limitation (accepted): two concurrent streams on the SAME session
# overwrite each other's event, so an abort targets the newest stream only.
# Single-user deployment + the UI's stop button always targets the current
# stream, so this race has no practical impact.
_abort_events: dict[str, asyncio.Event] = {}

# -- Session ID validation --
# Allow: alphanumeric, hyphens, underscores. Max 64 chars.
# Rejects injection attempts, excessively long IDs, and path-traversal patterns.
_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _validate_session_id(session_id: str) -> str:
    """Return session_id if valid, else raise 400."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid session_id: use only letters, numbers, hyphens, underscores (max 64 chars).",
        )
    return session_id


# -- Request/Response Models --

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session"
    user_id: str = "default"
    think_mode: bool = False
    images: list[str] = []
    reasoning_effort: str = ""
    # Set to "chip" by the UI when the send came from a welcome chip:
    # chip texts carry no details, so create/send tools must ask first.
    origin: str = ""


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    history_length: int
    memories_saved: int
    pending_action: dict | None = None
    thinking: str | None = None
    verification_status: str | None = None
    retrieved_count: int = 0
    retrieval_ms: int = 0


class RenameRequest(BaseModel):
    name: str


class ExecuteRequest(BaseModel):
    session_id: str
    user_id: str = "default"
    tool: str
    params: dict


# -- Helpers --

async def _gather_memories(message: str, user_id: str, query_embedding: bytes | None = None) -> list[dict]:
    core = await get_memories(user_id=user_id, limit=5)
    relevant = await search_memories(message, user_id=user_id, limit=get("MEMORY_LIMIT", 10), query_embedding=query_embedding)
    seen, combined = set(), []
    for mem in core + relevant:
        if mem["id"] not in seen:
            seen.add(mem["id"])
            combined.append(mem)
    return combined[:get("MEMORY_LIMIT", 10)]


async def _shared_query_embedding(message: str) -> bytes | None:
    """Embed the query once so retrieval, intent and memory search share a
    single inference instead of embedding the message three times.
    """
    try:
        from embedding import embed_async
        return await embed_async(message)
    except Exception as e:
        logger.warning(f"Shared query embedding failed (falling back to per-call): {e}")
        return None


async def _update_summary(session_id: str):
    try:
        meta = await get_session_meta(session_id)
        to_summarize, new_boundary = await get_messages_to_summarize(
            session_id, get("HISTORY_LIMIT", 12), meta["summarized_until"],
            get("SUMMARY_BATCH_SIZE", 5), early_trigger=get("SUMMARY_EARLY_TRIGGER", 6),
        )
        if not to_summarize:
            return
        new_summary = await summarize_conversation(to_summarize, meta["summary"])
        await update_session_summary(session_id, new_summary, new_boundary)
    except Exception as e:
        logger.error(f"Summary update failed for {session_id}: {e}")


async def _enrich_title(session_id: str):
    """Background task: replace the RAKE instant title with an LLM-generated one.

    Only runs when LLM_TITLE_ENRICHMENT is enabled and ONLY on the very first
    assistant reply of the session (when total message count in DB is exactly 2:
    1 user + 1 assistant). Never runs on subsequent turns.
    Reads user + assistant messages from DB, calls LLM, updates session name.
    Failure is silent — the RAKE title stays as fallback.
    """
    try:
        from config import get
        if get("LLM_TITLE_ENRICHMENT", "on") != "on":
            return
        # Robust first-turn check: total row count must be exactly 2 (1 user + 1 assistant).
        # Using COUNT(*) avoids race where get_history(limit=3) sees a transient 2
        # while total is actually 50 (limit truncates, COUNT does not).
        db = await get_db()
        async with db.execute("SELECT COUNT(*) FROM conversations WHERE session_id = ?", (session_id,)) as cur:
            total = (await cur.fetchone())[0]
        if total != 2:
            return
        messages = await get_history(session_id, limit=2)
        user_msg = messages[0]["content"] if messages[0]["role"] == "user" else ""
        asst_msg = messages[1]["content"] if messages[1]["role"] == "assistant" else ""
        if not user_msg or not asst_msg:
            return
        from title import generate_llm_title
        title = await generate_llm_title(user_msg, asst_msg)
        if title:
            await update_session_name(session_id, title)
    except Exception as e:
        logger.error(f"Title enrichment failed for {session_id}: {e}")


# -- Endpoints --

@router.post("/", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, background_tasks: BackgroundTasks):
    _validate_session_id(req.session_id)
    if not req.message.strip() and not req.images:
        raise HTTPException(status_code=400, detail="Message or image is required.")

    # Per-session rate limit (20 req/min per session)
    from main import _session_limiter
    allowed, _ = _session_limiter.allow(req.session_id)
    if not allowed:
        raise HTTPException(status_code=429, detail="Session rate limit exceeded. Try again later.")

    try:
        await save_message(req.session_id, "user", req.message, images=req.images or None)

        from llm import _classify_intent, is_contextual_followup
        query_embedding = await _shared_query_embedding(req.message)
        history_coro = get_history(req.session_id, limit=get("HISTORY_LIMIT", 12))
        retrieval_coro = retrieve_relevant_history(req.session_id, req.message, query_embedding=query_embedding)
        memories_coro = _gather_memories(req.message, req.user_id, query_embedding=query_embedding)
        meta_coro = get_session_meta(req.session_id)
        intent_coro = _classify_intent(req.message, query_embedding=query_embedding)

        history, retrieved, memories, meta, (intent, tool_group) = await asyncio.gather(
            history_coro, retrieval_coro, memories_coro, meta_coro, intent_coro
        )
        retrieved_msgs, ret_stats = retrieved
        history = merge_history(history, retrieved_msgs)

        if intent == "question" and tool_group is None and is_contextual_followup(req.message):
            from llm import llm_resolve_with_evidence, resolve_resume_context
            resolved = await resolve_resume_context(req.message, history, session_id=req.session_id)
            if resolved:
                intent, tool_group = "action", resolved
                logger.info(f"Resume resolver -> {resolved} (session history): {req.message!r}")
            else:
                intent, tool_group = await llm_resolve_with_evidence(req.message, history)

        result = await chat_with_ollama(
            history, memories=memories, think=req.think_mode,
            summary=meta["summary"], user_id=req.user_id, session_id=req.session_id,
            intent=intent, tool_group=tool_group, reasoning_effort=req.reasoning_effort,
        )

        if result["pending_action"]:
            return ChatResponse(
                reply="", session_id=req.session_id, history_length=len(history),
                memories_saved=0, pending_action=result["pending_action"],
                retrieved_count=len(retrieved_msgs), retrieval_ms=round(ret_stats["latency_ms"]),
            )

        reply_text = _clean_assistant_reply(result["reply"])
        if reply_text:
            await save_message(req.session_id, "assistant", reply_text, reasoning=result.get("thinking"))
        else:
            logger.warning("Non-stream assistant reply empty after sanitization — not saved (session %s)", req.session_id)
        background_tasks.add_task(_update_summary, req.session_id)
        background_tasks.add_task(_enrich_title, req.session_id)

        return ChatResponse(
            reply=reply_text or result["reply"], session_id=req.session_id,
            history_length=len(history), memories_saved=result["memories_saved"],
            thinking=result.get("thinking"),
            retrieved_count=len(retrieved_msgs), retrieval_ms=round(ret_stats["latency_ms"]),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Chat endpoint error: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@router.post("/stream")
async def chat_stream(req: ChatRequest, background_tasks: BackgroundTasks):
    _validate_session_id(req.session_id)
    if not req.message.strip() and not req.images:
        raise HTTPException(status_code=400, detail="Message or image is required.")

    # Per-session rate limit (20 req/min per session)
    from main import _session_limiter
    allowed, _ = _session_limiter.allow(req.session_id)
    if not allowed:
        raise HTTPException(status_code=429, detail="Session rate limit exceeded. Try again later.")

    try:
        await save_message(req.session_id, "user", req.message, images=req.images or None)

        from llm import _classify_intent, is_contextual_followup
        query_embedding = await _shared_query_embedding(req.message)
        history_coro = get_history(req.session_id, limit=get("HISTORY_LIMIT", 12))
        retrieval_coro = retrieve_relevant_history(req.session_id, req.message, query_embedding=query_embedding)
        memories_coro = _gather_memories(req.message, req.user_id, query_embedding=query_embedding)
        meta_coro = get_session_meta(req.session_id)
        intent_coro = _classify_intent(req.message, query_embedding=query_embedding)

        history, retrieved, memories, meta, (intent, tool_group) = await asyncio.gather(
            history_coro, retrieval_coro, memories_coro, meta_coro, intent_coro
        )
        retrieved_msgs, ret_stats = retrieved
        history = merge_history(history, retrieved_msgs)

        if intent == "question" and tool_group is None and is_contextual_followup(req.message):
            from llm import llm_resolve_with_evidence, resolve_resume_context
            resolved = await resolve_resume_context(req.message, history, session_id=req.session_id)
            if resolved:
                intent, tool_group = "action", resolved
                logger.info(f"Resume resolver -> {resolved} (session history): {req.message!r}")
            else:
                intent, tool_group = await llm_resolve_with_evidence(req.message, history)
    except Exception as e:
        logger.error("Chat stream setup error: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")

    reply_parts: list[str] = []
    reply_saved = False
    abort_event = asyncio.Event()
    _abort_events[req.session_id] = abort_event

    async def generate():
        nonlocal reply_saved
        stream_audit_ids: list[int] = []
        try:
            async for event in chat_with_ollama_stream(
                history, memories=memories, think=req.think_mode,
                summary=meta["summary"], user_id=req.user_id, session_id=req.session_id,
                intent=intent, tool_group=tool_group, reasoning_effort=req.reasoning_effort,
                origin=(req.origin or "").strip().lower(),
            ):
                if abort_event.is_set():
                    logger.info("Stream aborted for session %s", req.session_id)
                    break
                if "token" in event:
                    reply_parts.append(event["token"])
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event.get("done"):
                    full = _clean_assistant_reply("".join(reply_parts))
                    reply_saved = True  # also when skipped — never let finally re-save raw parts
                    done_payload = {'done': True, 'session_id': req.session_id,
                                    'memories_saved': event.get('memories_saved', 0),
                                    'retrieved_count': len(retrieved_msgs),
                                    'retrieval_ms': round(ret_stats['latency_ms'])}
                    if full:
                        msg_id = await save_message(req.session_id, "assistant", full, reasoning=event.get("reasoning") or None)
                        await link_audits_to_message(msg_id, stream_audit_ids)
                        # Anchor for per-message regenerate branching (the frontend
                        # stores this id on the bubble and truncates context from it).
                        done_payload['message_id'] = msg_id
                    else:
                        logger.info("Streamed assistant reply empty after sanitization — not saved (session %s)", req.session_id)
                    yield f"data: {json.dumps(done_payload)}\n\n"
                elif "reasoning" in event:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif "confirm" in event:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif "tool" in event:
                    tinfo = event.get("tool") or {}
                    if tinfo.get("phase") == "end" and tinfo.get("audit_id") is not None:
                        stream_audit_ids.append(tinfo["audit_id"])
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif "gen_retry" in event:
                    # NOT terminal — the inner loop keeps generating after an
                    # in-flight retry (escalation/overflow/tool_leak). Returning
                    # here silently swallowed every post-retry token.
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif "error" in event:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    return
        except Exception as e:
            logger.error("Chat stream generate error: %s\n%s", e, traceback.format_exc())
            yield f"data: {json.dumps({'error': 'Stream error'})}\n\n"
        finally:
            _abort_events.pop(req.session_id, None)
            if not reply_saved and reply_parts:
                try:
                    partial = _clean_assistant_reply("".join(reply_parts))
                    if partial:
                        msg_id = await save_message(req.session_id, "assistant", partial)
                        await link_audits_to_message(msg_id, stream_audit_ids)
                        logger.info("Saved partial assistant reply after stream interruption")
                    else:
                        logger.info("Partial assistant reply empty after sanitization — not saved")
                    reply_saved = True
                except Exception as e:
                    logger.error("Failed to save partial reply: %s\n%s", e, traceback.format_exc())

    summary_bg = BackgroundTasks()
    summary_bg.add_task(_update_summary, req.session_id)
    summary_bg.add_task(_enrich_title, req.session_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
        background=summary_bg,
    )


@router.post("/abort/{session_id}")
async def abort_generation(session_id: str):
    _validate_session_id(session_id)
    event = _abort_events.get(session_id)
    if event:
        event.set()
        logger.info("Abort requested for session %s", session_id)
        return {"ok": True, "aborted": True}
    return {"ok": True, "aborted": False}


@router.post("/execute", response_model=ChatResponse)
async def execute_action(req: ExecuteRequest):
    import time

    _validate_session_id(req.session_id)
    from tool_verification import run_verification
    from tools import CONFIRM_TOOLS, is_tool_success, run_tool, validate_confirm_params
    try:
        if req.tool in CONFIRM_TOOLS:
            err = validate_confirm_params(req.tool, req.params)
            if err:
                raise HTTPException(status_code=400, detail=err)
        t0 = time.perf_counter()
        try:
            result, entity_id = await run_tool(req.tool, req.params, context={"user_id": req.user_id, "session_id": req.session_id})
            success = is_tool_success(result)
        except Exception as e:
            logger.error("Execute action error: %s\n%s", e, traceback.format_exc())
            result = f"ERROR: {e}"
            entity_id = None
            success = False
        duration_ms = (time.perf_counter() - t0) * 1000
        # Manual executions (confirmed destructive actions) are exactly the
        # ones that must be audit-logged — the model loop already logs its
        # own tool calls, but /execute runs outside that loop.
        audit_id, verification_status = await run_verification(req.tool, req.params, result, success, entity_id=entity_id, duration_ms=duration_ms, error=None if success else result)
        msg_id = await save_message(req.session_id, "assistant", result)
        if audit_id is not None:
            await link_audits_to_message(msg_id, [audit_id])
        return ChatResponse(reply=result, session_id=req.session_id, history_length=0, memories_saved=0, verification_status=verification_status)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Execute action error: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


class CorrectionRequest(BaseModel):
    audit_id: int
    expected_tool: str | None = None
    expected_group: str | None = None


@router.post("/tool-correction")
async def set_tool_correction(req: CorrectionRequest):
    """Set a correction on a tool audit log entry for fine-tuning data collection.

    Called when the user identifies a tool call was incorrect. The user may
    send EITHER a precise expected_tool (exact tool name, power-user / curl)
    OR an expected_group (domain key from GET /tools/groups, the UI path) —
    at least one is required. Updates the fields and sets corrected_at.
    """
    from db import get_audit_tool_name, set_tool_correction
    from llm.intent import tool_group_keys
    from tools.definitions import TOOL_NAMES, TOOL_TO_GROUP

    if not req.expected_tool and not req.expected_group:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of expected_tool or expected_group",
        )

    if req.expected_tool is not None and req.expected_tool not in TOOL_NAMES:
        valid_tools = ", ".join(sorted(TOOL_NAMES))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid expected_tool: '{req.expected_tool}'. Valid tools: {valid_tools}",
        )

    if req.expected_group is not None and req.expected_group not in tool_group_keys():
        valid_groups = ", ".join(tool_group_keys())
        raise HTTPException(
            status_code=400,
            detail=f"Invalid expected_group: '{req.expected_group}'. Valid groups: {valid_groups}",
        )

    ok = await set_tool_correction(req.audit_id, req.expected_tool, req.expected_group)
    if not ok:
        raise HTTPException(status_code=404, detail="Audit log entry not found")

    # Same-group "correction" (BUG-5): the picked group already matches the
    # tool's own group — a no-op, not a real correction. Surface it so the UI
    # can warn and so corpus_feeder skips these as noise.
    noop = False
    if req.expected_group is not None and req.expected_tool is None:
        tool_name = await get_audit_tool_name(req.audit_id)
        if tool_name and TOOL_TO_GROUP.get(tool_name) == req.expected_group:
            noop = True

    return {
        "ok": True,
        "noop": noop,
        "audit_id": req.audit_id,
        "expected_tool": req.expected_tool,
        "expected_group": req.expected_group,
    }


class ConfirmRequest(BaseModel):
    audit_id: int


@router.post("/tool-confirm")
async def set_tool_confirmation(req: ConfirmRequest):
    """Record a positive confirmation on a tool audit log entry.

    Called when the user marks a tool call as correct. A confirmation is the
    opposite of a correction, so any previously stored correction fields on
    the row are cleared (and vice versa) — a row holds at most one signal.
    """
    from db import set_tool_confirmation

    ok = await set_tool_confirmation(req.audit_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Audit log entry not found")
    return {"ok": True, "audit_id": req.audit_id}


class MessageFeedbackRequest(BaseModel):
    message_id: int
    value: str
    note: str | None = None


@router.post("/message-feedback")
async def post_message_feedback(req: MessageFeedbackRequest):
    """Store a 👍/👎 verdict for an assistant message that had no tool call.

    The thumbs are now universal: every round is markable, so subtle failures —
    the model asking a clarifying question instead of acting, dropping the
    intent, or hallucinating a no-tool reply — are captured as data instead of
    silently lost. One row per message; marking the other thumb overwrites it.
    A free-text note on 👎 records *why* it was wrong.
    """
    from db import upsert_message_feedback

    if req.value not in ("up", "down"):
        raise HTTPException(status_code=400, detail="value must be 'up' or 'down'")

    ok = await upsert_message_feedback(req.message_id, req.value, req.note)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Message not found, or it is not an assistant message",
        )
    return {"ok": True, "message_id": req.message_id, "value": req.value}


# -- Sessions --

@router.get("/sessions")
async def list_sessions():
    return {"sessions": await get_all_sessions()}


@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, req: RenameRequest):
    _validate_session_id(session_id)
    name = (req.name or "").strip()[:100] or "Unnamed"
    await update_session_name(session_id, name)
    return {"ok": True}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all its messages, maps, and metadata."""
    _validate_session_id(session_id)
    await clear_history(session_id)
    return {"ok": True, "message": f"Session '{session_id}' deleted."}


@router.delete("/messages/last/{session_id}")
async def delete_last_msg(session_id: str):
    """Delete the last assistant message for regenerate.

    Called by the frontend before re-sending the user message so the
    stale reply never appears in the model's context window.
    """
    _validate_session_id(session_id)
    removed = await delete_last_assistant(session_id)
    return {"ok": True, "removed": removed}


class BranchRequest(BaseModel):
    message_id: int


@router.delete("/messages/branch/{session_id}")
async def delete_branch_msg(session_id: str, req: BranchRequest):
    """Truncate a conversation from an anchored message onward.

    Per-message regenerate: the clicked assistant message is the anchor; it and
    everything saved after it are removed so the re-run draws a clean branch
    (same prompt, fresh reply) — matching ChatGPT/Claude branch semantics.
    """
    _validate_session_id(session_id)
    removed = await delete_branch(session_id, req.message_id)
    return {"ok": True, "removed": removed}


@router.get("/search")
async def search_messages(q: str = Query(..., min_length=1)):
    """FTS5 full-text search across all session messages."""
    from db import search_sessions
    results = await search_sessions(q)
    return {"ok": True, "results": results}


@router.post("/sessions")
async def create_session(req: RenameRequest | None = None):
    """Explicitly create a new session with an optional name."""
    import uuid
    session_id = str(uuid.uuid4())[:12]
    name = (req.name.strip()[:100] if req and req.name else "New Chat") or "New Chat"
    from db import get_db
    db = await get_db()
    await db.execute(
        "INSERT OR IGNORE INTO sessions (id, name, created_at, last_active) VALUES (?, ?, datetime('now'), datetime('now'))",
        (session_id, name),
    )
    await db.commit()
    return {"ok": True, "session_id": session_id, "name": name}


# -- History --

@router.get("/history")
async def get_chat_history(session_id: str = Query(...)):
    _validate_session_id(session_id)
    msgs = await get_history(session_id, limit=50, include_reasoning=True, include_audits=True)
    return {"session_id": session_id, "messages": msgs}


@router.post("/reload-corpus")
async def reload_corpus():
    """Force the intent-routing corpus (base + additions.jsonl) to rebuild live.

    Normally the cache revalidates automatically via the additions file mtime on
    the next classification; this endpoint makes the refresh immediate and
    deterministic (e.g. after corpus_feeder.py --commit). No service restart.
    """
    from llm.intent import reset_tool_embed_cache
    reset_tool_embed_cache()
    return {"ok": True, "reloaded": True}


@router.delete("/history")
async def clear_chat_history(session_id: str = Query(...)):
    _validate_session_id(session_id)
    await clear_history(session_id)
    return {"status": "success", "message": f"'{session_id}' deleted."}


# -- Memories --

@router.get("/memories")
async def list_memories(user_id: str = Query("default"), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    all_mems = await get_all_memories(user_id)
    page = all_mems[offset:offset + limit]
    return {"user_id": user_id, "count": len(all_mems), "limit": limit, "offset": offset, "memories": page}


@router.delete("/memories")
async def delete_memory_endpoint(user_id: str = Query("default"), id: str = Query(...)):
    try:
        memory_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid memory ID.")
    await delete_memory(user_id=user_id, memory_id=memory_id)
    return {"status": "success", "message": f"Memory {id} deleted."}


# -- Export --

@router.get("/export")
async def export_data(user_id: str = Query("default")):
    """Export all user data as JSON (memories + sessions summary)."""
    from db import get_all_memories, get_all_sessions
    mems = await get_all_memories(user_id)
    sessions = await get_all_sessions()
    return {
        "user_id": user_id,
        "memories": [{"id": m["id"], "content": m["content"], "category": m["category"], "importance": m["importance"]} for m in mems],
        "sessions": sessions,
        "session_count": len(sessions),
        "memory_count": len(mems),
    }


# -- Image Upload (multipart, for mobile clients) --

@router.post("/upload", tags=["media"])
async def upload_image(file: UploadFile = File(...)):
    """Upload an image as multipart/form-data. Returns base64 string for use in chat."""
    import base64

    from config import get as cfg
    max_mb = int(cfg("MEDIA_MAX_MB", 100))
    max_bytes = max_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            await file.close()
            raise HTTPException(status_code=413, detail=f"File too large (max {max_mb} MB).")
        chunks.append(chunk)
    await file.close()
    data = b"".join(chunks)
    return {"ok": True, "base64": base64.b64encode(data).decode("utf-8"), "size_bytes": len(data)}


# -- Offline Sync (mobile) --

class SyncCommand(BaseModel):
    tool: str
    params: dict
    timestamp: str
    session_id: str = "default_session"

    @field_validator("session_id")
    @classmethod
    def validate_sid(cls, v: str) -> str:
        if not _SESSION_ID_RE.match(v):
            raise ValueError("Invalid session_id: use only letters, numbers, hyphens, underscores (max 64 chars).")
        return v


class SyncRequest(BaseModel):
    commands: list[SyncCommand]


@router.post("/sync", tags=["sync"])
async def sync_commands(req: SyncRequest, background_tasks: BackgroundTasks):
    """Process batched offline commands from mobile client.

    Each command is executed sequentially. Safe tools run immediately;
    confirm tools are queued and returned for user approval.

    Returns results for each command in order.
    """
    from tool_verification import run_verification
    from tools import CONFIRM_TOOLS, OFFLINE_SAFE_TOOLS, is_tool_success, run_tool

    results = []
    for i, cmd in enumerate(req.commands):
        if cmd.tool in CONFIRM_TOOLS and cmd.tool not in OFFLINE_SAFE_TOOLS:
            results.append({
                "index": i,
                "status": "needs_confirm",
                "tool": cmd.tool,
                "params": cmd.params,
                "session_id": cmd.session_id,
            })
            continue

        import time
        t0 = time.perf_counter()
        try:
            result, entity_id = await run_tool(
                cmd.tool, cmd.params,
                context={"user_id": "default", "session_id": cmd.session_id},
            )
            success = is_tool_success(result)
            duration_ms = (time.perf_counter() - t0) * 1000
            is_noop = isinstance(result, str) and result.startswith("NOOP")
            audit_id, verification_status = await run_verification(cmd.tool, cmd.params, result, success, entity_id=entity_id, duration_ms=duration_ms)
            results.append({
                "index": i,
                "status": "noop" if is_noop else ("ok" if success else "error"),
                "tool": cmd.tool,
                "result": result if not success else None,
                "verification_status": verification_status,
            })
        except Exception as e:
            logger.error(f"Sync command {i} failed: {e}")
            results.append({
                "index": i,
                "status": "error",
                "tool": cmd.tool,
                "result": str(e),
            })

    ok_count = sum(1 for r in results if r["status"] == "ok")
    confirm_count = sum(1 for r in results if r["status"] == "needs_confirm")
    error_count = sum(1 for r in results if r["status"] == "error")
    return {"ok": True, "total": len(req.commands), "executed": ok_count, "needs_confirm": confirm_count, "errors": error_count, "results": results}

