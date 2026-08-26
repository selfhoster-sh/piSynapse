"""piSynapse Main Application
FastAPI app with lifespan, CORS, API-key auth, rate limiting, static files, and all routers.
"""

import asyncio
import contextvars
import hmac
import json
import logging
import os
import socket
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
    LLM_BACKEND,
    LLM_MODEL,
    MEDIA_MAX_MB,
    TRUST_X_FORWARDED_FOR,
    TRUSTED_HOSTS,
)
from db import close_db, get_db, init_db

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

    def allow(self, ip: str) -> tuple[bool, int]:
        """Returns (allowed, remaining). remaining = max(0, rpm - count)."""
        now = time.time()
        if now - self._last_cleanup > 60:
            self._cleanup(now)
        if len(self._buckets) >= self.max_buckets and ip not in self._buckets:
            return False, 0
        bucket = self._buckets[ip]
        cutoff = now - 60
        bucket[:] = [t for t in bucket if t > cutoff]
        remaining = max(0, self.rpm - len(bucket))
        if len(bucket) >= self.rpm:
            return False, 0
        bucket.append(now)
        return True, remaining - 1

    def remaining(self, ip: str) -> int:
        """Count remaining tokens without consuming one."""
        now = time.time()
        bucket = self._buckets.get(ip, [])
        cutoff = now - 60
        active = [t for t in bucket if t > cutoff]
        return max(0, self.rpm - len(active))

    def _cleanup(self, now: float):
        cutoff = now - 120
        empty = [ip for ip, ts in self._buckets.items() if not ts or ts[-1] < cutoff]
        for ip in empty:
            del self._buckets[ip]
        self._last_cleanup = now

_rate_limiter = _RateLimiter(rpm=30)


class _SessionRateLimiter(_RateLimiter):
    """Per-session rate limiter — same token-bucket, keyed by session_id."""

    def allow(self, session_id: str) -> tuple[bool, int]:
        return super().allow(session_id)


_session_limiter = _SessionRateLimiter(rpm=20)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not API_KEY:
        logger.warning("⚠  API_KEY is not set — all endpoints are UNPROTECTED. "
                       "Set API_KEY in .env for production use.")

    if not TRUSTED_HOSTS:
        logger.warning(
            "TRUSTED_HOSTS is not set — accepting this machine's local "
            f"hostnames/IPs only ({len(_LOCAL_TRUSTED_HOSTS)} auto-accepted). "
            "Set TRUSTED_HOSTS in .env (e.g. your LAN IP) to restrict for production."
        )

    await init_db()
    logger.info("Database ready (WAL mode active)")

    # Compress old tool-audit detail rows into daily summaries (idempotent).
    # One-shot sweep on startup (clears any backlog), then a daily background task.
    from db import periodic_cleanup_loop, periodic_rollup_loop, purge_intent_audit, rollup_tool_audit
    await rollup_tool_audit()
    await purge_intent_audit()
    rollup_task = asyncio.create_task(periodic_rollup_loop())

    # Retention sweep (conversations/memories) on a daily cadence; it also runs
    # once inside init_db() but that covers only startup-time data.
    cleanup_task = asyncio.create_task(periodic_cleanup_loop())

    # Warm up active LLM model in background
    async def _warmup():
        try:
            import httpx

            from config import LITERT_BASE_URL, LLM_BACKEND, LLM_NUM_BATCH, LLM_NUM_CTX, LLM_TOP_P, OLLAMA_BASE_URL
            # Short-lived client scoped to the warmup request (no leak).
            async with httpx.AsyncClient(timeout=120) as client:
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
                            "think": False,
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

    # Pre-warm the embedding model (used by retrieval, intent and memory
    # search). Without this the very first chat request pays the ONNX model
    # load inside the request path, inflating TTFT.
    async def _warmup_embeddings():
        try:
            from embedding import embed_async
            await embed_async("")
            logger.info("Embedding model ready (warmed up)")
        except Exception as e:
            logger.warning(f"Embedding warmup failed: {e}")
    asyncio.create_task(_warmup_embeddings())

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

    # Cancel the background loops so the app can shut down cleanly.
    for task in (rollup_task, cleanup_task):
        task.cancel()
    for task in (rollup_task, cleanup_task):
        try:
            await task
        except asyncio.CancelledError:
            pass

    await close_db()
    logger.info("Database connection closed.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    lifespan=lifespan,
    title="piSynapse",
    description=(
        "piSynapse personal AI assistant API.\n\n"
        "## Authentication\n"
        "All endpoints require `X-API-Key` header (except `/health`, `/`, `/static/*`).\n\n"
        "## Streaming (SSE)\n"
        "`POST /chat/stream` returns `text/event-stream`. Events:\n"
        "- `{token: \"...\"}` — incremental text\n"
        "- `{reasoning: \"...\"}` — thinking content (when think_mode=true)\n"
        "- `{confirm: {tool, params, preview?}}` — tool confirmation required\n"
        "- `{done: true, session_id, memories_saved}` — stream complete\n"
        "- `{error: \"...\"}` — error during stream\n\n"
        "### Reconnection\n"
        "SSE idle timeout: 300s. On disconnect, retry with exponential backoff (1s, 2s, 4s, max 30s).\n"
        "If a `done` event was not received, the last message may be partial — re-fetch history to verify.\n\n"
        "## Mobile Notes\n"
        "- Images: use `POST /chat/upload` (multipart) instead of base64 in chat body.\n"
        "- Offline: use `POST /chat/sync` to batch queue commands when reconnected.\n"
        "- Rate limits: 30 req/min per IP, 20 req/min per session."
    ),
    version="2.0.0",
    openapi_tags=[
        {"name": "chat", "description": "Core chat, streaming, and message management"},
        {"name": "sessions", "description": "Session lifecycle (create, list, rename, delete)"},
        {"name": "memories", "description": "Long-term memory management"},
        {"name": "media", "description": "Voice transcription, TTS, image upload"},
        {"name": "sync", "description": "Offline command sync (mobile)"},
        {"name": "config", "description": "Settings and configuration"},
        {"name": "widgets", "description": "Weather and calendar widgets"},
        {"name": "health", "description": "Health check"},
    ],
)

