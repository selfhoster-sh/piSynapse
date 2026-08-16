"""Constructs LLM request payloads (messages, tool schemas) per backend format."""
import json
import logging

from tools import TOOLS

logger = logging.getLogger("piSynapse")

_VALID_REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh")


def _reasoning_effort(think: bool, requested: str | None = None) -> str:
    """Map think flag + level to a litert-lm reasoning_effort value.

    An explicit per-request level (UI menu) wins; otherwise fall back to the
    configured default read dynamically from the config module so that live
    settings updates take effect without a server restart.
    """
    if not think:
        return "none"
    from config import get
    if requested is None:
        requested = get("LLM_REASONING_EFFORT", "medium") or "medium"
    effort = requested.strip().lower()
    if effort not in _VALID_REASONING_EFFORTS:
        logger.warning(f"Invalid reasoning_effort={effort!r}, falling back to 'medium'")
        return "medium"
    return effort


def _build_payload(
    messages: list[dict],
    *,
    stream: bool = False,
    think: bool = False,
    use_tools: bool = True,
    tool_list: list[dict] | None = None,
    backend: str | None = None,
    reasoning_effort: str | None = None,
) -> dict:
    # Read live values so UI setting changes apply without a restart.
    from config import get
    backend = (backend or get("LLM_BACKEND", "litert")).lower()
    model_name = get("LLM_MODEL", "gemma4-e2b")
    temperature = get("LLM_TEMPERATURE", 0.6)
    top_p = get("LLM_TOP_P", 0.85)
    top_k = get("LLM_TOP_K", 40)
    max_output = int(get("LLM_MAX_OUTPUT_TOKENS", 2048) or 2048)

    if backend == "litert":
        payload = {
            "model": model_name.replace(":", "-"),
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "max_tokens": max_output,
            # litert-lm only reads max_completion_tokens; max_tokens is ignored.
            "max_completion_tokens": max_output,
            # Gemma 4 thinking is a native request-level feature (litert-lm >= 0.15):
            # "none" disables it, any of minimal/low/medium/high/xhigh enables it.
            "reasoning_effort": _reasoning_effort(think, reasoning_effort),
        }
        if use_tools:
            payload["tools"] = tool_list if tool_list is not None else TOOLS
        return payload

    payload = {
        "model": model_name,
        "messages": messages,
        "stream": stream,
        "think": think,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "num_ctx": get("LLM_NUM_CTX", 8192),
            "num_batch": get("LLM_NUM_BATCH", 256),
        },
        "keep_alive": get("LLM_KEEP_ALIVE", "4h"),
    }
    if use_tools:
        payload["tools"] = tool_list if tool_list is not None else TOOLS
    return payload


def _build_full_messages(
    base_msgs: list[dict],
    memories: list[dict],
    summary: str,
    email_session_id: str,
    tool_group: str | None = None,
) -> list[dict]:
    from prompt import build_context, get_email_context, get_system_prompt, get_tool_system_prompt

    ctx = build_context(
        memories=memories or None,
        summary=summary,
        email_context=get_email_context(email_session_id) or None,
    )
    if tool_group:
        system = get_tool_system_prompt(tool_group) + ctx
    else:
        system = get_system_prompt() + ctx

    return [{"role": "system", "content": system}] + base_msgs


def _normalize_messages_for_backend(messages: list[dict], backend: str = "ollama") -> list[dict]:
    if backend != "litert":
        return messages

    result = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        images = msg.get("images")

        new_msg: dict = {"role": role}

        if images and role in ("user",):
            parts = [{"type": "text", "text": content or ""}]
            for img_b64 in images:
                if isinstance(img_b64, str):
                    if img_b64.startswith("data:"):
                        header = img_b64.split(",")[0] if "," in img_b64 else ""
                        data = img_b64.split(",", 1)[1] if "," in img_b64 else img_b64
                        if "audio" in header:
                            parts.append({"type": "input_audio", "input_audio": {"data": data}})
                        else:
                            parts.append({"type": "image_url", "image_url": {"url": img_b64}})
                    else:
                        parts.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}})
            new_msg["content"] = parts
        else:
            new_msg["content"] = content

        if "tool_calls" in msg:
            tcs = msg["tool_calls"]
            normalized_tcs = []
            for tc in tcs:
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, dict):
                    fn["arguments"] = json.dumps(args)
                normalized_tcs.append(tc)
            new_msg["tool_calls"] = normalized_tcs
        if "tool_call_id" in msg:
            new_msg["tool_call_id"] = msg["tool_call_id"]

        result.append(new_msg)

    return result
