"""piSynapse Main Application
FastAPI app with lifespan, CORS, API-key auth, rate limiting, static files, and all routers.
"""

import asyncio
import contextvars
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
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from config import (
    API_KEY,
    CORS_ORIGINS,
    LLM_BACKEND,
    LLM_MODEL,
    MEDIA_MAX_MB,
    RATE_LIMIT_PUBLIC_RPM,
    RATE_LIMIT_RPM,
    RATE_LIMIT_SESSION_RPM,
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

_rate_limiter = _RateLimiter(rpm=RATE_LIMIT_RPM)


_session_limiter = _RateLimiter(rpm=RATE_LIMIT_SESSION_RPM)


# Exempt paths (health/static) get their own lenient bucket: still bounded
# against L7 floods, far above any legitimate poller.
_public_limiter = _RateLimiter(rpm=RATE_LIMIT_PUBLIC_RPM)


# Set when lifespan startup cannot initialize the database. The app keeps
# serving so /health reports the condition instead of crash-looping blindly.
DB_DEGRADED: str | None = None


def _effective_trusted_hosts() -> set[str]:
    """Resolve the Host allowlist, refusing to disable the check.

    A literal "*" in TRUSTED_HOSTS is rejected with an error log and ignored
    (falls back to local-only) instead of turning Host validation off.
    """
    trusted = {h for h in TRUSTED_HOSTS if h != "*"}
    if "*" in TRUSTED_HOSTS:
        logger.error("TRUSTED_HOSTS contains '*': refusing to disable Host checking; wildcard ignored.")
    return _LOCAL_TRUSTED_HOSTS if not trusted else {h.lower() for h in trusted}


def _validate_cors_origins(origins: list[str]) -> None:
    """Fail fast on a credentialed wildcard (spec violation + CSRF risk)."""
    if "*" in (origins or []):
        raise RuntimeError("CORS_ORIGINS must not contain '*': allow_credentials=True forbids wildcards.")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not API_KEY:
        logger.warning(
            "⚠  API_KEY is not set — the API now runs FAIL-CLOSED: every "
            "non-public endpoint returns 503 until you set API_KEY in .env "
            "(generate one with the installer or `python -c 'import secrets; "
            "print(secrets.token_urlsafe(32))'`)."
        )

    if not TRUSTED_HOSTS:
        logger.warning(
            "TRUSTED_HOSTS is not set — accepting this machine's local "
            f"hostnames/IPs only ({len(_LOCAL_TRUSTED_HOSTS)} auto-accepted). "
            "Set TRUSTED_HOSTS in .env (e.g. your LAN IP) to restrict for production."
        )

    global DB_DEGRADED
    try:
        await init_db()
        logger.info("Database ready (WAL mode active)")
    except Exception as e:
        # Fail visible, not silent: serve degraded so /health reports the
        # condition (with recovery hint) instead of crash-looping.
        DB_DEGRADED = f"{type(e).__name__}: {e}"
        logger.critical(
            "Database init failed — serving DEGRADED. Recovery: restore "
            "backups/piSynapse-auto-*.db over assistant.db and restart. Error: %s",
            e,
        )
    else:
        # Bind the pre-existing `.env` key holder as admin (idempotent;
        # zero data rewrites — existing rows already point at 'default').
        try:
            from db import ensure_default_admin, seed_admin_settings

            admin = await ensure_default_admin()
            if admin is not None:
                logger.info("Admin bootstrapped onto the default identity.")
            seeded = await seed_admin_settings()
            if seeded:
                logger.info(f"Migrated {seeded} personal setting(s) from .env to the admin profile.")
        except Exception as e:
            logger.warning(f"Admin bootstrap skipped: {e}")
        try:
            from db import db_quick_check

            problem = await db_quick_check()
            if problem is not None:
                DB_DEGRADED = problem
                logger.critical(
                    "Database integrity check failed — serving DEGRADED. "
                    "Recovery: see docs/backup-restore.md. Detail: %s", problem,
                )
        except Exception as e:
            logger.warning(f"Integrity check skipped: {e}")
    # Baseline online backup at startup (best-effort, never blocks boot).
    try:
        from db import auto_backup_db

        backup_path = await auto_backup_db()
        if backup_path:
            logger.info(f"Startup DB backup: {backup_path}")
    except Exception as e:
        logger.warning(f"Startup backup skipped: {e}")

    # Embedding dimension drift guard (Faz 2): stored vectors written by a
    # different model than the configured one silently zero out cosine scores.
    # Best-effort, never blocks startup.
    try:
        from config import EMBED_MODEL
        from db import get_db as _dim_get_db
        _dim_db = await _dim_get_db()
        _dim_row = await (
            await _dim_db.execute(
                "SELECT embedding FROM conversations "
                "WHERE embedding IS NOT NULL LIMIT 1"
            )
        ).fetchone()
        if _dim_row is None:
            _dim_row = await (
                await _dim_db.execute(
                    "SELECT embedding FROM memories "
                    "WHERE embedding IS NOT NULL LIMIT 1"
                )
            ).fetchone()
        if _dim_row is not None and _dim_row[0]:
            _stored_dim = len(bytes(_dim_row[0])) // 4
            _lname = str(EMBED_MODEL).lower()
            _expected = (
                384 if "minilm" in _lname else (768 if "mpnet" in _lname else None)
            )
            if _expected is not None and _stored_dim != _expected:
                logger.warning(
                    "Embedding dimension drift: stored vectors are %d-dim but "
                    "EMBED_MODEL '%s' produces %d-dim. Run reembed_all.py, "
                    "otherwise retrieval/memory similarity silently returns 0.",
                    _stored_dim, EMBED_MODEL, _expected,
                )
    except Exception as _dim_e:
        logger.warning(f"Embedding dimension check skipped: {_dim_e}")

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
    background_tasks = [
        asyncio.create_task(_warmup()),
        asyncio.create_task(_warmup_embeddings()),
        asyncio.create_task(_preload_whisper()),
    ]

    yield

    # Cancel the background loops so the app can shut down cleanly.
    for task in (rollup_task, cleanup_task, *background_tasks):
        task.cancel()
    for task in (rollup_task, cleanup_task, *background_tasks):
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
    version="1.7.2",
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
_validate_cors_origins(CORS_ORIGINS)
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
    # Unset → auto-allow this machine's local names/IPs (safe default).
    allowed = _effective_trusted_hosts()
    host = request.headers.get("host", "").split(":")[0].lower()
    if not host or host not in allowed:
        return JSONResponse(status_code=403, content={"detail": "Invalid Host header"})
    return await call_next(request)


# ── Middleware: hardening response headers ─────────────────────────────────────

@app.middleware("http")
async def hardening_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
    )
    # HSTS only over HTTPS — harmless if absent over plaintext HTTP.
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# ── Middleware: API Key auth + Rate limiting + Body size ───────────────────────

