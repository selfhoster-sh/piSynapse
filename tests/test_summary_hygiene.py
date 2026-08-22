"""Summary-pipeline poisoning defenses (2026-08-22).

The running conversation summary must never absorb leaked tool-call syntax:
input messages are stripped before reaching the summarizer model, the
returned summary is sanitized before being stored, and the system prompt
explicitly instructs the model to ignore artifacts.
"""

import asyncio

import llm.chat as lchat


class _Resp:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class _Client:
    def __init__(self, reply_content):
        self.reply = reply_content
        self.payloads = []

    async def post(self, url, json=None):
        self.payloads.append({"url": url, "json": json})
        return _Resp(self.reply)


def _run_summarize(monkeypatch, messages, reply="Kısa özet.", previous=""):
    client = _Client(reply)
    monkeypatch.setattr(lchat, "_get_client", lambda: client)
    result = asyncio.run(
        lchat.summarize_conversation(messages, previous_summary=previous)
    )
    return result, client


def test_summary_prompt_locks_poisoning_defenses():
    prompt = lchat.SUMMARY_SYSTEM_PROMPT
    assert "tool-call syntax" in prompt
    assert "malformed tags" in prompt
    assert "do not infer or invent" in prompt
    # Contradiction handling: newer information wins.
    assert "takes priority" in prompt


def test_summary_input_strips_leaked_assistant_content(monkeypatch):
    result, client = _run_summarize(
        monkeypatch,
        [
            {"role": "user", "content": "notlarımı listele"},
            {"role": "assistant", "content":
                "<|tool_call|>call:list_notes{{}}<tool_call|> Notlarını listeledim."},
        ],
    )
    sent = client.payloads[0]["json"]["messages"]
    user_msg = next(m for m in sent if m["role"] == "user")
    assert "call:" not in user_msg["content"]
    assert "<|tool_call" not in user_msg["content"]
    assert "Notlarını listeledim." in user_msg["content"]
    assert result == "Kısa özet."


def test_summary_drops_pure_leak_messages_entirely(monkeypatch):
    _, client = _run_summarize(
        monkeypatch,
        [
            {"role": "user", "content": "selam"},
            {"role": "assistant", "content": "<|tool_call>call:x{{}}<tool_call|>"},
        ],
    )
    user_msg = next(
        m for m in client.payloads[0]["json"]["messages"] if m["role"] == "user"
    )
    assert "assistant:" not in user_msg["content"]  # emptied row dropped


def test_summary_user_messages_are_never_sanitized(monkeypatch):
    _, client = _run_summarize(
        monkeypatch,
        [{"role": "user", "content": 'bana call:create_note{{}} yazan kodu göster'}],
    )
    user_msg = next(
        m for m in client.payloads[0]["json"]["messages"] if m["role"] == "user"
    )
    assert "call:create_note{{}}" in user_msg["content"]


def test_summary_output_is_sanitized_before_storage(monkeypatch):
    """Even if the summarizer model echoes artifacts despite the prompt,
    the returned summary must be clean before update_session_summary().
    """
    result, _ = _run_summarize(
        monkeypatch,
        [{"role": "user", "content": "merhaba"}],
        reply="Özet <|tool_call|>call:x{}<tool_call|> devamı",
    )
    assert result == "Özet devamı"
