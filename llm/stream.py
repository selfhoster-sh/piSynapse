"""SSE streaming chat handler. Manages tool-call loops, token buffering, and TTFT."""
import asyncio
import json
import logging
import re
import time

from config import (
    LITERT_BASE_URL,
    OLLAMA_BASE_URL,
    get,
)
from tool_verification import run_verification
from tools import (
    CONFIRM_TOOLS,
    get_tools_for_group,
    is_tool_success,
    parse_tool_args,
    run_tool,
    validate_confirm_params,
)

from .payload import _build_full_messages, _build_payload, _normalize_messages_for_backend, trim_messages_for_context
from .utils import _check_tool_leak, _get_client, clean_reasoning, parse_leaked_tool_call, strip_tool_leaks

logger = logging.getLogger("piSynapse")

EARLY_BUFFER_CHARS = 8

TRUNCATION_RETRY_NOTE = (
    "\n\n[Note: The previous reply was cut off mid-answer. "
    "Continue where you left off and COMPLETE the answer fully "
    "without stopping early. Do not repeat items already listed.]"
)


def _looks_truncated(text: str) -> bool:
    """Heuristic: True when the reply ends at a dangling list marker (e.g. '4.')"""
    if not text:
        return False
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    return bool(re.match(r"^\d+\.\s*$", lines[-1].strip()))


async def _iter_sse_lines(resp, idle_timeout: float):
    """Yield decoded lines from an httpx streaming response.

    Each chunk read is bounded by ``idle_timeout`` — if the server sends no
    bytes for that long (silent hang mid-stream), the generator stops so the
    client never stalls indefinitely on a dead connection.
    """
    it = resp.aiter_bytes()
    buf = b""
    while True:
        try:
            chunk = await asyncio.wait_for(it.__anext__(), timeout=idle_timeout)
        except asyncio.TimeoutError:
            logger.warning(f"SSE stream idle timeout — no data for {idle_timeout}s, aborting stream")
            break
        except StopAsyncIteration:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            yield line.decode("utf-8", errors="replace")
    if buf:
        yield buf.decode("utf-8", errors="replace")


def _merge_tool_calls(acc: list, tc: list) -> list:
    """Merge streaming tool-call deltas by index.

    OpenAI-style (LiteRT) streams send tool calls as incremental deltas:
    the first chunk carries the id/name, later chunks carry fragments of
    the arguments JSON. Overwriting the accumulator each chunk would lose
    the id/name and truncate arguments, so merge by ``index``. Ollama-style
    streams send complete tool-call lists, which replace the accumulator.
    """
    if not tc:
        return acc
    if any(c.get("index") is None for c in tc):
        return tc
    for call in tc:
        idx = call.get("index", 0)
        while len(acc) <= idx:
            acc.append({})
        target = acc[idx]
        for k, v in call.items():
            if k == "index":
                continue
            if k == "function" and isinstance(v, dict):
                fn = target.setdefault("function", {})
                for fk, fv in v.items():
                    if fk == "arguments" and isinstance(fv, str):
                        fn["arguments"] = fn.get("arguments", "") + fv
                    else:
                        fn[fk] = fv
            elif v is not None:
                target[k] = v
    return acc


def _is_context_overflow(err: Exception) -> bool:
    msg = str(err).lower()
    return any(k in msg for k in ("token", "too long", "context", "invalid_argument"))


def _shrink_tool_responses(current_msgs: list[dict]) -> None:
    """Truncate tool responses so the prompt fits the model's context window."""
    for m in current_msgs:
        if m.get("role") == "tool" and isinstance(m.get("content"), str) and len(m["content"]) > 600:
            m["content"] = m["content"][:600] + "\n[content truncated]"


