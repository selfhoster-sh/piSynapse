"""Semantic history retrieval — mitigates "lost in the middle".

Keeps the most recent messages verbatim (conversational continuity) and, for the
older messages inside the history window, retains only the top-k most relevant
to the current query via FastEmbed cosine similarity. Overlaps its own DB fetch
so it can run in parallel with get_history() without adding latency.
"""

import asyncio
import logging
import time

from config import HISTORY_LIMIT

logger = logging.getLogger("piSynapse")

RECENT_WINDOW = 8      # last N messages kept verbatim
TOP_K = 6              # most relevant older messages to retain
SIM_THRESHOLD = 0.20   # ignore older messages below this similarity
TIME_BUDGET_MS = 1500  # hard budget for the whole retrieval (wall clock)


def split_recent(history: list[dict], recent_window: int = RECENT_WINDOW):
    """Split a chronological history into (recent verbatim, older candidates)."""
    if len(history) <= recent_window:
        return history, []
    return history[-recent_window:], history[:-recent_window]


def merge_history(history: list[dict], retrieved: list[dict], recent_window: int = RECENT_WINDOW):
    """Replace the older part of history with the retrieved (relevant) subset.

    Falls back to the original history untouched when nothing was retrieved.
    """
    if not retrieved:
        return history
    recent, _ = split_recent(history, recent_window)
    return retrieved + recent


async def _fetch_candidates(session_id: str, recent_window: int = RECENT_WINDOW) -> list[dict]:
    """Older messages just before the verbatim window, chronological order."""
    limit = max(0, HISTORY_LIMIT - recent_window)
    if limit == 0:
        return []
    from db import get_db
    db = await get_db()
    async with db.execute(
        """SELECT role, content, timestamp FROM conversations
           WHERE session_id = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
        (session_id, limit, recent_window),
    ) as cur:
        rows = await cur.fetchall()
    return [
        {"role": r[0], "content": r[1], "timestamp": r[2]}
        for r in reversed(rows)
        if r[1]
    ]


async def retrieve_relevant_history(
    session_id: str,
    query: str,
    recent_window: int = RECENT_WINDOW,
    top_k: int = TOP_K,
    threshold: float = SIM_THRESHOLD,
    time_budget_ms: int = TIME_BUDGET_MS,
    query_embedding: bytes | None = None,
) -> tuple[list[dict], dict]:
    """Return (relevant older messages in chronological order, stats).

    Enforces a real wall-clock budget with asyncio.wait_for: on timeout the
    retrieval aborts and falls back to ([], stats) so it can never stall the
    request path beyond the budget. Never raises.
    """
    start = time.perf_counter()
    stats = {
        "candidates": 0, "retrieved": 0, "latency_ms": 0.0,
        "budget_ms": time_budget_ms, "timeout": False,
    }

    def _finish(picked: list[dict]) -> tuple[list[dict], dict]:
        stats["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
        logger.info(
            f"Retrieval: candidates={stats['candidates']} retrieved={stats['retrieved']} "
            f"latency={stats['latency_ms']}ms"
        )
        return picked, stats

    async def _run() -> list[dict]:
        candidates = await _fetch_candidates(session_id, recent_window)
        stats["candidates"] = len(candidates)
        if not candidates:
            return []

        from embedding import cosine_similarity, embed_batch_async

        if query_embedding is not None:
            # Query vector already computed upstream (shared with intent +
            # memory search); only the candidates need embedding.
            vecs = await embed_batch_async([m["content"] for m in candidates])
            query_vec = query_embedding
        else:
            vecs = await embed_batch_async([query] + [m["content"] for m in candidates])
            query_vec = vecs[0]
        scored = [
            (cosine_similarity(query_vec, v), m)
            for m, v in zip(candidates, vecs[1:] if query_embedding is None else vecs)
        ]
        scored = [s for s in scored if s[0] >= threshold]
        scored.sort(key=lambda s: s[0], reverse=True)
        picked = [m for _, m in scored[:top_k]]
        picked.sort(key=lambda m: m.get("timestamp") or "")
        stats["retrieved"] = len(picked)
        return picked

    try:
        if not query.strip():
            return _finish([])
        picked = await asyncio.wait_for(_run(), timeout=time_budget_ms / 1000.0)
        return _finish(picked)
    except asyncio.TimeoutError:
        stats["timeout"] = True
        logger.warning(
            f"Retrieval exceeded budget ({time_budget_ms}ms) and was aborted ({session_id})"
        )
        return _finish([])
    except Exception as e:
        logger.warning(f"Semantic history retrieval failed for {session_id}: {e}")
        return _finish([])