# CORS — restrict to specific origins when set, otherwise same-origin only
# allow_headers must be explicit when allow_credentials=True (spec forbids "*")
_CORS_HEADERS = ["X-API-Key", "Content-Type", "X-Request-ID", "Authorization"]
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=_CORS_HEADERS,
        allow_credentials=True,
    )
else:
    # No explicit origins — same-origin only (no cross-origin requests allowed)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=_CORS_HEADERS,
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


def _local_trusted_hosts() -> set[str]:
    """Loopback + this machine's hostname and ALL interface IPv4s (lowercased).

    Used as the safe default when TRUSTED_HOSTS is unset: accepts requests
    whose Host header is localhost or one of this machine's own addresses
    (LAN, docker, VPN), while still rejecting arbitrary external domains.
    """
    allowed = {"localhost", "127.0.0.1", "::1"}
    try:
        allowed.add(socket.gethostname().lower())
    except Exception:
        pass
    # All interface IPv4 addresses (Linux SIOCGIFADDR ioctl — no extra deps).
    try:
        import fcntl
        import struct

        for _index, name in socket.if_nameindex():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    packed = fcntl.ioctl(s.fileno(), 0x8915, struct.pack("256s", name[:15].encode("utf-8")))
                    allowed.add(socket.inet_ntoa(packed[20:24]))
                finally:
                    s.close()
            except OSError:
                continue
    except Exception:
        pass
    # Fallback: primary outbound interface address (e.g. over a VPN).
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            allowed.add(s.getsockname()[0])
        finally:
            s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if ":" not in ip or ip == "::1":
                allowed.add(ip.lower())
    except Exception:
        pass
    return allowed


_LOCAL_TRUSTED_HOSTS = _local_trusted_hosts()


@app.middleware("http")
async def trusted_host_middleware(request: Request, call_next):
    if "*" in TRUSTED_HOSTS:
        return await call_next(request)
    # Unset → auto-allow this machine's local names/IPs (safe default).
    allowed = _LOCAL_TRUSTED_HOSTS if not TRUSTED_HOSTS else {h.lower() for h in TRUSTED_HOSTS}
    host = request.headers.get("host", "").split(":")[0].lower()
    if host and host not in allowed:
        return JSONResponse(status_code=403, content={"detail": "Invalid Host header"})
    return await call_next(request)


# ── Middleware: API Key auth + Rate limiting + Body size ───────────────────────