async def chat_with_ollama_stream(
    messages: list[dict],
    *,
    memories: list[dict] | None = None,
    think: bool = False,
    summary: str = "",
    user_id: str | None = None,
    session_id: str = "",
    intent: str = "action",
    tool_group: str | None = None,
    reasoning_effort: str = "",
):
    full_msgs = await _build_full_messages(messages, memories or [], summary, session_id, tool_group=tool_group)
    context = {"user_id": user_id, "session_id": session_id}
    current_msgs: list[dict] = []
    memories_saved = 0
    client = _get_client()
    backend = get("LLM_BACKEND", "litert")

    from tools import get_combined_tools
    if intent == "question" and tool_group is None:
        use_tools = False
        filtered_tools = None
        logger.info("Pure chat (question+None) — tools disabled")
    else:
        use_tools = True
        if tool_group:
            filtered_tools = get_tools_for_group(tool_group)
            logger.info(f"Tool group: {tool_group} ({len(filtered_tools)} tools)")
        else:
            filtered_tools = get_combined_tools()
            logger.info(f"No specific group — sending combined tools ({len(filtered_tools)} tools)")

    executed_tool_sigs: set[str] = set()
    truncation_retried = False
    overflow_retried = False

    for iteration in range(get("LLM_MAX_TOOL_ITERATIONS", 5)):
        if truncation_retried:
            use_tools = False
            filtered_tools = None
        tools_tokens = 0
        if use_tools and filtered_tools:
            tools_tokens = len(json.dumps(filtered_tools, ensure_ascii=False)) // 4
        if backend == "litert":
            payload = _build_payload(
                trim_messages_for_context(
                    _normalize_messages_for_backend(full_msgs + current_msgs, backend="litert"),
                    context_window=int(get("LLM_NUM_CTX", 6144)),
                    reserved_output=int(get("LLM_MAX_OUTPUT_TOKENS", 2048)),
                    tools_tokens=tools_tokens,
                ),
                stream=True, think=think, use_tools=use_tools, tool_list=filtered_tools, backend="litert",
                reasoning_effort=reasoning_effort,
            )
            url = f"{LITERT_BASE_URL}/v1/chat/completions"
        else:
            payload = _build_payload(
                trim_messages_for_context(
                    full_msgs + current_msgs,
                    context_window=int(get("LLM_NUM_CTX", 6144)),
                    reserved_output=int(get("LLM_MAX_OUTPUT_TOKENS", 2048)),
                    tools_tokens=tools_tokens,
                ),
                stream=True, think=think, use_tools=use_tools, tool_list=filtered_tools, reasoning_effort=reasoning_effort,
            )
            url = f"{OLLAMA_BASE_URL}/api/chat"

        buf = ""
        full_text = ""
        full_reasoning = ""
        early_buf_flushed = False
        tool_calls_acc: list = []
        done_reason = None
        suppressing = False

        try:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for raw in _iter_sse_lines(resp, get("SSE_READ_IDLE_TIMEOUT", 300.0)):
                    if not raw:
                        continue

                    if backend == "litert":
                        if raw.startswith("data: "):
                            raw = raw[6:]
                        if raw == "[DONE]":
                            break
                        if not raw:
                            continue
                        try:
                            chunk = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if chunk.get("error"):
                            err = chunk["error"]
                            if isinstance(err, dict):
                                err = err.get("message", str(err))
                            raise RuntimeError(f"litert stream error: {err}")
                        choice = chunk.get("choices", [{}])[0]
                        delta = choice.get("delta", {})
                        token = delta.get("content", "")
                        reasoning_token = delta.get("reasoning_content") or ""
                        tc = delta.get("tool_calls")
                        finish = choice.get("finish_reason")
                        if finish:
                            done_reason = finish
                    else:
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        msg = data.get("message", {})
                        token = msg.get("content", "")
                        reasoning_token = msg.get("reasoning_content", "") or ""
                        tc = msg.get("tool_calls")
                        done = data.get("done", False)
                        if done:
                            done_reason = data.get("done_reason")

                    if tc:
                        tool_calls_acc = _merge_tool_calls(tool_calls_acc, tc)

                    if reasoning_token:
                        full_reasoning += reasoning_token
                        if not tool_calls_acc:
                            yield {"reasoning": reasoning_token}

                    if token:
                        full_text += token
                        if not suppressing and not tool_calls_acc:
                            if _check_tool_leak(full_text) or _check_tool_leak(buf + token):
                                suppressing = True
                                logger.info("Tool call pattern detected mid-stream, suppressing output")
                        if suppressing:
                            pass
                        elif not early_buf_flushed:
                            buf += token
                            if not tool_calls_acc and (len(buf) >= EARLY_BUFFER_CHARS or done_reason):
                                early_buf_flushed = True
                                if buf:
                                    yield {"token": buf}
                                    buf = ""
                            elif tool_calls_acc:
                                early_buf_flushed = True
                                buf = ""
                        else:
                            yield {"token": token}

                    if done_reason:
                        break

        except Exception as e:
            logger.error(f"Stream error ({backend}): {e}")
            if _is_context_overflow(e) and not overflow_retried and current_msgs:
                overflow_retried = True
                _shrink_tool_responses(current_msgs)
                logger.info("Context overflow detected — shrinking tool responses and retrying")
                continue
            yield {"error": f"{backend} connection error"}
            return

        if not full_text and not full_reasoning and not tool_calls_acc and current_msgs:
            if not overflow_retried:
                overflow_retried = True
                _shrink_tool_responses(current_msgs)
                logger.warning("Generation returned empty after tool call — shrinking tool responses and retrying")
                continue
            yield {"error": "Model generation failed (context too long). Please ask again."}
            return

        if done_reason == "length":
            logger.warning(f"Model stopped early (done_reason='length'). Consider raising LLM_NUM_CTX (currently {get('LLM_NUM_CTX', 6144)}).")

        if not tool_calls_acc and not think and backend != "litert" and _check_tool_leak(full_text):
            logger.info("Tool leak detected in stream buffer, retrying with think-mode...")
            try:
                retry_payload = _build_payload(
                    await _build_full_messages(messages, memories or [], summary, session_id) + current_msgs,
                    stream=False, think=True, use_tools=True, tool_list=filtered_tools,
                )
                resp2 = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=retry_payload)
                resp2.raise_for_status()
                tc2 = resp2.json()["message"].get("tool_calls") or []
                if tc2:
                    logger.info("Recovered tool calls via think-mode retry (streaming)")
                    tool_calls_acc = tc2
            except Exception as e:
                logger.warning(f"Think-mode retry failed: {e}")

        if not tool_calls_acc:
            leaked = parse_leaked_tool_call(full_text)
            if leaked:
                logger.info(f"Recovered leaked tool call: {leaked['function']['name']}() — executing")
                tool_calls_acc = [leaked]
            else:
                truncated = done_reason == "length" or _looks_truncated(full_text or buf)
                if truncated and not truncation_retried and current_msgs:
                    truncation_retried = True
                    for m in reversed(current_msgs):
                        if m.get("role") == "tool":
                            m["content"] += TRUNCATION_RETRY_NOTE
                            break
                    logger.info("Final reply looked truncated — regenerating once")
                    continue

                if suppressing and full_text:
                    logger.warning(f"No tool call found after suppression, yielding raw text: {full_text[:120]}...")
                    yield {"token": strip_tool_leaks(full_text)}
                elif buf:
                    yield {"token": buf}
                yield {"done": True, "memories_saved": memories_saved, "reasoning": clean_reasoning(full_reasoning)}
                return

        non_confirm_calls = [c for c in tool_calls_acc if c.get("function", {}).get("name", "") not in CONFIRM_TOOLS]
        confirm_calls = [c for c in tool_calls_acc if c.get("function", {}).get("name", "") in CONFIRM_TOOLS]

        current_sigs = {
            f"{c['function']['name']}({json.dumps(parse_tool_args(c['function'].get('arguments')), sort_keys=True)})"
            for c in tool_calls_acc
        }
        if current_sigs and current_sigs.issubset(executed_tool_sigs):
            logger.info(f"All {len(tool_calls_acc)} tool call(s) already executed previously — yielding accumulated text as final answer")
            if buf:
                yield {"token": buf}
            yield {"done": True, "memories_saved": memories_saved, "reasoning": clean_reasoning(full_reasoning)}
            return

        if non_confirm_calls:
            current_msgs.append({"role": "assistant", "content": "", "tool_calls": non_confirm_calls})
            for call in non_confirm_calls:
                fn = call.get("function", {})
                tn = fn.get("name", "")
                args: dict = {}
                t0 = time.perf_counter()
                try:
                    args = parse_tool_args(fn.get("arguments"))
                    result = await run_tool(tn, args, context)
                    success = is_tool_success(result)
                except Exception as e:
                    logger.error(f"Tool {tn} failed: {e}")
                    result = f"ERROR: tool {tn} failed"
                    success = False
                duration_ms = (time.perf_counter() - t0) * 1000
                await run_verification(tn, args, result, success, duration_ms=duration_ms, error=None if success else result)
                if tn == "save_memory" and is_tool_success(result):
                    memories_saved += 1
                tool_msg = {"role": "tool", "tool_name": tn, "content": result}
                if call.get("id"):
                    tool_msg["tool_call_id"] = call["id"]
                current_msgs.append(tool_msg)

            for call in non_confirm_calls:
                fn = call.get("function", {})
                tn = fn.get("name", "")
                args = parse_tool_args(fn.get("arguments"))
                sig = f"{tn}({json.dumps(args, sort_keys=True)})"
                executed_tool_sigs.add(sig)

        for call in confirm_calls:
            tn = call.get("function", {}).get("name", "")
            params = parse_tool_args(call["function"].get("arguments"))
            err = validate_confirm_params(tn, params)
            if err:
                logger.warning(f"Confirm tool {tn} missing params: {err}")
                yield {"token": err}
                yield {"done": True, "memories_saved": memories_saved, "reasoning": clean_reasoning(full_reasoning)}
                return

            preview = None
            if tn == "update_calendar_event":
                try:
                    from calendar_ops import find_events_by_summary
                    matches = await asyncio.to_thread(find_events_by_summary, params.get("summary", ""), days_back=30, days_ahead=90)
                    if matches:
                        preview = "; ".join(f"'{m['summary']}' at {m['start']}" for m in matches)
                except Exception as e:
                    logger.warning(f"Preview lookup for {tn} failed: {e}")

            action = {"tool": tn, "params": params}
            if preview:
                action["preview"] = preview
            logger.info(f"Confirmation required for tool: {tn}")
            yield {"confirm": action}
            return

        if non_confirm_calls and iteration < get("LLM_MAX_TOOL_ITERATIONS", 5) - 1:
            for m in reversed(current_msgs):
                if m.get("role") == "tool":
                    m["content"] += (
                        "\n\n[Note: If the user's request requires additional actions "
                        "(e.g. sending this data via email, creating another event), "
                        "call the next tool NOW. Do NOT reply until all actions are done.]"
                    )
                    break

    logger.warning(f"Max tool iterations ({get('LLM_MAX_TOOL_ITERATIONS', 5)}) exceeded in streaming")
    yield {"done": True, "memories_saved": memories_saved, "reasoning": clean_reasoning(full_reasoning)}
