from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import re
import logging

from llm import chat_with_ollama, PendingAction, run_tool, _label_tool_result
from memory import get_history, save_message, get_memories, save_memory, clear_history, get_all_memories

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("piSynapse")

router = APIRouter(prefix="/chat", tags=["chat"])

# In-memory store for pending actions awaiting user confirmation.
# Key: session_id, Value: PendingAction dict
# A simple dict is sufficient for single-user Pi deployment.
_pending_actions: dict[str, dict] = {}


# --- Request / Response models ---

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str = "default_session"
    user_id: str = "default"

class ChatResponse(BaseModel):
    reply: str
    session_id: str
    history_length: int
    memories_saved: int
    awaiting_confirmation: bool = False


# --- Memory helpers ---

def extract_and_clean_memory(reply_text: str) -> tuple[str, list]:
    """
    Extracts MEMORY: [category] content lines from the model response.
    Returns (cleaned_reply, [(category, content), ...]).
    """
    memories_to_save = []
    cleaned_lines = []
    pattern = re.compile(r"MEMORY:\s*\[(.*?)\]\s*(.*)", re.IGNORECASE)

    for line in reply_text.splitlines():
        match = pattern.search(line.strip())
        if match:
            category = match.group(1).strip()
            content = match.group(2).strip()
            if content:
                memories_to_save.append((category, content))
        else:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip(), memories_to_save


async def _persist_memories(memories_to_save: list, user_id: str) -> int:
    """Save extracted memories. Returns count of successfully saved memories."""
    saved = 0
    for category, content in memories_to_save:
        try:
            await save_memory(content=content, category=category, user_id=user_id)
            saved += 1
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
    return saved


# --- LLM-powered confirmation helpers ---
# These delegate language detection and phrasing entirely to the LLM,
# so they work in Turkish, English, or any other language automatically.

async def _llm_generate_confirmation_prompt(
    pending: PendingAction,
    history: list[dict],
    memories: list[dict],
    user_id: str,
) -> str:
    """Asks the LLM to generate a confirmation prompt in the user's language."""
    prompt = (
        f"You are about to perform the following action on behalf of the user, "
        f"but you need their explicit confirmation first.\n\n"
        f"{pending.confirmation_context}\n\n"
        f"Show the user the details of this action clearly and ask for confirmation. "
        f"Respond in the same language the user has been using. "
        f"Do NOT perform the action yet. Do NOT call any tools."
    )
    messages = history + [{"role": "user", "content": prompt}]
    reply, _ = await chat_with_ollama(messages, memories, user_id=user_id)
    return reply or "Please confirm or cancel this action."


async def _llm_detect_intent(
    user_input: str,
    history: list[dict],
    memories: list[dict],
    user_id: str,
) -> str:
    """
    Classifies the user's reply to a confirmation request.
    Returns 'yes', 'no', or 'unclear'.
    """
    prompt = (
        f"The user was asked to confirm or cancel a pending action. "
        f"Their reply was: \"{user_input}\"\n\n"
        f"Classify their intent as exactly one of: yes, no, unclear.\n"
        f"Reply with only the single word, nothing else."
    )
    messages = history + [{"role": "user", "content": prompt}]
    reply, _ = await chat_with_ollama(messages, memories, user_id=user_id)
    intent = reply.strip().lower().split()[0] if reply and reply.strip() else "unclear"
    return intent if intent in {"yes", "no"} else "unclear"


async def _llm_generate_cancel_reply(
    pending: PendingAction,
    history: list[dict],
    memories: list[dict],
    user_id: str,
) -> str:
    """Asks the LLM to acknowledge cancellation in the user's language."""
    prompt = (
        f"The user cancelled the following pending action:\n\n"
        f"{pending.confirmation_context}\n\n"
        f"Acknowledge the cancellation naturally and offer further help. "
        f"Respond in the same language the user has been using. Do NOT call any tools."
    )
    messages = history + [{"role": "user", "content": prompt}]
    reply, _ = await chat_with_ollama(messages, memories, user_id=user_id)
    return reply or "Action cancelled."


async def _llm_generate_unclear_reply(
    pending: PendingAction,
    history: list[dict],
    memories: list[dict],
    user_id: str,
) -> str:
    """Asks the LLM to re-ask for confirmation when intent was unclear."""
    prompt = (
        f"The user's reply to your confirmation request was unclear. "
        f"Re-ask them to confirm or cancel the following action:\n\n"
        f"{pending.confirmation_context}\n\n"
        f"Keep it brief. Respond in the same language the user has been using. Do NOT call any tools."
    )
    messages = history + [{"role": "user", "content": prompt}]
    reply, _ = await chat_with_ollama(messages, memories, user_id=user_id)
    return reply or "Please confirm (yes) or cancel (no)."


