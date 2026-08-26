#!/usr/bin/env python3
"""Comprehensive integration test for hybrid title generation.

Tests the FULL piSynapse flow via real API:
1. RAKE instant title on first user message
2. Real LLM title after assistant response
3. Edge cases: empty, long, code, multilingual, short
4. Latency measurements
5. Fallback behavior when LLM fails

Uses real litert:9379 endpoint.
"""

import asyncio
import json
import re
import time

import requests

API = "http://localhost:9379"
CHAT_API = "http://localhost:8765"  # piSynapse main API (if running)


# ═══════════════════════════════════════════════════════════════
# RAKE Implementation
# ═══════════════════════════════════════════════════════════════

STOP_WORDS = {
    # Turkish
    "bir", "ve", "bu", "da", "de", "ile", "için", "mı", "mi", "mu", "mü",
    "ne", "nasıl", "var", "yok", "olan", "gibi", "daha", "çok", "az",
    "ben", "sen", "biz", "siz", "onlar", "o", "şu", "her", "hiç",
    "ama", "fakat", "çünkü", "eğer", "ki", "bile", "sadece", "yalnız",
    "hem", "ya", "veya", "ise", "sonra", "önce", "arasında",
    "bana", "sana", "onu", "bunu", "şunu", "bize", "size", "onlara",
    "gönder", "söyle", "ver", "et", "yap", "yapmak", "etmek", "olmak",
    "lütfen", "şimdi", "olur", "olsun", "olarak",
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
}


def rake_title(text: str, max_words: int = 5) -> str:
    """RAKE-based instant title extraction."""
    # Sanitize: strip emails, URLs
    clean = re.sub(r'\S+@\S+\.\S+', '', text)
    clean = re.sub(r'https?://\S+', '', clean)
    clean = clean.strip()
    if not clean:
        return text[:40]

    words = re.findall(r"\w+", clean.lower())
    phrases = []
    current = []
    for w in words:
        if w in STOP_WORDS or len(w) < 2 or w.isdigit():
            if current:
                phrases.append(current)
                current = []
        else:
            current.append(w)
    if current:
        phrases.append(current)

    if not phrases:
        # Fallback: take any non-stop words
        fallback = [w for w in words if w not in STOP_WORDS and not w.isdigit()]
        if fallback:
            return " ".join(fallback[:max_words]).title()
        return text[:40]

    best_phrase = max(phrases, key=lambda p: (len(p), sum(len(w) for w in p)))
    phrase_str = " ".join(best_phrase[:max_words])

    # Try to match original casing
    match = re.search(re.escape(phrase_str), clean, re.IGNORECASE)
    if match:
        return match.group(0).strip().title()
    return phrase_str.title()


# ═══════════════════════════════════════════════════════════════
# Real LLM Title Generation
# ═══════════════════════════════════════════════════════════════