_MAX_BODY_BYTES = 4 * 1024 * 1024  # 4 MB
_DEBUG_MAX_BODY_BYTES = 8 * 1024    # debug beacons are tiny telemetry payloads


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path

    # --- Skip auth for exempt paths ---
    is_exempt = path == "/health" or path == "/" or path == "/favicon.ico" or path == "/sw.js" or path.startswith("/static")
    # Credential-issuing endpoints cannot require credentials — but they stay
    # under the STRICT rate limiter (not the lenient public bucket) as
    # anti-enumeration/brute-force hardening.
    is_public_auth = path in ("/users/register", "/users/login") and request.method == "POST"

    # --- Skip auth for CORS preflight (only OPTIONS with Access-Control-Request-Method) ---
    if request.method == "OPTIONS" and "access-control-request-method" in request.headers:
        is_exempt = True

    # --- Debug beacon: sendBeacon cannot set headers, so the key travels
    # in the JSON body as _k. The legacy ?k= query param was removed: keys
    # in URLs leak into logs/proxies (audit Y22).
    # Always require auth for /debug — never leave it open. ---
    is_debug = path == "/debug"
    if is_debug:
        from db import count_users, resolve_user_by_key

        try:
            has_users = await count_users() > 0
        except Exception:
            has_users = False
        if not API_KEY and not has_users:
            return JSONResponse(status_code=403, content={"detail": "Debug endpoint disabled: no credentials configured"})
        key = request.headers.get("x-api-key", "")
        if not key:
            # Try JSON body (_k from sendBeacon)
            try:
                body = await request.body()
                if body:
                    import json as _json
                    data = _json.loads(body.decode())
                    key = data.get("_k", "") or data.get("k", "")
            except Exception:
                pass
        if await resolve_user_by_key(key) is None:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

    # --- API Key verification (DB users + legacy .env key; unknown -> 401) ---
    if not is_exempt and not is_debug and not is_public_auth:
        from db import count_users, resolve_user_by_key

        user = await resolve_user_by_key(request.headers.get("x-api-key", ""))
        if user is None:
            # Fail-closed misconfiguration signal only when NOTHING could
            # authenticate (no .env key and no registered users at all).
            try:
                configured = bool(API_KEY) or await count_users() > 0
            except Exception:
                configured = bool(API_KEY)
            if not configured:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Server misconfigured: no credentials set. Register the first user or set API_KEY in .env."},
                )
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
        # Resolve API key → user for downstream handlers/db queries.
        request.state.user_id = user["id"]
        request.state.is_admin = bool(user.get("is_admin"))

    # --- Rate limiting ---
    # Authenticated routes bucket by user (multi-user): NAT-shared IPs must
    # not share quota. Exempt paths use the separate lenient IP bucket.
    if TRUST_X_FORWARDED_FOR:
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    else:
        # Default: never trust the spoofable X-Forwarded-For header.
        client_ip = request.client.host if request.client else "unknown"
    if not client_ip:
        client_ip = "unknown"
    if not is_exempt or is_debug:
        limiter = _rate_limiter
        who = getattr(request.state, "user_id", None)
        bucket = f"user:{who}" if who else f"ip:{client_ip}"
    else:
        limiter = _public_limiter
        bucket = f"ip:{client_ip}"
    allowed, remaining = limiter.allow(bucket)
    if not allowed:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again later."},
                           headers={"Retry-After": "60", "X-RateLimit-Limit": str(limiter.rpm), "X-RateLimit-Remaining": "0"})

    # --- Body size limit ---
    # Only the transcription endpoints accept larger payloads (audio recordings);
    # everything else (chat text, TTS text, config JSON) stays at the 4 MB cap.
    # Exact match, not prefix: "/chat" must not widen the limit for sub-routes.
    _large_body_paths = frozenset({"/chat/transcribe", "/chat/transcribe-gemma4", "/chat/upload"})
    if request.method in ("POST", "PATCH"):
        te = request.headers.get("transfer-encoding", "")
        if "chunked" in te.lower():
            return JSONResponse(status_code=413, content={"detail": "Chunked transfer encoding not allowed"})
        cl = request.headers.get("content-length")
        if cl is None:
            return JSONResponse(status_code=411, content={"detail": "Content-Length required"})
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
    if bucket:
        rem = limiter.remaining(bucket)
        response.headers["X-RateLimit-Limit"] = str(limiter.rpm)
        response.headers["X-RateLimit-Remaining"] = str(rem)
    return response


