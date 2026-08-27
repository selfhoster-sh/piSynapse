#!/usr/bin/env python3
"""Real LLM title generation test — calls litert:9379 for actual title output.

Compares:
1. RAKE (instant, <1ms)
2. LLM (real call, measures actual latency)
"""

import re
import time

import requests

LITERT = "http://localhost:9379/v1/chat/completions"
MODEL = "gemma4-e2b"

# --- RAKE ---
STOP_WORDS = {
    "bir", "ve", "bu", "da", "de", "ile", "için", "mı", "mi", "mu", "mü",
    "ne", "nasıl", "var", "yok", "olan", "gibi", "daha", "çok", "az",
    "ben", "sen", "biz", "siz", "onlar", "o", "şu", "her", "hiç",
    "ama", "fakat", "çünkü", "eğer", "ki", "bile", "sadece", "yalnız",
    "bana", "sana", "onu", "bunu", "şunu", "gönder", "söyle", "ver", "et", "yap",
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "can", "may", "might", "what", "how", "when", "where", "why",
    "please", "check", "create", "explain", "get", "show", "in", "on", "at",
    "to", "for", "of", "with", "by", "from", "as", "into", "about", "your", "my"
}

def title_rake(text: str) -> str:
    words = re.findall(r"\w+", text.lower())
    phrases = []
    current = []
    for w in words:
        if w in STOP_WORDS or len(w) < 2:
            if current:
                phrases.append(current)
                current = []
        else:
            current.append(w)
    if current:
        phrases.append(current)
    if not phrases:
        return text[:40]
    best_phrase = max(phrases, key=lambda p: (len(p), sum(len(w) for w in p)))
    return " ".join(best_phrase).title()


# --- Real LLM Title Generation ---
def title_llm(user_msg: str, assistant_msg: str) -> tuple[str, float]:
    """Call real LLM to generate a session title. Returns (title, latency_ms)."""
    prompt = f"""Based on this conversation between a user and an AI assistant, generate a short session title (2-5 words).

Rules:
- Only output the title, nothing else
- Be concise and descriptive
- Use the language of the conversation (Turkish if user wrote in Turkish)
- Focus on the TOPIC, not the action
- Do not include email addresses, URLs, or personal info

User: {user_msg}
Assistant: {assistant_msg[:300]}

Title:"""

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 20,
        "temperature": 0.1,
    }

    t0 = time.perf_counter()
    try:
        r = requests.post(LITERT, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        title = data["choices"][0]["message"]["content"].strip().strip('"').strip("'")
        # Clean up: remove "Title:" prefix if LLM added it
        title = re.sub(r"^Title:\s*", "", title, flags=re.IGNORECASE)
        latency = (time.perf_counter() - t0) * 1000
        return title, latency
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        return f"ERROR: {e}", latency


# --- Test Cases ---
TEST_CASES = [
    ("İstanbul için yarınki hava durumu bilgisini sa.dg725@proton.me adresine gönder",
     "İstanbul için yarın hava durumu şöyle: Sabah parçalı bulutlu 18°C, öğleden sonra güneşli 24°C. Yağış yok. E-posta gönderiliyor."),
    ("Bana gelen son e-postaları özetleyip önemli olanları işaretler misin",
     "Son 5 e-posta: 1) Proje deadline hatırlatması (önemli), 2) Fatura, 3) Newsletter, 4) Takvim daveti, 5) Spam. Önemliler yıldızlandı."),
    ("Python aiosqlite veritabanı bağlantısı kilitlenme hatasını nasıl çözerim",
     "aiosqlite kilitlenme WAL mode ile çözülür. PRAGMA busy_timeout=5000 ekleyin ve write işlemlerini serialize edin."),
    ("What is the current weather forecast for London tomorrow",
     "Tomorrow in London: partly cloudy, high 22°C, low 15°C. 20% chance of rain afternoon. Wind 12 km/h SW."),
    ("How do I fix memory leak issues in Node.js express application",
     "Node.js memory leaks: 1) Check closure references, 2) Remove unused event listeners, 3) Use process.memoryUsage() to monitor heap."),
    ("Akşama ne yemek pişirsem pratik bir tarif öner",
     "Pratik akşam yemeği: Tavuk sote. Malzemeler: tavuk göğsü, biber, soğan, domates. Süre: 25 dakika."),
    ("Merhaba nasılsın bugün hava çok güzel",
     "Merhaba! İyiyim, teşekkür ederim. Evet bugün hava güzel, dışarı çıkmak için harika bir gün."),
]


def main():
    print("=" * 100)
    print("REAL LLM TITLE GENERATION TEST (litert:9379 / gemma4-e2b)")
    print("=" * 100)
    print()

    rake_times = []
    llm_times = []

    for i, (user, assistant) in enumerate(TEST_CASES):
        # RAKE
        t0 = time.perf_counter()
        rake_title = title_rake(user)
        rake_ms = (time.perf_counter() - t0) * 1000
        rake_times.append(rake_ms)

        # Real LLM
        llm_title, llm_ms = title_llm(user, assistant)
        llm_times.append(llm_ms)

        print(f"--- Test {i+1} ---")
        print(f"  User:      {user[:75]}...")
        print(f"  Assistant: {assistant[:75]}...")
        print()
        print(f"  RAKE:  {rake_title:<40} ({rake_ms:.3f} ms)")
        print(f"  LLM:   {llm_title:<40} ({llm_ms:.1f} ms)")
        print()

    avg_rake = sum(rake_times) / len(rake_times)
    avg_llm = sum(llm_times) / len(llm_times)

    print("=" * 100)
    print("REAL LATENCY SUMMARY (Pi5 / gemma4-e2b):")
    print(f"  RAKE:  {avg_rake:.3f} ms  (instant)")
    print(f"  LLM:   {avg_llm:.0f} ms  ({avg_llm/1000:.1f} seconds)")
    print(f"  Ratio: LLM is {avg_llm/avg_rake:.0f}x slower than RAKE")
    print("=" * 100)


if __name__ == "__main__":
    main()
