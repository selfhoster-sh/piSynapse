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

from config import get
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
from retrieval import merge_history, retrieve_relevant_history

logger = logging.getLogger("piSynapse")

router = APIRouter(prefix="/chat", tags=["chat"])


# -- Request/Response Models --

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session"
    user_id: str = "default"
    think_mode: bool = False
    images: list[str] = []
    reasoning_effort: str = ""


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    history_length: int
    memories_saved: int
    pending_action: dict | None = None
    thinking: str | None = None
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


# -- Endpoints --

@router.post("/", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, background_tasks: BackgroundTasks):
    if not req.message.strip() and not req.images:
        raise HTTPException(status_code=400, detail="Message or image is required.")

    try:
        await save_message(req.session_id, "user", req.message, images=req.images or None)

        from llm import _classify_intent, contextual_email_followup
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

        if intent == "question" and tool_group is None and contextual_email_followup(req.message, history):
            intent, tool_group = "action", "email"
            logger.info(f"Contextual follow-up detected (email): {req.message!r}")

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

        await save_message(req.session_id, "assistant", result["reply"], reasoning=result.get("thinking"))
        background_tasks.add_task(_update_summary, req.session_id)

        return ChatResponse(
            reply=result["reply"], session_id=req.session_id,
            history_length=len(history), memories_saved=result["memories_saved"],
            thinking=result.get("thinking"),
            retrieved_count=len(retrieved_msgs), retrieval_ms=round(ret_stats["latency_ms"]),
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

        from llm import _classify_intent, contextual_email_followup
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

        if intent == "question" and tool_group is None and contextual_email_followup(req.message, history):
            intent, tool_group = "action", "email"
            logger.info(f"Contextual follow-up detected (email): {req.message!r}")
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
                intent=intent, tool_group=tool_group, reasoning_effort=req.reasoning_effort,
            ):
                if "token" in event:
                    reply_parts.append(event["token"])
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event.get("done"):
                    full = strip_prefix("".join(reply_parts))
                    await save_message(req.session_id, "assistant", full, reasoning=event.get("reasoning") or None)
                    reply_saved = True
                    yield f"data: {json.dumps({'done': True, 'session_id': req.session_id, 'memories_saved': event.get('memories_saved', 0), 'retrieved_count': len(retrieved_msgs), 'retrieval_ms': round(ret_stats['latency_ms'])})}\n\n"
                elif "reasoning" in event:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif "confirm" in event:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    return
                elif "error" in event:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    return
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
    import time

    from tool_verification import run_verification
    from tools import CONFIRM_TOOLS, is_tool_success, run_tool, validate_confirm_params
    try:
        if req.tool in CONFIRM_TOOLS:
            err = validate_confirm_params(req.tool, req.params)
            if err:
                raise HTTPException(status_code=400, detail=err)
        t0 = time.perf_counter()
        try:
            result = await run_tool(req.tool, req.params, context={"user_id": req.user_id, "session_id": req.session_id})
            success = is_tool_success(result)
        except Exception as e:
            logger.error(f"Execute action error: {e}")
            result = f"ERROR: {e}"
            success = False
        duration_ms = (time.perf_counter() - t0) * 1000
        # Manual executions (confirmed destructive actions) are exactly the
        # ones that must be audit-logged — the model loop already logs its
        # own tool calls, but /execute runs outside that loop.
        await run_verification(req.tool, req.params, result, success, duration_ms=duration_ms, error=None if success else result)
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
    msgs = await get_history(session_id, limit=50, include_reasoning=True)
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

