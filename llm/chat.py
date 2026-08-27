"""Non-streaming chat: payload building + LLM request + tool execution loop."""
import asyncio
import json
import logging
import time

from config import (
    DEFAULT_LLM_MAX_OUTPUT_TOKENS,
    DEFAULT_LLM_NUM_CTX,
    LITERT_BASE_URL,
    OLLAMA_BASE_URL,
    get,
)
from messages import get_message
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
from .utils import (
    _THINKING_STRIP_RE,
    _check_tool_leak,
    _get_client,
    clean_reasoning,
    strip_prefix,
    strip_tool_leaks,
)
from .utils import (
    EMPTY_ANSWER_FALLBACK as _EMPTY_ANSWER_FALLBACK,  # noqa: F401 -- legacy alias, referenced by tests
)
from .utils import (
    FINALIZE_NUDGE as _FINALIZE_NUDGE,
)
from .utils import (
    CONTINUATION_NOTE,
    MAX_IDENTICAL_EXECUTIONS as _MAX_IDENTICAL_EXECUTIONS,
    is_lookup_tool,
    is_mutation_tool,
    user_requested_action,
)
from .utils import (
    empty_answer_fallback as _empty_answer_fallback,
)

logger = logging.getLogger("piSynapse")


async def _llm_request(
    msgs: list[dict], *, use_think: bool = False, use_tools: bool = True,
    tool_list: list[dict] | None = None,
    reasoning_effort: str | None = None,
) -> tuple[dict | None, dict | None, str | None]:
    client = _get_client()
    backend = get("LLM_BACKEND", "litert")
    normalized = _normalize_messages_for_backend(msgs, backend=backend)

    if backend == "litert":
        payload = _build_payload(normalized, stream=False, think=use_think, use_tools=use_tools, tool_list=tool_list, backend="litert", reasoning_effort=reasoning_effort)
        try:
            resp = await client.post(f"{LITERT_BASE_URL}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            rj = resp.json()
            choices = rj.get("choices", [])
            if not choices:
                logger.error(f"LiteRT response missing 'choices'. Keys={list(rj.keys())}")
                return rj, None, None
            choice = choices[0]
            msg = choice.get("message", {})
            rj["done_reason"] = choice.get("finish_reason", "stop")
            return rj, msg, None
        except Exception as e:
            logger.error(f"LiteRT request exception: {e}")
            return None, None, str(e)

    payload = _build_payload(normalized, stream=False, think=use_think, use_tools=use_tools, tool_list=tool_list, backend="ollama")
    try:
        resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        resp.raise_for_status()
        rj = resp.json()
        msg = rj.get("message")
        if msg is None:
            logger.error(f"Ollama response missing 'message' key. Keys={list(rj.keys())}, done={rj.get('done')}, done_reason={rj.get('done_reason')}")
        return rj, msg, None
    except Exception as e:
        logger.error(f"Ollama request exception: {e}")
        return None, None, str(e)


SUMMARY_SYSTEM_PROMPT = (
    "You maintain a short running summary of an ongoing conversation between a "
    "user and an AI assistant. Update the existing summary with the new messages "
    "below, keeping only information useful for future context: facts about the "
    "user, ongoing tasks, decisions and preferences. "
    "Ignore and do not include any raw tool-call syntax, malformed tags, or system "
    "artifacts that appear in the messages — these are bugs, not user content. "
    "Only include information explicitly present in the messages — do not infer or "
    "invent details. If new messages contradict the existing summary (e.g. the user "
    "changed their mind or a decision was reversed), the newer information takes "
    "priority — drop the outdated version rather than keeping both. "
    "Keep it to a short paragraph, roughly 3-5 sentences. If the existing summary is "
    "already long, COMPRESS it by merging redundant details and dropping outdated "
    "information. "
    "Reply in the same language as the conversation. Output ONLY the updated "
    "summary text, with no preamble or extra commentary."
)


def _summary_transcript(messages: list[dict]) -> str:
    """Build the summarizer transcript with poisoning defense.

    Assistant messages are stripped of leaked tool-call fragments before they
    ever reach the model (prompt instructions alone are not enough for small
    models), and messages that become empty after stripping are dropped.
    """
    cleaned: list[dict] = []
    for m in messages:
        content = m.get("content", "")
        if m.get("role") == "assistant":
            content = strip_tool_leaks(content)
        if content.strip():
            cleaned.append({**m, "content": content})
    return "\n".join(f"{m['role']}: {m['content']}" for m in cleaned)


async def summarize_conversation(messages: list[dict], previous_summary: str = "") -> str:
    transcript = _summary_transcript(messages)
    if not transcript.strip():
        logger.info("Summarization skipped: nothing left after leak sanitization")
        return previous_summary
    user_content = (
        f"Existing summary:\n{previous_summary or '(none yet)'}\n\n"
        f"New messages:\n{transcript}\n\n"
        "Updated summary:"
    )
    client = _get_client()
    backend = get("LLM_BACKEND", "litert")
    payload = _build_payload(
        [{"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
         {"role": "user", "content": user_content}],
        stream=False,
        think=False,
        backend=backend,
    )
    if backend == "litert":
        payload["max_tokens"] = 500
        payload["max_completion_tokens"] = 500
        url = f"{LITERT_BASE_URL}/v1/chat/completions"
    else:
        payload["options"] = {**payload.get("options", {}), "num_predict": 500}
        url = f"{OLLAMA_BASE_URL}/api/chat"
    try:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        rj = resp.json()
        raw = (
            rj["choices"][0]["message"]["content"]
            if backend == "litert" else rj["message"]["content"]
        )
        # Output guard: the summarizer may echo artifacts it was told to ignore.
        return strip_tool_leaks(raw.strip())
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        return previous_summary


async def chat_with_ollama(
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
) -> dict:
    full_msgs = await _build_full_messages(messages, memories or [], summary, session_id, tool_group=tool_group)
    context = {
        "user_id": user_id,
        "session_id": session_id,
        "_user_text": next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""),
    }
    current_msgs: list[dict] = []
    memories_saved = 0
    thinking = ""
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
    sig_exec_counts: dict[str, int] = {}
    final_nudge_used = False
    mutation_executed = False
    continuation_noted = False
    tools_tokens = 0
    if use_tools and filtered_tools:
        tools_tokens = len(json.dumps(filtered_tools, ensure_ascii=False)) // 4

    for iteration in range(get("LLM_MAX_TOOL_ITERATIONS", 5)):
        if final_nudge_used:
            use_tools = False
            filtered_tools = None
        iter_msgs = _normalize_messages_for_backend(full_msgs + current_msgs, backend=get("LLM_BACKEND", "litert"))
        iter_msgs = trim_messages_for_context(
            iter_msgs,
            context_window=int(get("LLM_NUM_CTX", DEFAULT_LLM_NUM_CTX)),
            reserved_output=int(get("LLM_MAX_OUTPUT_TOKENS", DEFAULT_LLM_MAX_OUTPUT_TOKENS)),
            tools_tokens=tools_tokens,
        )
        resp_json, message, err = await _llm_request(
            iter_msgs, use_think=think, use_tools=use_tools,
            tool_list=filtered_tools, reasoning_effort=reasoning_effort,
        )
        if err:
            logger.error(f"Ollama request failed: {err}")
            return {"reply": get_message("llm_unreachable"), "pending_action": None, "memories_saved": memories_saved, "thinking": None}
        if not resp_json or not message:
            logger.error(f"Ollama returned empty response (resp_json={resp_json}, message={message})")
            return {"reply": get_message("llm_empty_response"), "pending_action": None, "memories_saved": memories_saved, "thinking": None}

        if resp_json.get("done_reason") == "length":
            logger.warning(f"Ollama stopped early (done_reason='length'). Consider raising LLM_NUM_CTX (currently {get('LLM_NUM_CTX', DEFAULT_LLM_NUM_CTX)}).")

        tool_calls = message.get("tool_calls") or []
        raw_content = _THINKING_STRIP_RE.sub('', message.get("content", "") or "").strip()
        # Ollama >=0.9 emits thinking as `message.thinking`; accept the older
        # reasoning_content alias too.
        thinking = clean_reasoning(message.get("thinking") or message.get("reasoning_content") or "")

        # Unified think-mode retry (both backends): only a leaked tool-call
        # pattern justifies the extra call — a legitimate plain-text answer
        # must not pay for it. reasoning_effort is preserved so litert's
        # thinking budget matches the original request.
        if not tool_calls and not think and use_tools and iteration == 0 and _check_tool_leak(raw_content):
            logger.info("No tool calls produced (tool leak), retrying with think-mode...")
            think_msgs = await _build_full_messages(messages, memories or [], summary, session_id, tool_group=tool_group)
            think_msgs = _normalize_messages_for_backend(think_msgs + current_msgs, backend=get("LLM_BACKEND", "litert"))
            resp2, msg2, err2 = await _llm_request(
                think_msgs, use_think=True, use_tools=use_tools, tool_list=filtered_tools,
                reasoning_effort=reasoning_effort,
            )
            if not err2 and msg2:
                tc2 = msg2.get("tool_calls") or []
                if tc2:
                    logger.info("Recovered tool calls via think-mode retry")
                    tool_calls, message, resp_json = tc2, msg2, resp2
                    thinking = clean_reasoning(message.get("thinking") or message.get("reasoning_content") or "")

        if not tool_calls:
            return {"reply": strip_prefix(raw_content), "pending_action": None, "memories_saved": memories_saved, "thinking": thinking}

        non_confirm_calls = [c for c in tool_calls if c.get("function", {}).get("name", "") not in CONFIRM_TOOLS]
        confirm_calls = [c for c in tool_calls if c.get("function", {}).get("name", "") in CONFIRM_TOOLS]

        current_sigs = {
            f"{c['function']['name']}({json.dumps(parse_tool_args(c['function'].get('arguments')), sort_keys=True)})"
            for c in tool_calls
        }
        if current_sigs and current_sigs.issubset(executed_tool_sigs):
            logger.info(f"All {len(tool_calls)} tool call(s) already executed previously — returning accumulated text as final answer")
            if not raw_content.strip() and not final_nudge_used:
                # Repeat with nothing accumulated: force one text-only round
                # instead of returning an empty reply (2026-08-22 incident).
                logger.info("Dedup hit with empty accumulated text — nudging a text-only final answer")
                final_nudge_used = True
                current_msgs.append({"role": "user", "content": _FINALIZE_NUDGE})
                continue
            reply = strip_prefix(raw_content)
            if not reply.strip():
                reply = _empty_answer_fallback()
            return {"reply": reply, "pending_action": None, "memories_saved": memories_saved, "thinking": thinking}

        allowed_names = {t["function"]["name"] for t in filtered_tools} if use_tools and filtered_tools else None
        if non_confirm_calls:
            current_msgs.append({"role": "assistant", "content": message.get("content", ""), "tool_calls": non_confirm_calls})
            for call in non_confirm_calls:
                fn = call.get("function", {})
                tn = fn.get("name", "")
                args: dict = {}
                t0 = time.perf_counter()
                probe_sig = f"{tn}({json.dumps(parse_tool_args(fn.get('arguments')), sort_keys=True)})"
                max_exec = 1 if tn.startswith("create_") or tn == "send_email" else _MAX_IDENTICAL_EXECUTIONS
                if sig_exec_counts.get(probe_sig, 0) >= max_exec:
                    # Side-effect safety: never run the exact same call more
                    # than _MAX_IDENTICAL_EXECUTIONS times per request.
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
                # Per-call accounting MUST happen here (not post-loop) to catch same-round duplicates
                executed_tool_sigs.add(probe_sig)
                sig_exec_counts[probe_sig] = sig_exec_counts.get(probe_sig, 0) + 1
                if is_mutation_tool(tn):
                    mutation_executed = True

        for call in confirm_calls:
            tn = call.get("function", {}).get("name", "")
            if allowed_names is not None and tn not in allowed_names:
                logger.warning(f"Confirm tool {tn} hallucinated (not offered) — rejected")
                return {"reply": f"[Rejected: '{tn}' is NOT available this turn. Available: {', '.join(sorted(allowed_names))}. Answer in plain text.]", "pending_action": None, "memories_saved": memories_saved, "thinking": thinking}
            params = parse_tool_args(call["function"].get("arguments"))
            err = validate_confirm_params(tn, params)
            if err:
                logger.warning(f"Confirm tool {tn} missing params: {err}")
                return {"reply": err, "pending_action": None, "memories_saved": memories_saved, "thinking": thinking}

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
                    notes = await get_notes_context(session_id)
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
                    tasks = await get_tasks_context(session_id)
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
            return {"reply": "", "pending_action": action,
                    "memories_saved": memories_saved, "thinking": thinking}

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
                        continuation_noted = True
                        m["content"] += CONTINUATION_NOTE
                    else:
                        m["content"] += (
                            "\n\n[Note: If the user's request requires additional actions "
                            "(e.g. sending this data via email, creating another event), "
                            "call the next tool NOW. Do NOT reply until all actions are done.]"
                        )
                    break

    logger.warning(f"Max tool iterations ({get('LLM_MAX_TOOL_ITERATIONS', 5)}) exceeded")
    return {"reply": "I made several tool calls but couldn't reach a final answer -- please try rephrasing.",
            "pending_action": None, "memories_saved": memories_saved, "thinking": thinking}