# --- Main chat endpoint ---

@router.post("/", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user_input = req.message.strip()

    # --- Confirmation flow ---
    if req.session_id in _pending_actions:
        pending = PendingAction.from_dict(_pending_actions[req.session_id])
        await save_message(req.session_id, "user", user_input)
        history = await get_history(req.session_id, limit=20)
        core_memories = await get_memories(user_id=req.user_id, limit=10)

        intent = await _llm_detect_intent(user_input, history, core_memories, req.user_id)

        if intent == "yes":
            del _pending_actions[req.session_id]
            tool_result = await run_tool(pending.tool_name, pending.tool_params)
            labeled = _label_tool_result(pending.tool_name, tool_result)
            logger.info(f"Confirmed: {pending.tool_name} → {tool_result[:80]}")

            summary_prompt = (
                f"Tool result: {labeled}\n\n"
                f"The user confirmed this action. Summarize what was done naturally. "
                f"Respond in the same language the user has been using."
            )
            history_with_result = history + [{"role": "user", "content": summary_prompt}]
            raw_reply, _ = await chat_with_ollama(history_with_result, core_memories, user_id=req.user_id)
            raw_reply = raw_reply or ""

            final_reply, memories_to_save = extract_and_clean_memory(raw_reply)
            await save_message(req.session_id, "assistant", final_reply)
            saved = await _persist_memories(memories_to_save, req.user_id)

            return ChatResponse(
                reply=final_reply,
                session_id=req.session_id,
                history_length=len(history),
                memories_saved=saved,
                awaiting_confirmation=False,
            )

        elif intent == "no":
            del _pending_actions[req.session_id]
            cancel_reply = await _llm_generate_cancel_reply(pending, history, core_memories, req.user_id)
            await save_message(req.session_id, "assistant", cancel_reply)
            logger.info(f"Cancelled by user: {pending.tool_name}")
            return ChatResponse(
                reply=cancel_reply,
                session_id=req.session_id,
                history_length=len(history),
                memories_saved=0,
                awaiting_confirmation=False,
            )

        else:
            unclear_reply = await _llm_generate_unclear_reply(pending, history, core_memories, req.user_id)
            await save_message(req.session_id, "assistant", unclear_reply)
            return ChatResponse(
                reply=unclear_reply,
                session_id=req.session_id,
                history_length=len(history),
                memories_saved=0,
                awaiting_confirmation=True,
            )

    # --- Normal flow ---
    await save_message(req.session_id, "user", user_input)
    history = await get_history(req.session_id, limit=20)
    core_memories = await get_memories(user_id=req.user_id, limit=10)

    raw_reply, pending_action = await chat_with_ollama(history, core_memories, user_id=req.user_id)

    if pending_action is not None:
        _pending_actions[req.session_id] = pending_action.to_dict()
        confirmation_reply = await _llm_generate_confirmation_prompt(
            pending_action, history, core_memories, req.user_id
        )
        await save_message(req.session_id, "assistant", confirmation_reply)
        history = await get_history(req.session_id, limit=20)
        return ChatResponse(
            reply=confirmation_reply,
            session_id=req.session_id,
            history_length=len(history),
            memories_saved=0,
            awaiting_confirmation=True,
        )

    # Guard: raw_reply should never be None here, but be safe
    raw_reply = raw_reply or ""
    final_reply, memories_to_save = extract_and_clean_memory(raw_reply)
    await save_message(req.session_id, "assistant", final_reply)
    saved = await _persist_memories(memories_to_save, req.user_id)

    return ChatResponse(
        reply=final_reply,
        session_id=req.session_id,
        history_length=len(history),
        memories_saved=saved,
        awaiting_confirmation=False,
    )


# --- Memory endpoint ---

@router.get("/memories")
async def list_memories(user_id: str = Query("default")):
    try:
        memories = await get_all_memories(user_id)
        return {"user_id": user_id, "count": len(memories), "memories": memories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- History endpoint ---

@router.delete("/history")
async def clear_chat_history(session_id: str = Query(...)):
    try:
        await clear_history(session_id)
        _pending_actions.pop(session_id, None)
        return {"status": "success", "message": f"Session '{session_id}' cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
