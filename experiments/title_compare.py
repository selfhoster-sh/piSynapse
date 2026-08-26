#!/usr/bin/env python3
"""Benchmark and comparison script for Session Title Generation algorithms.

Compares 4 candidate approaches:
1. Baseline: Naive prefix truncation (content[:40])
2. YAKE!: Statistical & contextual keyword/phrase extraction
3. spaCy NP: Grammatical Noun Phrase chunking (POS Tagging)
4. RAKE: Rapid Automatic Keyword Extraction (Co-occurrence scoring)

Measures:
- Latency (ms) per title
- Memory overhead
- Readability & Grammar integrity across TR, EN, and Mixed queries
"""

import time
import re
import yake
import spacy

# Load spaCy model for English (and blank pipeline for fallback)
nlp_en = spacy.load("en_core_web_sm")

# Test queries covering real user chat patterns (commands, questions, short, medium, tech, mixed)
TEST_QUERIES = [
    # Turkish Commands & Questions
    ("TR-1", "İstanbul için yarınki hava durumu bilgisini sa.dg725@proton.me adresine gönder"),
    ("TR-2", "Bana gelen son e-postaları özetleyip önemli olanları işaretler misin"),
    ("TR-3", "Yarın saat 14:00 için ekiple proje değerlendirme toplantısı notu oluştur"),
    ("TR-4", "Akşama ne yemek pişirsem pratik ve lezzetli bir tarif önerisi ver"),
    ("TR-5", "Python aiosqlite veritabanı bağlantısı kilitlenme hatasını nasıl çözerim"),
    ("TR-6", "Merhaba bugün çok yorgunum biraz muhabbet edelim"),
    ("TR-7", "Dolar ve Euro kurları bugün kaç lira oldu"),

    # English Commands & Questions
    ("EN-1", "What is the current weather forecast for London tomorrow morning"),
    ("EN-2", "Please check my unread emails and forward the urgent ones to my manager"),
    ("EN-3", "Create a new calendar event for team standup tomorrow at 10 AM"),
    ("EN-4", "How do I fix memory leak issues in Node.js express application"),
    ("EN-5", "Can you explain quantum computing in simple terms for a beginner"),

    # Short / Edge Cases
    ("EDGE-1", "Hava durumu"),
    ("EDGE-2", "Python async function"),
    ("EDGE-3", "Thanks!"),
]


# --- Approach 0: Naive Truncation ---
def title_naive(text: str) -> str:
    clean = text.strip().replace("\n", " ")
    return clean[:40] + ("\u2026" if len(clean) > 40 else "")


# --- Approach 1: YAKE! (Statistical) ---
kw_extractor_tr = yake.KeywordExtractor(lan="tr", n=3, dedupLim=0.9, top=1)
kw_extractor_en = yake.KeywordExtractor(lan="en", n=3, dedupLim=0.9, top=1)

def title_yake(text: str) -> str:
    # Quick lang check
    extractor = kw_extractor_en if any(w in text.lower() for w in ["what", "how", "please", "can", "check", "create"]) else kw_extractor_tr
    keywords = extractor.extract_keywords(text)
    if keywords:
        # YAKE scores lower = better
        best_phrase = keywords[0][0]
        # Capitalize nicely
        return " ".join(w.capitalize() for w in best_phrase.split())
    return title_naive(text)


# --- Approach 2: spaCy Noun Phrase (Grammatical POS) ---
def title_spacy_np(text: str) -> str:
    doc = nlp_en(text)
    # Collect noun chunks
    chunks = [chunk.text.strip() for chunk in doc.noun_chunks]
    if chunks:
        # Return the longest/first meaningful noun chunk
        best = max(chunks, key=len) if len(chunks) > 1 else chunks[0]
        # Clean leading articles/determiners (a, an, the)
        best = re.sub(r"^(the|a|an)\s+", "", best, flags=re.IGNORECASE)
        return best.capitalize()
    
    # Fallback for non-EN or failed NP: extract NOUN/PROPN tokens
    nouns = [tok.text for tok in doc if tok.pos_ in ("NOUN", "PROPN")]
    if nouns:
        return " ".join(nouns[:3]).capitalize()
    return title_naive(text)


# --- Approach 3: RAKE (Co-occurrence Phrase Extraction) ---
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
    # 1. Split into candidate phrases by punctuation and stop words
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
        return title_naive(text)

    # 2. Score phrases by length and word co-occurrence
    best_phrase = max(phrases, key=lambda p: (len(p), sum(len(w) for w in p)))
    # Restore original casing if possible
    phrase_str = " ".join(best_phrase)
    # Find in original text to match casing
    match = re.search(re.escape(phrase_str), text, re.IGNORECASE)
    if match:
        return match.group(0).strip().title()
    return phrase_str.title()


def run_benchmark():
    print("=" * 110)
    print(f"{'ID':<8} | {'Naive (Original)':<30} | {'YAKE! (Statistical)':<25} | {'spaCy (Grammar NP)':<25} | {'RAKE (Phrase)'}")
    print("=" * 110)

    timings = {"naive": [], "yake": [], "spacy": [], "rake": []}

    for q_id, query in TEST_QUERIES:
        # Naive
        t0 = time.perf_counter()
        out_naive = title_naive(query)
        timings["naive"].append((time.perf_counter() - t0) * 1000)

        # YAKE!
        t0 = time.perf_counter()
        out_yake = title_yake(query)
        timings["yake"].append((time.perf_counter() - t0) * 1000)

        # spaCy NP
        t0 = time.perf_counter()
        out_spacy = title_spacy_np(query)
        timings["spacy"].append((time.perf_counter() - t0) * 1000)

        # RAKE
        t0 = time.perf_counter()
        out_rake = title_rake(query)
        timings["rake"].append((time.perf_counter() - t0) * 1000)

        print(f"{q_id:<8} | {out_naive[:30]:<30} | {out_yake[:25]:<25} | {out_spacy[:25]:<25} | {out_rake[:25]}")

    print("=" * 110)
    print("\nPERFORMANCE LATENCY SUMMARY (Pi5):")
    for name, ts in timings.items():
        avg_ms = sum(ts) / len(ts)
        print(f"  - {name.upper():<10}: {avg_ms:.3f} ms / title")


if __name__ == "__main__":
    run_benchmark()
