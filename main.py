"""piSynapse Main Application
FastAPI app with lifespan, CORS, API-key auth, rate limiting, static files, and all routers.
"""

import asyncio
import contextvars
import hmac
import logging
import os
import time
import uuid as _uuid
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import (
    API_KEY,
    CORS_ORIGINS,
    LLM_MODEL,
    MEDIA_MAX_MB,
    TRUST_X_FORWARDED_FOR,
    TRUSTED_HOSTS,
)
from db import close_db, init_db

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_OLD_FACTORY = logging.getLogRecordFactory()
def _log_factory(*args, **kwargs):
    record = _OLD_FACTORY(*args, **kwargs)
    record.request_id = _request_id_var.get()
    return record
logging.setLogRecordFactory(_log_factory)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s",
)
logger = logging.getLogger("piSynapse")


# ── Rate Limiter ──────────────────────────────────────────────────────────────

class _RateLimiter:
    """Per-IP token bucket rate limiter."""

    def __init__(self, rpm: int = 30, max_buckets: int = 10000):
        self.rpm = rpm
        self.max_buckets = max_buckets
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()

    def allow(self, ip: str) -> bool:
        now = time.time()
        if now - self._last_cleanup > 60:
            self._cleanup(now)
        # Evict oldest entry if bucket limit reached (prevents unbounded growth)
        if len(self._buckets) >= self.max_buckets and ip not in self._buckets:
            return False
        bucket = self._buckets[ip]
        cutoff = now - 60
        bucket[:] = [t for t in bucket if t > cutoff]
        if len(bucket) >= self.rpm:
            return False
        bucket.append(now)
        return True

    def _cleanup(self, now: float):
        cutoff = now - 120
        empty = [ip for ip, ts in self._buckets.items() if not ts or ts[-1] < cutoff]
        for ip in empty:
            del self._buckets[ip]
        self._last_cleanup = now

_rate_limiter = _RateLimiter(rpm=30)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not API_KEY:
        logger.warning("⚠  API_KEY is not set — all endpoints are UNPROTECTED. "
                       "Set API_KEY in .env for production use.")

    await init_db()
    logger.info("Database ready (WAL mode active)")

    # Warm up active LLM model in background
    async def _warmup():
        try:
            import httpx

            from config import LITERT_BASE_URL, LLM_BACKEND, LLM_NUM_BATCH, LLM_NUM_CTX, LLM_TOP_P, OLLAMA_BASE_URL
            client = httpx.AsyncClient(timeout=120)
            if LLM_BACKEND == "litert":
                logger.info(f"Warming up LiteRT model '{LLM_MODEL}'...")
                r = await client.post(
                    f"{LITERT_BASE_URL}/v1/chat/completions",
                    json={
                        "model": LLM_MODEL.replace(":", "-"),
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 1,
                        "temperature": 0.2,
                        "stream": False,
                    },
                    timeout=60,
                )
                logger.info("LiteRT model ready."
                            if r.status_code == 200
                            else f"LiteRT warmup HTTP {r.status_code}")
            else:
                logger.info(f"Warming up Ollama model '{LLM_MODEL}'...")
                from tools import TOOLS
                r = await client.post(
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": LLM_MODEL,
                        "messages": [{"role": "user", "content": "hi"}],
                        "stream": False,
                        "keep_alive": os.getenv("LLM_KEEP_ALIVE", "4h"),
                        "tools": TOOLS,
                        "options": {
                            "num_predict": 1,
                            "temperature": 0.2,
                            "top_p": LLM_TOP_P,
                            "num_ctx": LLM_NUM_CTX,
                            "num_batch": LLM_NUM_BATCH,
                        },
                    },
                    timeout=120,
                )
                logger.info("Ollama model ready."
                            if r.status_code == 200
                            else f"Ollama warmup HTTP {r.status_code}")
        except Exception as e:
            logger.warning(f"Warmup failed: {e}")

    asyncio.create_task(_warmup())

    # Check transcription dependencies
    import shutil as _shutil
    if _shutil.which("ffmpeg"):
        logger.info("ffmpeg: available")
    else:
        logger.warning("ffmpeg: NOT FOUND — gemma4 audio transcription will be unavailable")

    # Pre-load Whisper model in background
    async def _preload_whisper():
        try:
            from routers.media import _get_whisper
            model = await asyncio.to_thread(_get_whisper)
            if model:
                logger.info("Whisper model ready (transcription available)")
            else:
                logger.warning("Whisper model unavailable — install faster-whisper or openai-whisper")
        except Exception as e:
            logger.warning(f"Whisper preload failed: {e}")
    asyncio.create_task(_preload_whisper())

    yield

    await close_db()
    logger.info("Database connection closed.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(lifespan=lifespan)

# CORS — restrict to specific origins when set, otherwise same-origin only
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
        allow_credentials=True,
    )
