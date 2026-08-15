"""piSynapse Utilities
Shared helpers: retry decorator, text processing.
"""

import asyncio
import logging
import random
import re
import time
from functools import wraps

logger = logging.getLogger("piSynapse")


def _is_retryable(exc: BaseException) -> bool:
    """Decide whether a failed attempt should be retried.

    HTTP status errors are only retried for 429 (rate limit) and 5xx
    (server-side/transient) — a 4xx like 404 or 403 is deterministic and
    retrying would just delay the inevitable. Any other exception type is
    treated as potentially transient (network blips, timeouts, DAV errors).
    """
    try:
        import httpx
    except ImportError:
        httpx = None
    if httpx is not None and isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return True


def retry(attempts: int = 2, delay: float = 1.0, backoff: float = 2.0, jitter: float = 0.1):
    """Decorator that retries a sync or async function on exception.

    Works for both regular functions (runs in executor) and async functions.
    Wait time grows exponentially: ``delay * backoff**attempt`` plus a small
    random jitter to avoid thundering-herd retries. HTTP 4xx errors other
    than 429 are not retried (see ``_is_retryable``). Re-raises the last
    exception if all attempts fail.
    """
    def decorator(fn):
        def _wait_for(attempt: int):
            return delay * (backoff ** attempt) + random.uniform(0, jitter * delay)

        if asyncio.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_wrapper(*args, **kwargs):
                last_exc = None
                for attempt in range(attempts):
                    try:
                        return await fn(*args, **kwargs)
                    except Exception as e:
                        last_exc = e
                        if attempt >= attempts - 1 or not _is_retryable(e):
                            break
                        wait = _wait_for(attempt)
                        logger.warning(f"{fn.__name__} attempt {attempt + 1} failed: {e}; retrying in {wait:.1f}s")
                        await asyncio.sleep(wait)
                raise last_exc
            return async_wrapper
        else:
            @wraps(fn)
            def sync_wrapper(*args, **kwargs):
                last_exc = None
                for attempt in range(attempts):
                    try:
                        return fn(*args, **kwargs)
                    except Exception as e:
                        last_exc = e
                        if attempt >= attempts - 1 or not _is_retryable(e):
                            break
                        wait = _wait_for(attempt)
                        logger.warning(f"{fn.__name__} attempt {attempt + 1} failed: {e}; retrying in {wait:.1f}s")
                        time.sleep(wait)
                raise last_exc
            return sync_wrapper
    return decorator


# -- Text Processing --

def clean_body_text(text: str) -> str:
    """Collapse whitespace to reduce token usage when passing email body to LLM."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def decode_email_header(value) -> str:
    """Safely decode email header values (handles encoded UTF-8, ISO-8859, etc.)."""
    if value is None:
        return ""
    from email.header import decode_header
    parts = decode_header(value)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def sanitize_imap_query(query: str) -> str:
    """Remove characters that would break IMAP search syntax."""
    return query.replace('"', "").replace("\\", "").strip()
