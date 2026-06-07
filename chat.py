from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import re
import logging

from llm import chat_with_ollama
from memory import get_history, save_message, get_memories, save_memory, clear_history, get_all_memories

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("piSynapse")

router = APIRouter(prefix="/chat", tags=["chat"])

# Request/Response models
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str = "default_session"
    user_id: str = "default"

class ChatResponse(BaseModel):
    reply: str
    session_id: str
    history_length: int
    memories_saved: int

# Memory extraction and response cleaning
def extract_and_clean_memory(reply_text: str) -> tuple[str, list]:
    """
    Extracts MEMORY lines from model response and removes them from displayed reply.
    MEMORY lines follow the format: MEMORY: [category] content
    Returns cleaned text and list of (category, content) tuples.
    """
    memories_to_save = []
    cleaned_lines = []
    pattern = re.compile(r"MEMORY:\s*\[(.*?)\]\s*(.*)", re.IGNORECASE)

    for line in reply_text.splitlines():
        match = pattern.search(line.strip())
        if match:
            category = match.group(1).strip()
            content = match.group(2).strip()
            memories_to_save.append((category, content))
        else:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip(), memories_to_save

# Main chat endpoint
@router.post("/", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """
    Main chat endpoint: processes user message, retrieves history and memories,
    calls LLM, extracts memories from response, and stores conversation.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Store user message in session history
    await save_message(req.session_id, "user", req.message)

    # Retrieve recent conversation history and user memories
    history = await get_history(req.session_id, limit=20)
    core_memories = await get_memories(user_id=req.user_id, limit=10)

    # Get LLM response with tool calling and memory context
    raw_reply, _ = await chat_with_ollama(history, core_memories, user_id=req.user_id)

    # Parse MEMORY directives from response and clean the reply
    final_reply, memories_to_save = extract_and_clean_memory(raw_reply)

    # Store cleaned assistant response
    await save_message(req.session_id, "assistant", final_reply)

    # Persist extracted memories with semantic deduplication
    for category, content in memories_to_save:
        try:
            await save_memory(content=content, category=category, user_id=req.user_id)
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")

    return ChatResponse(
        reply=final_reply,
        session_id=req.session_id,
        history_length=len(history),
        memories_saved=len(memories_to_save)
    )

# Memory listing endpoint
@router.get("/memories")
async def list_memories(user_id: str = Query("default")):
    """Retrieves all saved long-term memories for a user."""
    try:
        memories = await get_all_memories(user_id)
        return {"user_id": user_id, "count": len(memories), "memories": memories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Session history clearing endpoint
@router.delete("/history")
async def clear_chat_history(session_id: str = Query(...)):
    """Clears all conversation history for a specific session."""
    try:
        await clear_history(session_id)
        return {"status": "success", "message": f"Session '{session_id}' cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
