"""SSE streaming chat handler. Manages tool-call loops, token buffering, and TTFT."""
import asyncio
import json
import logging
import re
import time

from config import (
    DEFAULT_LLM_MAX_OUTPUT_TOKENS,
    DEFAULT_LLM_NUM_CTX,
    LITERT_BASE_URL,
    OLLAMA_BASE_URL,
    get,
)
from tool_verification import run_verification
from tools import (
    CONFIRM_TOOLS,
    TOOL_NAMES,
    get_tools_for_group,
    is_tool_success,
    parse_tool_args,
    run_tool,
    validate_confirm_params,
)

from .payload import _build_full_messages, _build_payload, _normalize_messages_for_backend, litert_cache_key, trim_messages_for_context
from .utils import (
    CONTINUATION_NOTE,
    _TOOL_ASK_HINT,
    _bare_tool_name,
    _check_tool_leak,
    _chip_clarify_question,
    _escalation_tools,
    _get_client,
    _wants_tools_hint,
    clean_reasoning,
    is_lookup_tool,
    is_mutation_tool,
    parse_leaked_tool_call,
    chip_clarify_response,
    should_arm_tool_hint,
    strip_tool_leaks,
    user_requested_action,
)
from .utils import (
    FINALIZE_NUDGE as _FINALIZE_NUDGE,
)
from .utils import (
    MAX_IDENTICAL_EXECUTIONS as _MAX_IDENTICAL_EXECUTIONS,
)
from .utils import (
    empty_answer_fallback as _empty_answer_fallback,
)

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
        # Indexless deltas (LiteRT sends them raw): when both sides hold a
        # single call, accumulate argument fragments instead of replacing
        # (replacing truncated multi-chunk JSON to {} and misfired tools).
        if len(acc) == 1 and len(tc) == 1:
            target, call = acc[0], tc[0]
            for k, v in call.items():
                if k == "function" and isinstance(v, dict):
                    fn = target.setdefault("function", {})
                    for fk, fv in v.items():
                        if fk == "arguments" and isinstance(fv, str):
                            fn["arguments"] = fn.get("arguments", "") + fv
                        elif fk not in fn or fn[fk] in (None, ""):
                            fn[fk] = fv
                elif v is not None and (k not in target or target[k] in (None, "")):
                    target[k] = v
            return acc
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






