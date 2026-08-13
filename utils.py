"""piSynapse Utilities
Shared helpers: retry decorator, text processing.
"""

import asyncio
import logging
import re
import time
from functools import wraps

logger = logging.getLogger("piSynapse")


def retry(attempts: int = 2, delay: float = 1.0):
    """Decorator that retries a sync or async function on exception.

    Works for both regular functions (runs in executor) and async functions.
    Re-raises the last exception if all attempts fail.
    """
    def decorator(fn):
        if asyncio.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_wrapper(*args, **kwargs):
                last_exc = None
                for attempt in range(attempts):
                    try:
                        return await fn(*args, **kwargs)
                    except Exception as e:
                        last_exc = e
                        if attempt < attempts - 1:
                            logger.warning(f"{fn.__name__} attempt {attempt + 1} failed: {e}")
                            await asyncio.sleep(delay)
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
                        if attempt < attempts - 1:
                            logger.warning(f"{fn.__name__} attempt {attempt + 1} failed: {e}")
                            time.sleep(delay)
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
