"""Constructs LLM request payloads (messages, tool schemas) per backend format."""
import json
import logging

from config import (
    LLM_BACKEND,
    LLM_KEEP_ALIVE,
    LLM_MODEL,
    LLM_NUM_BATCH,
    LLM_NUM_CTX,
    LLM_TEMPERATURE,
    LLM_TOP_K,
    LLM_TOP_P,
)
from tools import TOOLS

logger = logging.getLogger("piSynapse")

_VALID_REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh")


def _reasoning_effort(think: bool) -> str:
    """Map think flag + configured level to a litert-lm reasoning_effort value.

    Read dynamically from the config module so that live settings updates
    (Settings API + sync_config) take effect without a server restart.
    """
    if not think:
        return "none"
    import config as _cfg
    effort = (getattr(_cfg, "LLM_REASONING_EFFORT", "medium") or "medium").strip().lower()
    if effort not in _VALID_REASONING_EFFORTS:
        logger.warning(f"Invalid LLM_REASONING_EFFORT={effort!r}, falling back to 'medium'")
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
) -> dict:
    if (backend or LLM_BACKEND) == "litert":
        model = LLM_MODEL.replace(":", "-")
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "temperature": LLM_TEMPERATURE,
            "max_tokens": LLM_NUM_CTX,
            # Gemma 4 thinking is a native request-level feature (litert-lm >= 0.15):
            # "none" disables it, any of minimal/low/medium/high/xhigh enables it.
            "reasoning_effort": _reasoning_effort(think),
        }
        if use_tools:
            payload["tools"] = tool_list if tool_list is not None else TOOLS
        return payload

    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "stream": stream,
        "think": think,
        "options": {
            "temperature": LLM_TEMPERATURE,
            "top_p": LLM_TOP_P,
            "top_k": LLM_TOP_K,
            "num_ctx": LLM_NUM_CTX,
            "num_batch": LLM_NUM_BATCH,
        },
        "keep_alive": LLM_KEEP_ALIVE,
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