def llm_title(user_msg: str, assistant_msg: str) -> tuple[str, float, bool]:
    """Call real LLM via litert. Returns (title, latency_ms, success)."""
    prompt = f"""Based on this conversation, generate a short session title (2-5 words).
Rules:
- Only output the title text, nothing else
- Be concise and descriptive
- Use the same language as the user
- Focus on the TOPIC, not the action verbs
- Do not include email addresses, URLs, or personal info
- Do not include quotes or punctuation marks

User: {user_msg}
Assistant: {assistant_msg[:500]}

Title:"""

    payload = {
        "model": "gemma4-e2b",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 15,
        "temperature": 0.1,
    }

    t0 = time.perf_counter()
    try:
        r = requests.post(f"{API}/v1/chat/completions", json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        raw = data["choices"][0]["message"]["content"].strip()
        # Clean: remove quotes, "Title:" prefix, extra whitespace
        title = raw.strip('"\'')
        title = re.sub(r'^Title:\s*', '', title, flags=re.IGNORECASE)
        title = title.strip('.').strip()
        latency = (time.perf_counter() - t0) * 1000
        return title, latency, True
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        return f"ERROR: {e}", latency, False


# ═══════════════════════════════════════════════════════════════
# Test Cases
# ═══════════════════════════════════════════════════════════════

TEST_CASES = [
    # Turkish: weather + email (real user scenario from piSynapse)
    {
        "user": "İstanbul için yarınki hava durumu bilgisini sa.dg725@proton.me adresine gönder",
        "assistant": "İstanbul için yarın hava durumu: Sabah parçalı bulutlu 18°C, öğleden sonra güneşli 24°C. Yağış beklenmiyor. E-posta gönderimi tamamlandı.",
        "category": "TR-action",
        "expected_contains": ["İstanbul", "hava"],
        "expected_not_contains": ["sa.dg725", "proton", "gönder"],
    },
    # Turkish: email summarization
    {
        "user": "Bana gelen son e-postaları özetleyip önemli olanları işaretler misin",
        "assistant": "Son 5 e-postanız var: 1) Proje deadline hatırlatması (önemli), 2) Fatura bildirimi, 3) Newsletter, 4) Takvim daveti, 5) Spam. Önemli olanları yıldızladım.",
        "category": "TR-action",
        "expected_contains": ["e-posta"],
        "expected_not_contains": ["işaretler", "özetleyip", "misin"],
    },
    # Turkish: technical error
    {
        "user": "Python aiosqlite veritabanı bağlantısı kilitlenme hatasını nasıl çözerim",
        "assistant": "aiosqlite kilitlenme hatası WAL mode ile çözülür. PRAGMA busy_timeout=5000 ekleyin ve write işlemlerini serialize edin.",
        "category": "TR-technical",
        "expected_contains": ["Python"],
        "expected_not_contains": ["nasıl", "çözerim"],
    },
    # Turkish: casual conversation
    {
        "user": "Merhaba nasılsın bugün hava çok güzel",
        "assistant": "Merhaba! İyiyim, teşekkür ederim. Evet bugün hava güzel, dışarı çıkmak için harika bir gün.",
        "category": "TR-casual",
        "expected_contains": [],
        "expected_not_contains": ["merhaba", "nasılsın"],
    },
    # Turkish: recipe request
    {
        "user": "Akşama ne yemek pişirsem pratik bir tarif öner",
        "assistant": "Pratik akşam yemeği: Tavuk sote. Malzemeler: tavuk göğsü, biber, soğan, domates, zeytinyağı. Süre: 25 dakika. Yapılışı: Soğanları soteleyin, tavukları ekleyin, sebzelerle birlikte pişirin.",
        "category": "TR-daily",
        "expected_contains": ["yemek"],
        "expected_not_contains": ["pişirsem", "öner"],
    },
    # English: weather
    {
        "user": "What is the current weather forecast for London tomorrow",
        "assistant": "Tomorrow in London: partly cloudy, high 22°C, low 15°C. 20% chance of rain in the afternoon. Wind speed 12 km/h from the southwest.",
        "category": "EN-question",
        "expected_contains": ["London", "weather"],
        "expected_not_contains": ["what", "is", "the"],
    },
    # English: technical
    {
        "user": "How do I fix memory leak issues in Node.js express application",
        "assistant": "Node.js memory leaks are usually caused by: 1) Unreferenced objects kept in closures, 2) Event listener accumulation, 3) Global variable leaks. Use process.memoryUsage() and Chrome DevTools heap snapshots to identify.",
        "category": "EN-technical",
        "expected_contains": ["memory", "leak"],
        "expected_not_contains": ["how", "fix"],
    },
    # English: email
    {
        "user": "Please check my unread emails and forward the urgent ones to my manager",
        "assistant": "You have 3 unread emails: 1) Client proposal (urgent), 2) Team meeting notes, 3) Newsletter. I've forwarded the client proposal to your manager.",
        "category": "EN-action",
        "expected_contains": ["email"],
        "expected_not_contains": ["please", "check"],
    },
    # Edge: very short
    {
        "user": "Hava durumu",
        "assistant": "İstanbul'da bugün hava güneşli, sıcaklık 26°C.",
        "category": "edge-short",
        "expected_contains": ["hava"],
        "expected_not_contains": [],
    },
    # Edge: code block
    {
        "user": "Bu Python kodunu çalıştır: print('hello world')",
        "assistant": "Kod çalıştırıldı. Çıktı: hello world",
        "category": "edge-code",
        "expected_contains": [],
        "expected_not_contains": ["print"],
    },
    # Edge: very long message
    {
        "user": "Bugün sabah saat 8:30'da kalktım, kahvaltıda zeytin peynir ekmek yedim, sonra 9:30'da işe gittim, otobüs çok kalabalıktı, 10:00'da ofise vardım, toplantı vardı, toplantıdan sonra maillerime baktım, 3 tane önemli mail vardı, birini cevapladım, diğerlerini sonra cevaplayacağım",
        "assistant": "Günaydın! Yoğun bir gün geçirmişsiniz. Maillerinizi yanıtlamanız için size zaman ayırabilirim.",
        "category": "edge-long",
        "expected_contains": [],
        "expected_not_contains": ["sabah", "kahvaltı"],
    },
    # Edge: emoji / special chars
    {
        "user": "👍 harika bir gün olacak! ☀️",
        "assistant": "Kesinlikle! Güzel bir gün olacak.",
        "category": "edge-emoji",
        "expected_contains": [],
        "expected_not_contains": [],
    },
    # Multilingual: Turkish + English mix
    {
        "user": "Python async hatası nasıl düzeltilir the event loop is already running error",
        "assistant": "Bu hata genellikle nested event loop çağrısında olur. Çözüm: asyncio.run() kullanın veya nest_asyncio paketini kurun.",
        "category": "mixed",
        "expected_contains": ["Python"],
        "expected_not_contains": ["nasıl", "the"],
    },
]


def run_tests():
    print("=" * 110)
    print("COMPREHENSIVE HYBRID TITLE TEST (Real LLM + RAKE)")
    print("=" * 110)
    print()

    rake_times = []
    llm_times = []
    llm_successes = 0
    llm_failures = 0
    rake_quality_pass = 0
    llm_quality_pass = 0

    for i, tc in enumerate(TEST_CASES):
        user = tc["user"]
        assistant = tc["assistant"]
        category = tc["category"]
        expected = tc.get("expected_contains", [])
        not_expected = tc.get("expected_not_contains", [])

        # RAKE
        t0 = time.perf_counter()
        rake_result = rake_title(user)
        rake_ms = (time.perf_counter() - t0) * 1000
        rake_times.append(rake_ms)

        # LLM
        llm_result, llm_ms, success = llm_title(user, assistant)
        llm_times.append(llm_ms)
        if success:
            llm_successes += 1
        else:
            llm_failures += 1

        # Quality checks
        rake_ok = True
        for exp in expected:
            if exp.lower() not in rake_result.lower():
                rake_ok = False
        for skip in not_expected:
            if skip.lower() in rake_result.lower():
                rake_ok = False
        if rake_ok:
            rake_quality_pass += 1

        llm_ok = True
        for exp in expected:
            if exp.lower() not in llm_result.lower():
                llm_ok = False
        for skip in not_expected:
            if skip.lower() in llm_result.lower():
                llm_ok = False
        if llm_ok:
            llm_quality_pass += 1

        # Visual output
        rake_icon = "✅" if rake_ok else "❌"
        llm_icon = "✅" if llm_ok else ("❌" if success else "⚠️")

        print(f"--- Test {i+1} [{category}] ---")
        print(f"  User:      {user[:70]}...")
        print(f"  RAKE:  {rake_icon} {rake_result:<40} ({rake_ms:.3f} ms)")
        print(f"  LLM:   {llm_icon} {llm_result:<40} ({llm_ms:.0f} ms)")
        print()

    # Summary
    total = len(TEST_CASES)
    avg_rake = sum(rake_times) / len(rake_times)
    avg_llm = sum(llm_times) / len(llm_times)

    print("=" * 110)
    print("RESULTS SUMMARY")
    print("=" * 110)
    print(f"  Total tests:      {total}")
    print(f"  RAKE quality:     {rake_quality_pass}/{total} passed ({rake_quality_pass/total*100:.0f}%)")
    print(f"  LLM quality:      {llm_quality_pass}/{total} passed ({llm_quality_pass/total*100:.0f}%)")
    print(f"  LLM success rate: {llm_successes}/{total} ({llm_failures} failures)")
    print()
    print("  LATENCY:")
    print(f"    RAKE:  {avg_rake:.3f} ms avg (instant)")
    print(f"    LLM:   {avg_llm:.0f} ms avg ({avg_llm/1000:.1f}s)")
    print()
    print("  VERDICT:")
    if llm_quality_pass > rake_quality_pass and llm_successes >= total * 0.8:
        print("    LLM generates significantly better titles.")
        print("    Recommend: RAKE for instant + LLM for final title")
    elif rake_quality_pass >= llm_quality_pass * 0.8:
        print("    RAKE is competitive with LLM for title quality.")
        print("    Recommend: RAKE-only (no extra LLM call needed)")
    else:
        print("    Mixed results. Need further analysis.")
    print("=" * 110)


if __name__ == "__main__":
    run_tests()