_MAX_BODY_BYTES = 4 * 1024 * 1024  # 4 MB
_DEBUG_MAX_BODY_BYTES = 8 * 1024    # debug beacons are tiny telemetry payloads


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path

    # --- Skip auth for exempt paths ---
    is_exempt = path == "/health" or path == "/" or path == "/favicon.ico" or path == "/sw.js" or path.startswith("/static")

    # --- Skip auth for CORS preflight (HEAD/OPTIONS never carry API key) ---
    if request.method in ("HEAD", "OPTIONS"):
        is_exempt = True

    # --- Debug beacon: navigator.sendBeacon cannot set headers, so it
    # authenticates via the ?k= query param (still protected by API_KEY).
    # Always require auth for /debug — never leave it open. ---
    is_debug = path == "/debug"
    if is_debug:
        if not API_KEY:
            return JSONResponse(status_code=403, content={"detail": "Debug endpoint disabled: API_KEY not configured"})
        key = request.query_params.get("k", "")
        if not hmac.compare_digest(key, API_KEY):
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

    # --- API Key verification ---
    if API_KEY and not is_exempt and not is_debug:
        key = request.headers.get("x-api-key", "")
        if not hmac.compare_digest(key, API_KEY):
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

    # --- Rate limiting ---
    client_ip = None
    if not is_exempt or is_debug:
        if TRUST_X_FORWARDED_FOR:
            client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        else:
            # Default: never trust the spoofable X-Forwarded-For header.
            client_ip = request.client.host if request.client else "unknown"
        if not client_ip:
            client_ip = "unknown"
        allowed, remaining = _rate_limiter.allow(client_ip)
        if not allowed:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again later."},
                               headers={"Retry-After": "60", "X-RateLimit-Limit": str(_rate_limiter.rpm), "X-RateLimit-Remaining": "0"})

    # --- Body size limit ---
    # Only the transcription endpoints accept larger payloads (audio recordings);
    # everything else (chat text, TTS text, config JSON) stays at the 4 MB cap.
    # Exact match, not prefix: "/chat" must not widen the limit for sub-routes.
    _large_body_paths = frozenset({"/chat/transcribe", "/chat/transcribe-gemma4"})
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
            if is_debug:
                limit = _DEBUG_MAX_BODY_BYTES
            elif request.url.path in _large_body_paths:
                limit = MEDIA_MAX_MB * 1024 * 1024
            else:
                limit = _MAX_BODY_BYTES
            limit_str = f"{limit // (1024 * 1024)} MB" if limit >= 1024 * 1024 else f"{limit // 1024} KB"
            if body_size > limit:
                return JSONResponse(status_code=413, content={"detail": f"Request body too large (max {limit_str})"})

    response = await call_next(request)
    if client_ip:
        rem = _rate_limiter.remaining(client_ip)
        response.headers["X-RateLimit-Limit"] = str(_rate_limiter.rpm)
        response.headers["X-RateLimit-Remaining"] = str(rem)
    return response


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


@app.get("/sw.js")
async def service_worker():
    return FileResponse("static/sw.js", media_type="application/javascript")


@app.get("/health")
async def health_check():
    return await collect_health()


async def _check_db() -> str:
    """Return 'ok' when the database answers a trivial query, else 'error'."""
    try:
        db = await get_db()
        cur = await db.execute("SELECT 1")
        await cur.fetchone()
        return "ok"
    except Exception as e:
        logger.warning(f"Health: db check failed: {e}")
        return "error"


async def _check_llm() -> str:
    """Ping the active LLM backend (LiteRT or Ollama) with a short timeout."""
    try:
        import httpx

        from config import LITERT_BASE_URL, OLLAMA_BASE_URL
        url = f"{LITERT_BASE_URL}/v1/models" if LLM_BACKEND == "litert" else f"{OLLAMA_BASE_URL}/api/tags"
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url)
        return "ok" if r.status_code < 500 else "error"
    except Exception as e:
        logger.warning(f"Health: llm check failed: {e}")
        return "error"


async def _check_nextcloud() -> str:
    """Ping Nextcloud's status.php; 'disabled' when not configured (optional dep)."""
    from config import NEXTCLOUD_URL
    if not NEXTCLOUD_URL:
        return "disabled"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{NEXTCLOUD_URL.rstrip('/')}/status.php")
        return "ok" if r.status_code < 500 else "error"
    except Exception as e:
        logger.warning(f"Health: nextcloud check failed: {e}")
        return "error"


async def collect_health() -> dict:
    """Aggregate critical dependency statuses into a single health payload.

    'disabled' dependencies (optional, e.g. Nextcloud when not configured)
    are excluded from the overall healthy/degraded decision.
    """
    deps = {
        "db": await _check_db(),
        "llm": await _check_llm(),
        "nextcloud": await _check_nextcloud(),
    }
    configured = {k: v for k, v in deps.items() if v != "disabled"}
    degraded = any(v != "ok" for v in configured.values())
    return {
        "status": "degraded" if degraded else "healthy",
        "model": LLM_MODEL,
        "dependencies": deps,
    }


@app.post("/debug")
async def debug_ingest(request: Request):
    try:
        body = await request.json()
        print(f"DBG|{json.dumps(body, ensure_ascii=False)[:2000]}")
    except Exception as e:
        print(f"DBG|bad payload: {e}")
    return {"ok": True}


# NOTE: CalDAV client (calendar_ops.py, nextcloud_tasks.py) holds credentials
# in memory. Never log the client object directly — only log exception messages.
# The caldav library's __repr__ may include connection details.