else:
    # No explicit origins — same-origin only (no cross-origin requests allowed)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
        allow_credentials=True,
    )


# ── Middleware: Request ID + Trusted Host + API Key auth + Rate limiting + Body size ──


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("x-request-id") or str(_uuid.uuid4())
    token = _request_id_var.set(rid)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        _request_id_var.reset(token)


@app.middleware("http")
async def trusted_host_middleware(request: Request, call_next):
    if "*" in TRUSTED_HOSTS:
        return await call_next(request)
    host = request.headers.get("host", "").split(":")[0]
    if host and host not in TRUSTED_HOSTS:
        return JSONResponse(status_code=403, content={"detail": "Invalid Host header"})
    return await call_next(request)


# ── Middleware: API Key auth + Rate limiting + Body size ───────────────────────

_MAX_BODY_BYTES = 4 * 1024 * 1024  # 4 MB


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path

    # --- Skip auth for exempt paths ---
    is_exempt = path == "/health" or path == "/" or path == "/favicon.ico" or path.startswith("/static")

    # --- Skip auth for CORS preflight (HEAD/OPTIONS never carry API key) ---
    if request.method in ("HEAD", "OPTIONS"):
        is_exempt = True

    # --- API Key verification ---
    if API_KEY and not is_exempt:
        key = request.headers.get("x-api-key", "")
        if not hmac.compare_digest(key, API_KEY):
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

    # --- Rate limiting ---
    if not is_exempt:
        if TRUST_X_FORWARDED_FOR:
            client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        else:
            # Default: never trust the spoofable X-Forwarded-For header.
            client_ip = request.client.host if request.client else "unknown"
        if not client_ip:
            client_ip = "unknown"
        if not _rate_limiter.allow(client_ip):
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again later."})

    # --- Body size limit ---
    # Paths that accept larger payloads (audio recordings, image uploads)
    _large_body_paths = ("/chat", "/chat/transcribe", "/chat/transcribe-gemma4", "/chat/tts")
    if request.method in ("POST", "PATCH"):
        te = request.headers.get("transfer-encoding", "")
        if "chunked" in te.lower():
            return JSONResponse(status_code=413, content={"detail": "Chunked transfer encoding not allowed"})
        cl = request.headers.get("content-length")
        if cl:
            try:
                body_size = int(cl)
            except (ValueError, TypeError):
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header"})
            limit = MEDIA_MAX_MB * 1024 * 1024 if request.url.path.startswith(_large_body_paths) else _MAX_BODY_BYTES
            if body_size > limit:
                return JSONResponse(status_code=413, content={"detail": f"Request body too large (max {limit // (1024*1024)} MB)"})

    return await call_next(request)


# ── Routers ───────────────────────────────────────────────────────────────────

from routers.chat import router as chat_router
from routers.config import router as config_router
from routers.media import router as media_router
from routers.widgets import router as widgets_router

app.include_router(chat_router)
app.include_router(config_router)
app.include_router(widgets_router)
app.include_router(media_router)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def read_index():
    return FileResponse("static/index.html")


@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/icons/favicon.ico", media_type="image/x-icon")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "model": LLM_MODEL}
