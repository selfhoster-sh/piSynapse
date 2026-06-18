import httpx
import asyncio
import logging
import os
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  # 🎯 Added for static files management
from routers import chat
from memory import init_db
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("piSynapse")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL       = os.getenv("LLM_MODEL",       "gemma4:e2b")

# Sync runner configurations from environment variables to match llm.py settings
LLM_NUM_CTX     = int(os.getenv("LLM_NUM_CTX",    "4096"))
LLM_NUM_THREAD  = int(os.getenv("LLM_NUM_THREAD", "4"))
LLM_NUM_BATCH   = int(os.getenv("LLM_NUM_BATCH",  "256"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize database
    await init_db()
    logger.info("✅ Database ready (WAL mode active)")

    # 2. Warm up Ollama model with EXACT same runner options and tool schemas
    logger.info(f"🔄 Loading '{LLM_MODEL}' into RAM…")
    try:
        # Import TOOLS inside the function to avoid circular dependency issues
        from llm import TOOLS

        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model":      LLM_MODEL,
                    "messages":   [{"role": "user", "content": "hi"}],
                    "stream":     False,
                    "keep_alive": os.getenv("LLM_KEEP_ALIVE", "24h"),
                    "tools":      TOOLS,  # Pre-register tools to avoid initial template crash
                    "options":    {
                        "num_predict": 1,
                        "temperature": 0.2,
                        "top_p":       0.9,
                        "num_ctx":     LLM_NUM_CTX,     # Crucial fix: Must match llm.py to prevent model reload
                        "num_thread":  LLM_NUM_THREAD,  # Crucial fix: Must match llm.py to prevent model reload
                        "num_batch":   LLM_NUM_BATCH,   # Crucial fix: Must match llm.py to prevent model reload
                    },
                },
            )
        logger.info(f"✅ Model ready." if r.status_code == 200
                    else f"⚠️ Warmup HTTP {r.status_code}")
    except Exception as e:
        logger.warning(f"⚠️ Warmup failed: {e}")

    # 3. Pre-load FastEmbed so the first chat request doesn't block mid-stream
    logger.info("🔄 Loading FastEmbed model…")
    try:
        from embedding import get_model
        await asyncio.to_thread(get_model)
        logger.info("✅ FastEmbed ready.")
    except Exception as e:
        logger.warning(f"⚠️ FastEmbed loading failed: {e}")

    yield


app = FastAPI(lifespan=lifespan)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Chat Router
app.include_router(chat.router)

# 🎯 Mount the static directory to serve frontend assets (CSS, JS, icons etc.)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def read_index():
    # 🎯 Serves index.html directly from the static folder
    return FileResponse("static/index.html")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "model": LLM_MODEL}


@app.get("/config")
async def get_config():
    """Returns the .env configurations needed by the UI on startup."""
    return {
        "username":     os.getenv("ASSISTANT_USER", "User"),
        "default_city": os.getenv("DEFAULT_CITY", ""),
        "model":        LLM_MODEL,
    }


# ── Widget Endpoints ──────────────────────────────────────────────────────────

@app.get("/widget/weather")
async def widget_weather():
    """
    Sidebar weather widget.
    Fetches directly from Open-Meteo — does not invoke the LLM.
    """
    from llm import run_tool, DEFAULT_CITY
    city = DEFAULT_CITY
    if not city:
        return {"error": "DEFAULT_CITY is not set", "city": "", "summary": ""}
    try:
        summary = await run_tool("get_weather", {"city": city})
        return {"city": city, "summary": summary}
    except Exception as e:
        return {"error": str(e), "city": city, "summary": ""}


@app.get("/widget/calendar")
async def widget_calendar():
    """
    Sidebar calendar widget — returns today's events as structured data.
    Does not invoke the LLM.
    """
    from nextcloud_auth import get_nextcloud_client
    from llm import _nc_list_events_today
    client = get_nextcloud_client()
    if not client:
        return {"events": []}
    try:
        events = await asyncio.to_thread(_nc_list_events_today, client)
        return {"events": events}
    except Exception as e:
        logger.warning(f"Calendar widget error: {e}")
        return {"events": []}
