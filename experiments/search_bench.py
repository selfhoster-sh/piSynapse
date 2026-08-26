#!/usr/bin/env python3
"""Benchmark: LIKE vs FTS5 for session message search on SQLite.

Creates a realistic conversation DB, populates it, then measures
query performance for both approaches across varying data sizes.
"""

import asyncio
import random
import sqlite3
import string
import time
from pathlib import Path

DB_PATH = Path("/tmp/opencode/search_bench.db")

# Realistic sentence fragments for generating test data
WORDS = [
    "hava", "durumu", "bugün", "yarın", "istanbul", "ankara", "izmir",
    "email", "gönder", "oku", "sil", "not", "oluştur", "takvim",
    " Toplantı", "saat", "dakika", "para", "birim", "kur", "dolar",
    "euro", "piyasa", "borsa", "spor", "maç", "sonuç", "skor",
    "yemek", "tarif", "malzeme", "video", "müzik", "şarkı", "film",
    "hikaye", "anlat", "özet", "çeviri", "translate", "hesapla",
    "para_birimi", "gece", "gündüz", "sabah", "akşam", "öğle",
]

CONVERSATIONS = [
    ["merhaba", "bugün hava nasıl", "istanbul için hava durumunu söyle"],
    ["emailimi kontrol et", "gelen kutusunda yeni mail var mı", "önemli olanları özetle"],
    ["bir not oluştur", "toplantı notları", "yarın saat 14'te toplantı"],
    ["bugün ne pişirsem", "yemek tarifi ver", "malzemeler neler"],
    ["dolar kuru ne", "piyasa durumu", "borsa今天怎么样"],
    ["hikaye anlat", "biraz musique dinleyelim", "film öner"],
    ["çeviri yap", "this is a test sentence for translation", "özetle"],
    ["takvime bak", "yarın toplantı var mı", "haftalık plan"],
    ["notlarımı göster", "önceki notları bul", "arsiv ara"],
    ["nasılsın", "bugün çok yorgunum", "biraz dinlen"],
]


def generate_session(sid: int, num_turns: int) -> list[tuple[str, str, str]]:
    """Generate a realistic conversation with user/assistant message pairs."""
    messages = []
    conv = random.choice(CONVERSATIONS)
    for i in range(num_turns):
        user_text = conv[i % len(conv)]
        # Add some random variation
        if random.random() > 0.5:
            user_text += " " + random.choice(WORDS)
        assistant_text = f"Cevap: {user_text} hakkında bilgi"
        ts = f"2026-08-{random.randint(1,26):02d} {random.randint(8,23):02d}:{random.randint(0,59):02d}:00"
        messages.append((f"sess-{sid}", "user", user_text, ts))
        messages.append((f"sess-{sid}", "assistant", assistant_text, ts))
    return messages


def populate_db(num_sessions: int, avg_turns: int) -> int:
    """Populate the DB and return total message count."""
    DB_PATH.unlink(missing_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("""
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            summary TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            images TEXT,
            reasoning TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    conn.execute("CREATE INDEX idx_conv_session ON conversations(session_id, timestamp)")

    total = 0
    for sid in range(num_sessions):
        turns = random.randint(max(1, avg_turns - 3), avg_turns + 3)
        msgs = generate_session(sid, turns)
        conn.executemany(
            "INSERT INTO conversations (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            msgs,
        )
        # Create session row
        name = msgs[0][2][:40]
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, name) VALUES (?, ?)",
            (f"sess-{sid}", name),
        )
        total += len(msgs)

    conn.commit()

    # Create FTS5 virtual table
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts
        USING fts5(content, session_id, content='conversations', content_rowid='id')
    """)
    # Populate FTS index
    conn.execute("""
        INSERT INTO conversations_fts (rowid, content, session_id)
        SELECT id, content, session_id FROM conversations
    """)
    conn.commit()
    conn.close()
    return total


def bench_like(query: str, limit: int = 20) -> float:
    """LIKE-based search: find sessions containing the query in message content."""
    conn = sqlite3.connect(str(DB_PATH))
    start = time.perf_counter()
    rows = conn.execute("""
        SELECT DISTINCT session_id, name
        FROM conversations c
        LEFT JOIN sessions s ON s.id = c.session_id
        WHERE c.content LIKE ?
        ORDER BY c.timestamp DESC
        LIMIT ?
    """, (f"%{query}%", limit)).fetchall()
    elapsed = time.perf_counter() - start
    conn.close()
    return elapsed, rows


def bench_fts5(query: str, limit: int = 20) -> float:
    """FTS5-based search: same query on the FTS index."""
    conn = sqlite3.connect(str(DB_PATH))
    start = time.perf_counter()
    rows = conn.execute("""
        SELECT DISTINCT f.session_id, s.name
        FROM conversations_fts f
        LEFT JOIN sessions s ON s.id = f.session_id
        WHERE conversations_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, limit)).fetchall()
    elapsed = time.perf_counter() - start
    conn.close()
    return elapsed, rows


def main():
    sizes = [100, 500, 1000]
    queries = ["hava", "email", "toplantı", "not", "istanbul"]

    for num_sess in sizes:
        total = populate_db(num_sess, avg_turns=8)
        print(f"\n{'='*60}")
        print(f"Sessions: {num_sess}  |  Total messages: {total}")
        print(f"{'='*60}")
        print(f"{'Query':<15} {'LIKE (ms)':<12} {'FTS5 (ms)':<12} {'LIKE rows':<10} {'FTS5 rows':<10} {'Speedup'}")
        print("-" * 70)

        for q in queries:
            t_l, r_l = bench_like(q)
            t_f, r_f = bench_fts5(q)
            speedup = t_l / t_f if t_f > 0 else float("inf")
            print(f"{q:<15} {t_l*1000:<12.2f} {t_f*1000:<12.2f} {len(r_l):<10} {len(r_f):<10} {speedup:.1f}x")


if __name__ == "__main__":
    main()