def _build_round_request(backend: str, full_msgs: list[dict], current_msgs: list[dict],
                         use_tools: bool, filtered_tools, think: bool, reasoning_effort: str,
                         session_cache_key: str | None = None):
    """Construct the streaming request payload + endpoint URL for one round.

    Extracted so the per-iteration loop can wrap construction in a hard
    try/except — a silent generator death here showed users an empty reply
    with zero diagnostics (laptop field case, 2026-08-24).
    """
    tools_tokens = 0
    if use_tools and filtered_tools:
        tools_tokens = len(json.dumps(filtered_tools, ensure_ascii=False)) // 4
    if backend == "litert":
        payload = _build_payload(
            trim_messages_for_context(
                _normalize_messages_for_backend(full_msgs + current_msgs, backend="litert"),
                context_window=int(get("LLM_NUM_CTX", DEFAULT_LLM_NUM_CTX)),
                reserved_output=int(get("LLM_MAX_OUTPUT_TOKENS", DEFAULT_LLM_MAX_OUTPUT_TOKENS)),
                tools_tokens=tools_tokens,
            ),
            stream=True, think=think, use_tools=use_tools, tool_list=filtered_tools,
            backend="litert", reasoning_effort=reasoning_effort,
            session_cache_key=session_cache_key,
        )
        url = f"{LITERT_BASE_URL}/v1/chat/completions"
    else:
        payload = _build_payload(
            trim_messages_for_context(
                full_msgs + current_msgs,
                context_window=int(get("LLM_NUM_CTX", DEFAULT_LLM_NUM_CTX)),
                reserved_output=int(get("LLM_MAX_OUTPUT_TOKENS", DEFAULT_LLM_MAX_OUTPUT_TOKENS)),
                tools_tokens=tools_tokens,
            ),
            stream=True, think=think, use_tools=use_tools, tool_list=filtered_tools,
            reasoning_effort=reasoning_effort,
        )
        url = f"{OLLAMA_BASE_URL}/api/chat"
    return payload, url






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
    origin: str = "",
    abort_event=None,
):
    full_msgs = await _build_full_messages(messages, memories or [], summary, session_id, tool_group=tool_group, user_id=user_id or "default")
    context = {
        "user_id": user_id or "default",
        "_origin": (origin or "").strip().lower(),
        "session_id": session_id,
        # Guards (CLARIFY_REQUIRED etc.) anchor their clarifying question to
        # the user's own words — small models mirror the LAST language they
        # saw, and tool results are English meta-instructions.
        "_user_text": next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""),
    }
    current_msgs: list[dict] = []
    memories_saved = 0
    client = _get_client()
    backend = get("LLM_BACKEND", "litert")
    cache_key = litert_cache_key(context.get("user_id"), session_id)

    from tools import get_combined_tools
    intent_no_tools = intent == "question" and tool_group is None
    if intent_no_tools:
        use_tools = False
        filtered_tools = None
        # Shared gate (see llm/utils.py): hint ONLY on a real tool-domain
        # touch, else small models spuriously escalate on pure chat.
        hint_armed = should_arm_tool_hint(context["_user_text"])
        if hint_armed:
            full_msgs = full_msgs + [{"role": "system", "content": _TOOL_ASK_HINT}]
        logger.info("Pure chat (question+None) — tools disabled (hint_armed=%s)", hint_armed)
    else:
        use_tools = True
        if tool_group:
            filtered_tools = get_tools_for_group(tool_group)
            logger.info(f"Tool group: {tool_group} ({len(filtered_tools)} tools)")
        else:
            filtered_tools = get_combined_tools()
            logger.info(f"No specific group — sending combined tools ({len(filtered_tools)} tools)")

    # Chip-origin fast path: create/send chips never reach the model — the
    # clarifying question is deterministic and instant.
    last_user_msg = next((m.get("content", "") for m in reversed(messages)
                          if m.get("role") == "user"), "")
    if (origin == "chip" and not think):
        chip_q = chip_clarify_response(origin, think, tool_group, last_user_msg)
        if chip_q:
            logger.info("Chip-origin %s request — instant clarify (LLM skipped)", tool_group)
            yield {"token": chip_q}
            yield {"done": True, "session_id": session_id, "memories_saved": 0,
                   "retrieved_count": 0, "retrieval_ms": 0}
            return

    executed_tool_sigs: set[str] = set()
    sig_exec_counts: dict[str, int] = {}
    truncation_retried = False
    overflow_retried = False
    final_nudge_used = False
    tools_escalated = False
    litert_parse_recovered = False
    mutation_executed = False
    continuation_noted = False

    for iteration in range(get("LLM_MAX_TOOL_ITERATIONS", 5)):
        if abort_event is not None and abort_event.is_set():
            logger.info("Stream aborted before round %d — stopping", iteration)
            yield {"done": True, "aborted": True, "session_id": session_id,
                   "memories_saved": memories_saved}
            return
        if truncation_retried or final_nudge_used:
            use_tools = False
            filtered_tools = None
        try:
            payload, url = _build_round_request(
                backend, full_msgs, current_msgs, use_tools, filtered_tools,
                think, reasoning_effort, session_cache_key=cache_key)
        except Exception:
            logger.exception("Round %d request construction failed", iteration)
            yield {"error": "Internal error while preparing the model request."}
            return

        buf = ""
        full_text = ""
        full_reasoning = ""
        early_buf_flushed = False
        tool_calls_acc: list = []
        done_reason = None
        suppressing = False
        escalate_now = False

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
                        if data.get("error"):
                            err = data["error"]
                            if isinstance(err, dict):
                                err = err.get("message", str(err))
                            raise RuntimeError(f"ollama stream error: {err}")
                        msg = data.get("message", {})
                        token = msg.get("content", "")
                        # Ollama >=0.9 emits thinking as `message.thinking`;
                        # accept the older reasoning_content alias too.
                        reasoning_token = msg.get("thinking") or msg.get("reasoning_content") or ""
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
                        hatch_armed = intent_no_tools and hint_armed and not tools_escalated and not think
                        if not suppressing and not tool_calls_acc:
                            if _check_tool_leak(full_text) or _check_tool_leak(buf + token):
                                suppressing = True
                                logger.info("Tool call pattern detected mid-stream, suppressing output")
                            elif hatch_armed and (_wants_tools_hint(full_text) or _bare_tool_name(full_text)):
                                # Marker confirmed: nothing more of value in
                                # this round — stop reading, escalate below.
                                suppressing = True
                                logger.info("TOOL_NEEDED marker detected — cutting round short")
                        if suppressing:
                            if hatch_armed:
                                logger.info("Hatch armed — aborting pure-chat round to escalate")
                                escalate_now = True
                                break
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
            err_str = str(e)
            # LiteRT server-side grammar failure: the model emitted a doubled-
            # brace native call and the SERVER rejected it before we saw text
            # (INVALID_ARGUMENT: Failed to parse tool calls from code block: ...).
            # The full call is inside the error message — recover it and route
            # through the normal execution path instead of failing the turn.
            if ("Failed to parse tool calls from code block" in err_str
                    and not litert_parse_recovered):
                leaked = parse_leaked_tool_call(err_str.split("code block:", 1)[-1])
                if leaked:
                    litert_parse_recovered = True
                    logger.info("Recovered litert server-side parse failure: %s()",
                                leaked["function"]["name"])
                    tool_calls_acc = [leaked]
                    done_reason = "stop"
                else:
                    logger.error("Stream error (%s): %s", backend, e)
                    yield {"error": f"{backend} connection error"}
                    return
            elif _is_context_overflow(e) and not overflow_retried and current_msgs:
                overflow_retried = True
                _shrink_tool_responses(current_msgs)
                yield {"gen_retry": {"reason": "overflow"}}
                logger.info("Context overflow detected — shrinking tool responses and retrying")
                continue
            else:
                logger.error(f"Stream error ({backend}): {e}")
                yield {"error": f"{backend} connection error"}
                return

        if not full_text and not full_reasoning and not tool_calls_acc and current_msgs:
            if not overflow_retried:
                overflow_retried = True
                _shrink_tool_responses(current_msgs)
                yield {"gen_retry": {"reason": "empty"}}
                logger.warning("Generation returned empty after tool call — shrinking tool responses and retrying")
                continue
            yield {"error": "Model generation failed (context too long). Please ask again."}
            return

        if done_reason == "length":
            logger.warning(f"Model stopped early (done_reason='length'). Consider raising LLM_NUM_CTX (currently {get('LLM_NUM_CTX', DEFAULT_LLM_NUM_CTX)}).")

        if not escalate_now and intent_no_tools and hint_armed and not think and not tools_escalated \
                and (_check_tool_leak(full_text) or _wants_tools_hint(full_text)):
            # Round ended with a tool-signal we could not cut early —
            # escalate through the same path below.
            escalate_now = True

        if escalate_now:
            # Mid-stream hatch fired (TOOL_NEEDED marker or leaked call
            # syntax) — redo this round with the smallest sufficient toolset.
            # Gated on intent_no_tools upstream so terminal text-only modes
            # (final nudge / truncation retry) can never re-arm it.
            tools_escalated = True
            use_tools = True
            # The injected hint says "you have NO tools" — now false, and
            # left in place it would make the model re-emit the marker
            # instead of calling the freshly attached tools.
            full_msgs = [m for m in full_msgs if m.get("content") != _TOOL_ASK_HINT]
            last_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
            try:
                filtered_tools, esc_scope = _escalation_tools(full_text, last_user)
            except Exception:
                logger.exception("Escalation toolset selection failed")
                filtered_tools, esc_scope = get_combined_tools(), "combined"
            logger.info("Hatch escalating: scope=%s (%d tools)", esc_scope, len(filtered_tools))
            yield {"gen_retry": {"reason": "tools_escalated"}}
            continue

        if not tool_calls_acc and not think and use_tools and _check_tool_leak(full_text):
            # Unified think-mode retry (both backends): the model leaked a
            # tool-call pattern as plain text instead of emitting real
            # tool_calls. reasoning_effort is preserved so litert's thinking
            # budget matches the original request.
            logger.info("Tool leak detected in stream buffer, retrying with think-mode...")
            yield {"gen_retry": {"reason": "tool_leak"}}
            try:
                retry_msgs = await _build_full_messages(messages, memories or [], summary, session_id, tool_group=tool_group, user_id=user_id or "default") + current_msgs
                if backend == "litert":
                    retry_payload = _build_payload(
                        _normalize_messages_for_backend(retry_msgs, backend="litert"),
                        stream=False, think=True, use_tools=True, tool_list=filtered_tools,
                        backend="litert", reasoning_effort=reasoning_effort,
                        session_cache_key=cache_key,
                    )
                    retry_url = f"{LITERT_BASE_URL}/v1/chat/completions"
                else:
                    retry_payload = _build_payload(
                        retry_msgs,
                        stream=False, think=True, use_tools=True, tool_list=filtered_tools,
                        backend="ollama", reasoning_effort=reasoning_effort,
                    )
                    retry_url = f"{OLLAMA_BASE_URL}/api/chat"
                resp2 = await client.post(retry_url, json=retry_payload)
                resp2.raise_for_status()
                rj2 = resp2.json()
                msg2 = rj2["choices"][0]["message"] if backend == "litert" else (rj2.get("message") or {})
                tc2 = msg2.get("tool_calls") or []
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
            if not buf.strip() and not final_nudge_used:
                # Repeat with nothing accumulated: force one text-only round
                # instead of yielding an empty reply (2026-08-22 incident).
                logger.info("Dedup hit with empty accumulated text — nudging a text-only final answer")
                final_nudge_used = True
                current_msgs.append({"role": "user", "content": _FINALIZE_NUDGE})
                continue
            yield {"token": buf.strip() or _empty_answer_fallback()}
            yield {"done": True, "memories_saved": memories_saved, "reasoning": clean_reasoning(full_reasoning)}
            return

        # Tools offered THIS turn (filtered group / combined set). Small
        # models sometimes hallucinate a known-but-unoffered tool from
        # memory — executing it would write to the wrong domain (seen:
        # create_task during a calendar turn). Reject with guidance so
        # the model self-corrects using the tools it was given.
        allowed_names = ({t["function"]["name"] for t in filtered_tools}
                         if use_tools and filtered_tools else None)
        if non_confirm_calls:
            current_msgs.append({"role": "assistant", "content": "", "tool_calls": non_confirm_calls})
            for call in non_confirm_calls:
                fn = call.get("function", {})
                tn = fn.get("name", "")
                if abort_event is not None and abort_event.is_set():
                    # "Durdur" must stop tool execution too — previously the
                    # router broke its SSE loop while this generator kept
                    # running tools in the background, writing unchecked.
                    logger.info("Stream aborted before tool %s — stopping", tn)
                    yield {"done": True, "aborted": True, "session_id": session_id,
                           "memories_saved": memories_saved}
                    return
                args: dict = {}
                t0 = time.perf_counter()
                probe_sig = f"{tn}({json.dumps(parse_tool_args(fn.get('arguments')), sort_keys=True)})"
                # Creates are side-effectful and idempotency-unsafe (duplicate
                # notes/tasks/events): one identical call max. Read-like tools
                # tolerate the standard two-attempt budget.
                max_exec = 1 if tn.startswith("create_") or tn == "send_email" else _MAX_IDENTICAL_EXECUTIONS
                if sig_exec_counts.get(probe_sig, 0) >= max_exec:
                    # Side-effect safety: never run the exact same call more
                    # than max_exec times per request.
                    logger.warning(
                        f"Tool {tn} identical signature already executed "
                        f"{max_exec}x — refusing re-execution"
                    )
                    tool_msg = {
                        "role": "tool",
                        "tool_name": tn,
                        "content": (
                            "[Refused: this exact tool call has already been "
                            f"executed {max_exec} times. Its "
                            "result is in the messages above — do not call it "
                            "again, answer from the existing result.]"
                        ),
                    }
                    if call.get("id"):
                        tool_msg["tool_call_id"] = call["id"]
                    current_msgs.append(tool_msg)
                    yield {"tool": {"name": tn, "phase": "refused",
                                    "attempt": sig_exec_counts.get(probe_sig, 0) + 1,
                                    "max": max_exec}}
                    continue
                if allowed_names is not None and tn not in allowed_names:
                    logger.warning(f"Tool {tn} hallucinated (not offered this turn) — rejected")
                    tool_msg = {
                        "role": "tool",
                        "tool_name": tn,
                        "content": (
                            f"[Rejected: '{tn}' is NOT available in this conversation turn. "
                            f"Available tools: {', '.join(sorted(allowed_names))}. "
                            "Use one of those, or if none fits, answer in plain text.]"
                        ),
                    }
                    if call.get("id"):
                        tool_msg["tool_call_id"] = call["id"]
                    current_msgs.append(tool_msg)
                    continue
                try:
                    args = parse_tool_args(fn.get("arguments"))
                    yield {"tool": {"name": tn, "phase": "start",
                                    "attempt": sig_exec_counts.get(probe_sig, 0) + 1,
                                    "max": _MAX_IDENTICAL_EXECUTIONS}}
                    result, entity_id = await run_tool(tn, args, context)
                    success = is_tool_success(result)
                except Exception as e:
                    logger.error(f"Tool {tn} failed: {e}")
                    result = f"ERROR: tool {tn} failed"
                    entity_id = None
                    success = False
                duration_ms = (time.perf_counter() - t0) * 1000
                audit_id, verification_status = await run_verification(tn, args, result, success, entity_id=entity_id, duration_ms=duration_ms, error=None if success else result, user_id=context.get("user_id"))
                yield {"tool": {"name": tn, "phase": "end", "ok": success, "audit_id": audit_id, "verification_status": verification_status, "clarify": result.startswith("CLARIFY_REQUIRED"), "noop": result.startswith("NOOP")}}
                if tn == "save_memory" and is_tool_success(result):
                    memories_saved += 1
                # Per-call accounting MUST happen here: deferring it to a
                # post-loop pass let a second identical call in the SAME round
                # bypass the cap and execute twice (duplicate-create bug).
                executed_tool_sigs.add(probe_sig)
                sig_exec_counts[probe_sig] = sig_exec_counts.get(probe_sig, 0) + 1
                if is_mutation_tool(tn):
                    mutation_executed = True
                tool_msg = {"role": "tool", "tool_name": tn, "content": result}
                if call.get("id"):
                    tool_msg["tool_call_id"] = call["id"]
                current_msgs.append(tool_msg)

        for call in confirm_calls:
            tn = call.get("function", {}).get("name", "")
            if allowed_names is not None and tn not in allowed_names:
                logger.warning(f"Confirm tool {tn} hallucinated (not offered this turn) — rejected")
                yield {"token": f"[Rejected: '{tn}' is NOT available this turn. Available: {', '.join(sorted(allowed_names))}. Answer in plain text.]"}
                yield {"done": True, "memories_saved": memories_saved, "reasoning": clean_reasoning(full_reasoning)}
                return
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
            elif tn == "delete_note":
                try:
                    from prompt import get_notes_context
                    notes = await get_notes_context(session_id, context.get("user_id"))
                    ref = params.get("note_id")
                    if notes and ref:
                        is_num = isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit())
                        if is_num and 1 <= int(ref) <= len(notes):
                            n = notes[int(ref) - 1]
                            preview = f"{n.get('title', 'Untitled')}"
                except Exception as e:
                    logger.warning(f"Preview lookup for {tn} failed: {e}")
            elif tn in ("complete_task", "delete_task"):
                try:
                    from prompt import get_tasks_context
                    tasks = await get_tasks_context(session_id, context.get("user_id"))
                    ref = params.get("uid", "")
                    if tasks and ref:
                        is_num = isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit())
                        if is_num and 1 <= int(ref) <= len(tasks):
                            t_item = tasks[int(ref) - 1]
                            preview = f"{t_item.get('summary', 'Untitled')}"
                except Exception as e:
                    logger.warning(f"Preview lookup for {tn} failed: {e}")

            action = {"tool": tn, "params": params}
            if preview:
                action["preview"] = preview
            logger.info(f"Confirmation required for tool: {tn}")
            yield {"confirm": action}
            return

        if non_confirm_calls and iteration < get("LLM_MAX_TOOL_ITERATIONS", 5) - 1:
            round_names = {c["function"]["name"] for c in non_confirm_calls}
            lookup_only = bool(round_names) and all(is_lookup_tool(n) for n in round_names)
            for m in reversed(current_msgs):
                if m.get("role") == "tool":
                    if (
                        lookup_only
                        and not mutation_executed
                        and not continuation_noted
                        and user_requested_action(context["_user_text"])
                    ):
                        # List/read succeeded but the user wanted an action on
                        # what was found — push the model to finish the job
                        # (eval's dominant failure mode: list-then-stop).
                        continuation_noted = True
                        m["content"] += CONTINUATION_NOTE
                    else:
                        m["content"] += (
                            "\n\n[Note: If the user's request requires additional actions "
                            "(e.g. sending this data via email, creating another event), "
                            "call the next tool NOW. Do NOT reply until all actions are done.]"
                        )
                    break

    logger.warning(f"Max tool iterations ({get('LLM_MAX_TOOL_ITERATIONS', 5)}) exceeded in streaming")
    yield {"done": True, "memories_saved": memories_saved, "reasoning": clean_reasoning(full_reasoning)}
