"""Hybrid session title generation: RAKE (instant) + LLM (enriched).

Layer 1 — RAKE: Generates a title from the first user message in <1ms.
           Used as the instant sidebar label when the session is created.

Layer 2 — LLM: Generates an enriched title from the full conversation
           (user + assistant) in the background after the first reply.
           Replaces the RAKE title with a higher-quality one.

No external dependencies. Zero RAM overhead for RAKE.
LLM call runs as a background task — never blocks the chat response.
"""

import re

# ═══════════════════════════════════════════════════════════════
# Stop Words (Turkish + English + common chat filler)
# ═══════════════════════════════════════════════════════════════

_STOP_WORDS = frozenset({
    # Turkish
    "bir", "ve", "bu", "da", "de", "ile", "için", "mı", "mi", "mu", "mü",
    "ne", "nasıl", "var", "yok", "olan", "gibi", "daha", "çok", "az",
    "ben", "sen", "biz", "siz", "onlar", "o", "şu", "her", "hiç",
    "ama", "fakat", "çünkü", "eğer", "ki", "bile", "sadece", "yalnız",
    "hem", "ya", "veya", "ise", "sonra", "önce", "arasında",
    "bana", "sana", "onu", "bunu", "şunu", "bize", "size", "onlara",
    "gönder", "söyle", "ver", "et", "yap", "yapmak", "etmek", "olmak",
    "lütfen", "şimdi", "olur", "olsun", "olarak", "göster", "bul",
    # English
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "can", "may", "might", "shall", "need", "dare", "ought",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her",
    "us", "them", "my", "your", "his", "its", "our", "their",
    "this", "that", "these", "those", "what", "which", "who", "whom",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "into", "about", "between", "through", "after", "before", "above",
    "over", "under", "up", "down", "out", "off", "not", "no", "nor",
    "but", "or", "and", "if", "then", "than", "so", "very", "just",
    "also", "too", "more", "most", "some", "any", "how", "when",
    "where", "why", "all", "each", "every", "both", "few", "many",
    "much", "own", "same", "other", "such", "please", "check",
    "create", "explain", "get", "show", "write", "give", "tell", "use",
    "could", "please", "thanks", "thank",
})


def generate_rake_title(text: str, max_words: int = 5) -> str:
    """Extract a session title from user input using RAKE.

    - Strips emails, URLs, special characters
    - Splits on stop words to find candidate phrases
    - Returns the longest/most meaningful phrase
    - < 1ms execution time, zero dependencies
    """
    # Sanitize: strip emails, URLs
    clean = re.sub(r'\S+@\S+\.\S+', '', text)
    clean = re.sub(r'https?://\S+', '', clean)
    clean = re.sub(r'[^\w\s]', ' ', clean)
    clean = clean.strip()
    if not clean:
        return text[:40] + ('\u2026' if len(text) > 40 else '')

    words = re.findall(r'\w+', clean.lower())
    phrases: list[list[str]] = []
    current: list[str] = []
    for w in words:
        if w in _STOP_WORDS or len(w) < 2 or w.isdigit():
            if current:
                phrases.append(current)
                current = []
        else:
            current.append(w)
    if current:
        phrases.append(current)

    if not phrases:
        fallback = [w for w in words if w not in _STOP_WORDS and not w.isdigit()]
        if fallback:
            return ' '.join(fallback[:max_words]).title()
        return text[:40] + ('\u2026' if len(text) > 40 else '')

    best = max(phrases, key=lambda p: (len(p), sum(len(w) for w in p)))
    phrase_str = ' '.join(best[:max_words])

    # Restore original casing if possible
    match = re.search(re.escape(phrase_str), clean, re.IGNORECASE)
    if match:
        return match.group(0).strip().title()
    return phrase_str.title()


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
            import requests as _req
            litert_url = get("LITERT_URL", "http://localhost:9379")
            payload = {
                "model": "gemma4-e2b",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 15,
                "temperature": 0.1,
            }
            r = _req.post(
                f"{litert_url}/v1/chat/completions",
                json=payload, timeout=15,
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"].strip()
        else:
            # Ollama path — reuse existing chat_with_ollama
            from llm import chat_with_ollama
            raw = await chat_with_ollama(
                [{"role": "user", "content": prompt}],
                think=False, use_tools=False,
            )

        # Clean output
        title = raw.strip('"\'')
        title = re.sub(r'^Title:\s*', '', title, flags=re.IGNORECASE)
        title = title.strip('.').strip()
        # Sanity: must be non-empty and reasonable length
        if title and 2 <= len(title) <= 60:
            return title
        return None
    except Exception:
        return None
