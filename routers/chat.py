#!/usr/bin/env python3
"""
piSynapse Chat API Router
Handles chat messages, streaming responses, session management, and memory.
"""

import os
import json
import logging
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from llm import chat_with_ollama, chat_with_ollama_stream, run_tool, summarize_conversation
from memory import (
    get_history as db_get_history,
    save_message,
    get_memories,
    search_memories,
    clear_history,
    get_all_memories,
    get_all_sessions,
    update_session_name,
    get_session_meta,
    get_messages_to_summarize,
    update_session_summary,
    delete_memory as db_delete_memory,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("piSynapse")

router = APIRouter(prefix="/chat", tags=["chat"])

HISTORY_LIMIT      = int(os.getenv("HISTORY_LIMIT", "20"))
MEMORY_LIMIT       = int(os.getenv("MEMORY_LIMIT", "10"))
SUMMARY_BATCH_SIZE = int(os.getenv("SUMMARY_BATCH_SIZE", "6"))


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session"
    user_id: str = "default"
    think_mode: bool = False


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    history_length: int
    memories_saved: int
    pending_action: dict | None = None


class RenameRequest(BaseModel):
    name: str


class ExecuteRequest(BaseModel):
    session_id: str
    user_id: str = "default"
    tool: str
    params: dict


# ── Memory Retrieval ──────────────────────────────────────────────────────────
# Combines high-importance "core" memories with memories that are semantically
# relevant to the current message, so the LLM gets both stable facts about the
# user and context that actually matches what's being discussed.
async def gather_relevant_memories(message: str, user_id: str) -> list[dict]:
    core_memories     = await get_memories(user_id=user_id, limit=5)
    relevant_memories = await search_memories(message, user_id=user_id, limit=MEMORY_LIMIT)

    seen, combined = set(), []
    for mem in core_memories + relevant_memories:
        if mem["id"] not in seen:
            seen.add(mem["id"])
            combined.append(mem)
    return combined[:MEMORY_LIMIT]


# ── Rolling Summary Update (background task) ─────────────────────────────────
# Folds messages that have aged out of the HISTORY_LIMIT window into a running
# summary, so the model keeps long-term context without resending full history.
async def update_conversation_summary(session_id: str):
    try:
        meta = await get_session_meta(session_id)
        to_summarize, new_boundary = await get_messages_to_summarize(
            session_id, HISTORY_LIMIT, meta["summarized_until"], SUMMARY_BATCH_SIZE
        )
        if not to_summarize:
            return
        new_summary = await summarize_conversation(to_summarize, meta["summary"])
        await update_session_summary(session_id, new_summary, new_boundary)
    except Exception as e:
        logger.error(f"Summary update failed for session {session_id}: {e}")


# ── Chat Endpoint (non-streaming) ────────────────────────────────────────────
@router.post("/", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, background_tasks: BackgroundTasks):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    await save_message(req.session_id, "user", req.message)
    history       = await db_get_history(req.session_id, limit=HISTORY_LIMIT)
    core_memories = await gather_relevant_memories(req.message, req.user_id)
    session_meta  = await get_session_meta(req.session_id)
    result        = await chat_with_ollama(history, core_memories, think=req.think_mode,
                                            summary=session_meta["summary"], user_id=req.user_id)

    # The model requested a tool that needs user confirmation before running
    if result["pending_action"]:
        return ChatResponse(
            reply="",
            session_id=req.session_id,
            history_length=len(history),
            memories_saved=0,
            pending_action=result["pending_action"],
        )

    final_reply = result["reply"]
    await save_message(req.session_id, "assistant", final_reply)

    background_tasks.add_task(update_conversation_summary, req.session_id)

    return ChatResponse(
        reply=final_reply,
        session_id=req.session_id,
        history_length=len(history),
        memories_saved=result["memories_saved"],
    )


# ── Streaming Chat Endpoint ──────────────────────────────────────────────────
@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """
    Token-by-token streaming endpoint.
    Returns SSE format: data: {...}\n\n
    First token typically arrives in 3-5 seconds.
    """
    await save_message(req.session_id, "user", req.message)
    history       = await db_get_history(req.session_id, limit=HISTORY_LIMIT)
    core_memories = await gather_relevant_memories(req.message, req.user_id)
    session_meta  = await get_session_meta(req.session_id)

    reply_parts: list[str] = []

    async def generate():
        async for event in chat_with_ollama_stream(history, core_memories, req.think_mode,
                                                     summary=session_meta["summary"], user_id=req.user_id):

            if "token" in event:
                reply_parts.append(event["token"])
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            elif "confirm" in event:
                # Confirmation required — notify UI without saving
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                return

            elif "error" in event:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                return

            elif event.get("done"):
                # Stream complete — memory saves already happened as tool
                # calls during the stream, so just persist the visible reply.
                full = "".join(reply_parts)
                await save_message(req.session_id, "assistant", full)
                yield f"data: {json.dumps({'done': True, 'session_id': req.session_id, 'memories_saved': event.get('memories_saved', 0)})}\n\n"

    background_tasks = BackgroundTasks()
    background_tasks.add_task(update_conversation_summary, req.session_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":      "no-cache",
            "X-Accel-Buffering":  "no",
            "Connection":         "keep-alive",
        },
        background=background_tasks,
    )


# ── Execute User-Confirmed Actions ───────────────────────────────────────────
@router.post("/execute", response_model=ChatResponse)
async def execute_action(req: ExecuteRequest):
    """Executes user-approved tools like send_email / delete_calendar_event."""
    result = await run_tool(req.tool, req.params, context={"user_id": req.user_id})
    await save_message(req.session_id, "assistant", result)
    return ChatResponse(
        reply=result,
        session_id=req.session_id,
        history_length=0,
        memories_saved=0,
    )


# ── Session Management ───────────────────────────────────────────────────────
@router.get("/sessions")
async def list_sessions():
    try:
        return {"sessions": await get_all_sessions()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, req: RenameRequest):
    """Saves session name to DB — for synchronized names across devices."""
    await update_session_name(session_id, req.name)
    return {"ok": True}


@router.get("/history")
async def get_chat_history(session_id: str = Query(...)):
    try:
        msgs = await db_get_history(session_id, limit=50)
        return {"session_id": session_id, "messages": msgs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history")
async def clear_chat_history(session_id: str = Query(...)):
    await clear_history(session_id)
    return {"status": "success", "message": f"'{session_id}' deleted."}


# ── Memory Management ────────────────────────────────────────────────────────
@router.get("/memories")
async def list_memories(user_id: str = Query("default")):
    try:
        mems = await get_all_memories(user_id)
        return {"user_id": user_id, "count": len(mems), "memories": mems}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/memories")
async def delete_memory(user_id: str = Query("default"), id: str = Query(...)):
    """Delete a memory record by ID."""
    try:
        try:
            memory_id_int = int(id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid memory ID.")
        await db_delete_memory(user_id=user_id, memory_id=memory_id_int)
        return {"status": "success", "message": f"Memory {id} deleted."}
    except Exception as e:
        logger.error(f"Memory delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
