"""Session title generation: first 4 words (instant) + LLM (enriched).

Layer 1 — First 4 words: instant sidebar title from the first user message.
Layer 2 — LLM: 2-5 word enriched title from full conversation (background).
"""

import re


def generate_title_first4(text: str) -> str:
    """First 4 words of user message as instant title. No language list."""
    clean = text.strip()
    if not clean:
        return "Yeni Sohbet"
    # Split on whitespace, take first 4, strip trailing punctuation
    words = clean.split()
    first4 = " ".join(words[:4])
    # Truncate to 40 chars max to avoid overflow, add ellipsis if needed
    if len(first4) > 40:
        first4 = first4[:40].rsplit(" ", 1)[0] + "…"
    return first4

# Keep alias for backward compat (db.py still imports this name)
def generate_rake_title(text: str, max_words: int = 5) -> str:  # noqa: D401
    return generate_title_first4(text)


# ═══════════════════════════════════════════════════════════════
# LLM Title Generation (called as background task)
# ═══════════════════════════════════════════════════════════════

_TITLE_PROMPT = """Based on this conversation, generate a short session title (2-5 words).
Rules:
- Only output the title text, nothing else
- Be concise and descriptive
- Use the same language as the user
- Focus on the TOPIC, not the action verbs
- Do not include email addresses, URLs, or personal info
- Do not include quotes, punctuation, or "Title:" prefix

User: {user_msg}
Assistant: {assistant_msg}

Title:"""


async def generate_llm_title(user_msg: str, assistant_msg: str) -> str | None:
    """Generate an enriched session title via LLM.

    Returns the title string, or None on failure (caller keeps RAKE title).
    This function is designed to be called as a background task — it should
    never raise exceptions that crash the server.
    """
    try:
        from config import get
        backend = get("LLM_BACKEND", "litert")

        prompt = _TITLE_PROMPT.format(
            user_msg=user_msg,
            assistant_msg=assistant_msg[:500],
        )

        if backend == "litert":
            import httpx
            litert_url = get("LITERT_BASE_URL", "http://localhost:9379")
            model = get("LLM_MODEL", "gemma4-e2b").replace(":", "-")
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 15,
                "temperature": 0.1,
            }
            async with httpx.AsyncClient(timeout=15) as _client:
                r = await _client.post(
                    f"{litert_url}/v1/chat/completions",
                    json=payload,
                )
                r.raise_for_status()
                raw = r.json()["choices"][0]["message"]["content"].strip()
        else:
            # Ollama path — reuse existing chat_with_ollama (no tools for title)
            from llm import chat_with_ollama
            raw = await chat_with_ollama(
                [{"role": "user", "content": prompt}],
                think=False, intent="question", tool_group=None,
            )
            # chat_with_ollama returns dict, extract reply
            if isinstance(raw, dict):
                raw = raw.get("reply", "") or raw.get("content", "") or str(raw)

        # Clean output
        title = raw.strip('"\'')
        title = re.sub(r'^Title:\s*', '', title, flags=re.IGNORECASE)
        title = title.strip('.').strip()
        # Sanity: 2-5 words, 2-60 chars
        words = title.split()
        if title and 2 <= len(words) <= 5 and 2 <= len(title) <= 60:
            return title
        return None
    except Exception:
        return None
