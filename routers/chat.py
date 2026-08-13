#!/usr/bin/env python3
"""piSynapse Chat API Router
Handles chat messages, streaming responses, session management, and memory.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import HISTORY_LIMIT, MEMORY_LIMIT, SUMMARY_BATCH_SIZE, SUMMARY_EARLY_TRIGGER
from db import (
    clear_history,
    delete_memory,
    get_all_memories,
    get_all_sessions,
    get_history,
    get_memories,
    get_messages_to_summarize,
    get_session_meta,
    save_message,
    search_memories,
    update_session_name,
    update_session_summary,
)
from llm import chat_with_ollama, chat_with_ollama_stream, strip_prefix, summarize_conversation

logger = logging.getLogger("piSynapse")

router = APIRouter(prefix="/chat", tags=["chat"])


# -- Request/Response Models --

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session"
    user_id: str = "default"
    think_mode: bool = False
    images: list[str] = []


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


# -- Helpers --

async def _gather_memories(message: str, user_id: str) -> list[dict]:
    core = await get_memories(user_id=user_id, limit=5)
    relevant = await search_memories(message, user_id=user_id, limit=MEMORY_LIMIT)
    seen, combined = set(), []
    for mem in core + relevant:
        if mem["id"] not in seen:
            seen.add(mem["id"])
            combined.append(mem)
    return combined[:MEMORY_LIMIT]


async def _update_summary(session_id: str):
    try:
        meta = await get_session_meta(session_id)
        to_summarize, new_boundary = await get_messages_to_summarize(
            session_id, HISTORY_LIMIT, meta["summarized_until"],
            SUMMARY_BATCH_SIZE, early_trigger=SUMMARY_EARLY_TRIGGER,
        )
        if not to_summarize:
            return
        new_summary = await summarize_conversation(to_summarize, meta["summary"])
        await update_session_summary(session_id, new_summary, new_boundary)
    except Exception as e:
        logger.error(f"Summary update failed for {session_id}: {e}")


# -- Endpoints --

@router.post("/", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, background_tasks: BackgroundTasks):
    if not req.message.strip() and not req.images:
        raise HTTPException(status_code=400, detail="Message or image is required.")

    try:
        await save_message(req.session_id, "user", req.message, images=req.images or None)

        from llm import _classify_intent
        history_coro = get_history(req.session_id, limit=HISTORY_LIMIT)
        memories_coro = _gather_memories(req.message, req.user_id)
        meta_coro = get_session_meta(req.session_id)
        intent_coro = _classify_intent(req.message)

        history, memories, meta, (intent, tool_group) = await asyncio.gather(
            history_coro, memories_coro, meta_coro, intent_coro
        )

        result = await chat_with_ollama(
            history, memories=memories, think=req.think_mode,
            summary=meta["summary"], user_id=req.user_id, session_id=req.session_id,
            intent=intent, tool_group=tool_group,
        )

        if result["pending_action"]:
            return ChatResponse(
                reply="", session_id=req.session_id, history_length=len(history),
                memories_saved=0, pending_action=result["pending_action"],
            )

        await save_message(req.session_id, "assistant", result["reply"])
        background_tasks.add_task(_update_summary, req.session_id)

        return ChatResponse(
            reply=result["reply"], session_id=req.session_id,
            history_length=len(history), memories_saved=result["memories_saved"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/stream")
async def chat_stream(req: ChatRequest, background_tasks: BackgroundTasks):
    try:
        await save_message(req.session_id, "user", req.message, images=req.images or None)

        from llm import _classify_intent
        history_coro = get_history(req.session_id, limit=HISTORY_LIMIT)
        memories_coro = _gather_memories(req.message, req.user_id)
        meta_coro = get_session_meta(req.session_id)
        intent_coro = _classify_intent(req.message)

        history, memories, meta, (intent, tool_group) = await asyncio.gather(
            history_coro, memories_coro, meta_coro, intent_coro
        )
    except Exception as e:
        logger.error(f"Chat stream setup error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

    reply_parts: list[str] = []
    reply_saved = False

    async def generate():
        nonlocal reply_saved
        try:
            async for event in chat_with_ollama_stream(
                history, memories=memories, think=req.think_mode,
                summary=meta["summary"], user_id=req.user_id, session_id=req.session_id,
                intent=intent, tool_group=tool_group,
            ):
                if "token" in event:
                    reply_parts.append(event["token"])
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif "confirm" in event:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    return
                elif "error" in event:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    return
                elif event.get("done"):
                    full = strip_prefix("".join(reply_parts))
                    await save_message(req.session_id, "assistant", full)
                    reply_saved = True
                    yield f"data: {json.dumps({'done': True, 'session_id': req.session_id, 'memories_saved': event.get('memories_saved', 0)})}\n\n"
        except Exception as e:
            logger.error(f"Chat stream generate error: {e}")
            yield f"data: {json.dumps({'error': 'Stream error'})}\n\n"
        finally:
            if not reply_saved and reply_parts:
                try:
                    await save_message(req.session_id, "assistant", strip_prefix("".join(reply_parts)))
                    reply_saved = True
                    logger.info("Saved partial assistant reply after stream interruption")
                except Exception as e:
                    logger.error(f"Failed to save partial reply: {e}")

    summary_bg = BackgroundTasks()
    summary_bg.add_task(_update_summary, req.session_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
        background=summary_bg,
    )


@router.post("/execute", response_model=ChatResponse)
async def execute_action(req: ExecuteRequest):
    from tools import CONFIRM_TOOLS, run_tool, validate_confirm_params
    try:
        if req.tool in CONFIRM_TOOLS:
            err = validate_confirm_params(req.tool, req.params)
            if err:
                raise HTTPException(status_code=400, detail=err)
        result = await run_tool(req.tool, req.params, context={"user_id": req.user_id, "session_id": req.session_id})
        await save_message(req.session_id, "assistant", result)
        return ChatResponse(reply=result, session_id=req.session_id, history_length=0, memories_saved=0)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execute action error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")


# -- Sessions --

@router.get("/sessions")
async def list_sessions():
    return {"sessions": await get_all_sessions()}


@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, req: RenameRequest):
    await update_session_name(session_id, req.name)
    return {"ok": True}


# -- History --

@router.get("/history")
async def get_chat_history(session_id: str = Query(...)):
    msgs = await get_history(session_id, limit=50)
    return {"session_id": session_id, "messages": msgs}


@router.delete("/history")
async def clear_chat_history(session_id: str = Query(...)):
    await clear_history(session_id)
    return {"status": "success", "message": f"'{session_id}' deleted."}


# -- Memories --

@router.get("/memories")
async def list_memories(user_id: str = Query("default")):
    mems = await get_all_memories(user_id)
    return {"user_id": user_id, "count": len(mems), "memories": mems}


@router.delete("/memories")
async def delete_memory_endpoint(user_id: str = Query("default"), id: str = Query(...)):
    try:
        memory_id = int(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid memory ID.")
    await delete_memory(user_id=user_id, memory_id=memory_id)
    return {"status": "success", "message": f"Memory {id} deleted."}

