#!/usr/bin/env python3
"""ROADMAP destek deneyi: MiniLM vs multilingual-e5-small intent routing karşılaştırması.

- Aynı _TOOL_EMBED_CORPUS iki modelle embed edilir (e5'te 'passage: ' prefix'iyle).
- Test cümleleri (e5'te 'query: ' prefix'iyle) her iki modelde skorlanır.
- Rapor: best_sim, second_sim, margin, embedding-kararı (+keyword simülasyonu).

Çalıştır: ./venv/bin/python experiments/intent_embed_compare.py
"""
import sys

sys.path.insert(0, "/home/salih/piSynapse")

import numpy as np
from fastembed import TextEmbedding

from llm.intent import _TOOL_EMBED_CORPUS

MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
E5 = "intfloat/multilingual-e5-large"

# (mesaj, beklenen_grup) — ilk 8 kullanıcı istediği + saha loglarından gerçek vakalar
CASES = [
    ("yarın toplantıya katılacağım not düş",        "notes"),     # geceki belirsiz vaka
    ("toplantıyı unutma diye not al",               "notes"),
    ("randevuyu hatırlatıcı olarak yaz",            "tasks"),
    ("cuma günkü etkinlik için not düş",            "notes"),
    ("hava nasıl yarın",                            "weather"),
    ("e-postalarımı kontrol et",                    "email"),
    ("görev listeme ekle",                          "tasks"),
    ("sağlık durumumu unutma",                      "memory"),
    # saha loglarından gerçek vakalar:
    ("şemsiye almalı mıyım bugün?",                 "question"),
    ("notlarımı listele",                           "notes"),
    ("yarınki toplantıyı hatırlat",                 "calendar"),
    ("bu hafta kimden mail gelmiş bakar mısın",     "email"),
    ("süt almayı unutma",                           "memory"),   # tricky: unutma→memory, süt→task?
    ("yarın doktor randevum var",                   "calendar"),
]

def load(name):
    print(f"yükleniyor: {name} ...", flush=True)
    return TextEmbedding(model_name=name)

def vecs(model, texts):
    return np.array(list(model.embed(texts)))

def cos(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def score(qv, corpus_vecs, groups):
    sims = [cos(qv, cv) for cv in corpus_vecs]
    order = sorted(range(len(sims)), key=lambda i: -sims[i])
    best = order[0]
    second = order[1]
    return sims[best], sims[second], sims[best] - sims[second], groups[best]

import resource
import time


def _rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # KB->MB

def main():
    corpus_groups = [g for g, _ in _TOOL_EMBED_CORPUS]
    corpus_texts = [t for _, t in _TOOL_EMBED_CORPUS]

    print(f"başlangıç RSS: {_rss_mb():.0f} MB", flush=True)
    t0 = time.perf_counter()
    m_mini = load(MINILM)
    tl_mini = time.perf_counter()-t0
    mini_corpus = vecs(m_mini, corpus_texts)


    t0 = time.perf_counter()
    m_e5 = load(E5)
    tl_e5 = time.perf_counter()-t0
    e5_corpus = vecs(m_e5, ["passage: " + t for t in corpus_texts])
    print(f"load süreleri: MiniLM={tl_mini:.1f}s  E5={tl_e5:.1f}s | dim: "
          f"{len(mini_corpus[0])} vs {len(e5_corpus[0])} | RSS artışı toplam: {_rss_mb():.0f} MB",
          flush=True)

    # kaba hız ölçümü: 50 cümle (test seti × tekrar) embed süresi
    speed_texts = [m for m,_ in CASES] * 7   # ~98 cümle ≈ 50+
    t0=time.perf_counter()
    vecs(m_mini, speed_texts)
    sp_mini=time.perf_counter()-t0
    t0=time.perf_counter()
    vecs(m_e5,  speed_texts)
    sp_e5 =time.perf_counter()-t0
    print(f"embed hızı ({len(speed_texts)} cümle): MiniLM={sp_mini:.2f}s  E5={sp_e5:.2f}s\n", flush=True)

    rows = []
    for msg, expected in CASES:
        qv_m = vecs(m_mini, [msg])[0]
        b, s, margin, grp = score(qv_m, mini_corpus, corpus_groups)
        emb_ok_m = (b >= 0.50 and margin >= 0.05)

        qv_e = vecs(m_e5, ["query: " + msg])[0]
        be, se, margine, grpe = score(qv_e, e5_corpus, corpus_groups)
        emb_ok_e = (be >= 0.50 and margine >= 0.05)

        rows.append((msg, expected,
                     b, margin, grp if emb_ok_m else "-", emb_ok_m,
                     be, margine, grpe if emb_ok_e else "-", emb_ok_e))

    hdr = f"{'mesaj':38s} {'bekl':9s} | {'MiniLM sim':>10s} {'marg':>6s} {'grup':9s} {'emb-ok':6s} | {'E5 sim':>10s} {'marg':>6s} {'grup':9s} {'emb-ok':6s}"
    print("\n" + hdr)
    print("-" * len(hdr))
    for msg, exp, bm, mg, g, ok, be, me, ge, oke in rows:
        print(f"{msg[:36]:38s} {exp:9s} | {bm:10.3f} {mg:6.3f} {g or '-':9s} {str(ok):6s} | {be:10.3f} {me:6.3f} {ge or '-':9s} {str(oke):6s}")

    import statistics
    mm = [r[3] for r in rows]
    me5 = [r[7] for r in rows]
    thin_m = sum(1 for x in mm if x < 0.10)
    thin_e = sum(1 for x in me5 if x < 0.10)
    acc_m = sum(1 for r in rows if r[4] and r[5])
    acc_e = sum(1 for r in rows if r[8] and r[9])
    print(f"\nORTALAMA MARGIN : MiniLM={statistics.mean(mm):.3f}  E5={statistics.mean(me5):.3f}")
    print(f"İNCE MARJ (<0.10): MiniLM={thin_m}/{len(rows)}  E5={thin_e}/{len(rows)}")
    print(f"EMBEDDING KARARI: MiniLM={acc_m}/{len(rows)}  E5={acc_e}/{len(rows)}")

if __name__ == "__main__":
    main()
