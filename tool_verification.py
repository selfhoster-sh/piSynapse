"""Tool verification hook.

Invoked after every completed tool call inside the tool-call loops
(llm/stream.py and llm/chat.py). Runs per-tool verification rules in
``_verify`` and writes an audit row to SQLite (``tool_audit_log``) via
``db.log_tool_call``. Never raises: any failure inside verification is
logged and swallowed so it can never break or stall the tool-call loop.
"""
import logging

from db import log_tool_call

logger = logging.getLogger("piSynapse")


async def run_verification(
    tool_name: str,
    params: dict,
    result: str,
    success: bool,
    *,
    duration_ms: float | None = None,
    error: str | None = None,
) -> None:
    """Verify a completed tool call and record it in the audit log.

    Deliberately async: the loops are async, and verification may need
    non-blocking I/O (the SQLite audit write). Awaited at the call site so
    verification runs in order, right after the tool completes.

    Never raises: any failure inside verification (including DB errors) is
    logged and swallowed so it can never break or stall the tool-call loop.

    Args:
        tool_name: Name of the tool that ran (e.g. "list_notes").
        params: The parsed arguments the tool received.
        result: The raw result string returned by the tool.
        success: True if the tool completed without an error, False otherwise.
        duration_ms: Wall-clock duration of the tool call, in milliseconds.
        error: Error text when the tool failed (None when successful).
    """
    try:
        _verify(tool_name, params, result, success)
        await log_tool_call(tool_name, params, success, duration_ms=duration_ms, error=error)
    except Exception as e:
        logger.warning(f"Verification hook failed for tool '{tool_name}': {e}")


def _verify(tool_name: str, params: dict, result: str, success: bool) -> None:
    """Per-tool verification rules go here later (e.g. result shape checks)."""
    logger.debug(f"Verification hook fired for tool '{tool_name}' (success={success})")
