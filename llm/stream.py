"""SSE streaming chat handler. Manages tool-call loops, token buffering, and TTFT."""
import asyncio
import json
import logging

from config import (
    LITERT_BASE_URL,
    LLM_BACKEND,
    LLM_MAX_TOOL_ITERATIONS,
    LLM_NUM_CTX,
    OLLAMA_BASE_URL,
)
from tools import (
    CONFIRM_TOOLS,
    get_tools_for_group,
    parse_tool_args,
    run_tool,
    validate_confirm_params,
)

from .payload import _build_full_messages, _build_payload, _normalize_messages_for_backend
from .utils import _check_tool_leak, _get_client

logger = logging.getLogger("piSynapse")

EARLY_BUFFER_CHARS = 8


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
):
    full_msgs = _build_full_messages(messages, memories or [], summary, session_id, think=think)
    context = {"user_id": user_id, "session_id": session_id}
    current_msgs: list[dict] = []
    memories_saved = 0
    client = _get_client()
    backend = LLM_BACKEND

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

    for iteration in range(LLM_MAX_TOOL_ITERATIONS):
        if backend == "litert":
            payload = _build_payload(
                _normalize_messages_for_backend(full_msgs + current_msgs, backend="litert"),
                stream=True, use_tools=use_tools, tool_list=filtered_tools, backend="litert",
            )
            url = f"{LITERT_BASE_URL}/v1/chat/completions"
        else:
            payload = _build_payload(full_msgs + current_msgs, stream=True, think=think, use_tools=use_tools, tool_list=filtered_tools)
            url = f"{OLLAMA_BASE_URL}/api/chat"

        buf = ""
        full_text = ""
        early_buf_flushed = False
        tool_calls_acc: list = []
        done_reason = None
        suppressing = False

        try:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for raw in resp.aiter_lines():
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
                        choice = chunk.get("choices", [{}])[0]
                        delta = choice.get("delta", {})
                        token = delta.get("content", "")
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
                        tc = msg.get("tool_calls")
                        done = data.get("done", False)
                        if done:
                            done_reason = data.get("done_reason")

                    if tc:
                        tool_calls_acc = tc

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
            yield {"error": f"{backend} connection error"}
            return

        if done_reason == "length":
            logger.warning(f"Model stopped early (done_reason='length'). Consider raising LLM_NUM_CTX (currently {LLM_NUM_CTX}).")

        if not tool_calls_acc and not think and backend != "litert" and _check_tool_leak(full_text):
            logger.info("Tool leak detected in stream buffer, retrying with think-mode...")
            try:
                retry_payload = _build_payload(
                    _build_full_messages(messages, memories or [], summary, session_id, think=True) + current_msgs,
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
            if suppressing and full_text:
                logger.warning(f"No tool call found after suppression, yielding raw text: {full_text[:120]}...")
                yield {"token": full_text}
            elif buf:
                yield {"token": buf}
            yield {"done": True, "memories_saved": memories_saved}
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
            yield {"done": True, "memories_saved": memories_saved}
            return

        if non_confirm_calls:
            current_msgs.append({"role": "assistant", "content": "", "tool_calls": non_confirm_calls})
            for call in non_confirm_calls:
                fn = call.get("function", {})
                tn = fn.get("name", "")
                try:
                    result = await run_tool(tn, parse_tool_args(fn.get("arguments")), context)
                except Exception as e:
                    logger.error(f"Tool {tn} failed: {e}")
                    result = f"ERROR: tool {tn} failed"
                if tn == "save_memory" and not result.startswith("ERROR"):
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
                yield {"done": True, "memories_saved": memories_saved}
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

        if non_confirm_calls and iteration < LLM_MAX_TOOL_ITERATIONS - 1:
            for m in reversed(current_msgs):
                if m.get("role") == "tool":
                    m["content"] += (
                        "\n\n[Note: If the user's request requires additional actions "
                        "(e.g. sending this data via email, creating another event), "
                        "call the next tool NOW. Do NOT reply until all actions are done.]"
                    )
                    break

    logger.warning(f"Max tool iterations ({LLM_MAX_TOOL_ITERATIONS}) exceeded in streaming")
    yield {"done": True, "memories_saved": memories_saved}