# ── Routers ───────────────────────────────────────────────────────────────────

from routers.chat import router as chat_router
from routers.config import router as config_router
from routers.media import router as media_router
from routers.tools import router as tools_router
from routers.users import router as users_router
from routers.widgets import router as widgets_router

app.include_router(chat_router)
app.include_router(users_router)
app.include_router(config_router)
app.include_router(tools_router)
app.include_router(widgets_router)
app.include_router(media_router)

# Mount static files. html=True makes the dir index serve index.html so the
# SPA's relative asset paths (fonts/vendor/icons/manifest) resolve under
# /static/ — identical to the WebView's public/ root.
app.mount("/static", StaticFiles(directory="static", html=True), name="static")


@app.get("/")
async def read_index():
    # Redirect the root to /static/ so relative asset references resolve
    # against /static/ in a browser (the WebView bundles assets at its root).
    return RedirectResponse("/static/", status_code=307)


@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/icons/favicon.ico", media_type="image/x-icon")


@app.get("/sw.js")
async def service_worker():
    return FileResponse("static/sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})


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
    degraded = any(v != "ok" for v in configured.values()) or DB_DEGRADED is not None
    payload = {
        "status": "degraded" if degraded else "healthy",
        "model": LLM_MODEL,
        "dependencies": deps,
    }
    if DB_DEGRADED is not None:
        payload["startup_error"] = DB_DEGRADED
    return payload


@app.post("/debug")
async def debug_ingest(request: Request):
    try:
        body = await request.json()
        # Never persist the API key or client PII: drop auth fields, redact
        # sensitive values, truncate the rest, and log at debug level only
        # (INFO journals must not accumulate beacon payloads).
        body.pop("_k", None)
        body.pop("k", None)
        logger.debug("DBG|%s", json.dumps(_redact_debug_body(body), ensure_ascii=False)[:1000])
    except Exception as e:
        logger.debug("DBG|bad payload: %s", e)
    return {"ok": True}


_DEBUG_SENSITIVE_HINTS = (
    "password", "token", "secret", "credential", "auth", "api_key",
    "mail", "body", "content", "message", "prompt", "subject",
)


def _redact_debug_body(body):
    """Redact a debug-beacon payload for logging (PII-safe)."""
    if isinstance(body, dict):
        out = {}
        for k, v in body.items():
            kl = str(k).lower()
            if kl in ("_k", "k") or any(h in kl for h in _DEBUG_SENSITIVE_HINTS):
                out[k] = "[REDACTED]"
            else:
                out[k] = _redact_debug_body(v)
        return out
    if isinstance(body, list):
        return [_redact_debug_body(v) for v in body[:20]]
    if isinstance(body, (bool, int, float)) or body is None:
        return body
    return str(body)[:120]


# NOTE: CalDAV client (calendar_ops.py, nextcloud_tasks.py) holds credentials
# in memory. Never log the client object directly — only log exception messages.
# The caldav library's __repr__ may include connection details.
