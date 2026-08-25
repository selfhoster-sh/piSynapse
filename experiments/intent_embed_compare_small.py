#!/usr/bin/env python3
"""MiniLM (fastembed) vs multilingual-E5-SMALL (onnxruntime, O4) — aynı 14-vaka karşılaştırması.

E5-small pooling: mean-pool + L2 norm (resmi e5 usage); prefix'ler: query:/passage:.
"""
import sys, time, json
sys.path.insert(0, "/home/salih/piSynapse")
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer
from fastembed import TextEmbedding

from llm.intent import _TOOL_EMBED_CORPUS, _keyword_group

MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
E5_DIR = "/tmp/opencode/e5s"

CASES = [
    ("yarın toplantıya katılacağım not düş",        "notes"),
    ("toplantıyı unutma diye not al",               "notes"),
    ("randevuyu hatırlatıcı olarak yaz",            "tasks"),
    ("cuma günkü etkinlik için not düş",            "notes"),
    ("hava nasıl yarın",                            "weather"),
    ("e-postalarımı kontrol et",                    "email"),
    ("görev listeme ekle",                          "tasks"),
    ("sağlık durumumu unutma",                      "memory"),
    ("şemsiye almalı mıyım bugün?",                 "question"),
    ("notlarımı listele",                           "notes"),
    ("yarınki toplantıyı hatırlat",                 "calendar"),
    ("bu hafta kimden mail gelmiş bakar mısın",     "email"),
    ("süt almayı unutma",                           "memory"),
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
    b, s = order[0], order[1]
    return sims[b], sims[s], sims[b] - sims[s], groups[b]

# ── E5-small kurulumu ──
sess = ort.InferenceSession(f"{E5_DIR}/model_O4.onnx",
                            providers=["CPUExecutionProvider"])
tok = Tokenizer.from_file(f"{E5_DIR}/tokenizer.json")
tok.enable_truncation(max_length=512)
in_names = [i.name for i in sess.get_inputs()]
print("E5 onnx girdileri:", in_names)

def e5_embed(texts, prefix=""):
    out = []
    for t in texts:
        enc = tok.encode(prefix + t)
        ids = [enc.ids]
        mask = [enc.attention_mask]
        feed = {"input_ids": __import__("numpy").array(ids, dtype=np.int64),
                "attention_mask": __import__("numpy").array(mask, dtype=np.int64)}
        if "token_type_ids" in in_names:
            feed["token_type_ids"] = __import__("numpy").zeros((1, len(enc.ids)), dtype=np.int64)
        h = sess.run(None, feed)[0][0]              # (seq, dim)
        m = np.array(mask)[0][:, None]
        v = (h * m).sum(0) / m.sum()                 # mean pool
        v = v / np.linalg.norm(v)                    # L2
        out.append(v.astype(np.float32))
    return np.array(out)

def main():
    corpus_groups = [g for g, _ in _TOOL_EMBED_CORPUS]
    corpus_texts = [t for _, t in _TOOL_EMBED_CORPUS]

    t0=time.perf_counter(); m_mini = load(MINILM); tl_mini=time.perf_counter()-t0
    mini_corpus = vecs(m_mini, corpus_texts)

    # E5-small: onnxruntime ile doğrudan (fastembed desteklemiyor)
    t1=time.perf_counter()
    e5_corpus = e5_embed(["passage: " + t for t in corpus_texts])
    print(f"yükleme: MiniLM={tl_mini:.1f}s | E5 onnx kurulum+corpus embed: {time.perf_counter()-t1:.1f}s")

    rows = []
    for msg, expected in CASES:
        qv_m = vecs(m_mini, [msg])[0]
        bm, sm_, mg_, g_ = score(qv_m, mini_corpus, corpus_groups)
        ok_m = (bm >= 0.50 and mg_ >= 0.05)

        qv_e = e5_embed(["query: " + msg])[0]
        be, se_, me_, ge_ = score(qv_e, e5_corpus, corpus_groups)
        ok_e = (be >= 0.50 and me_ >= 0.05)

        rows.append((msg, expected, bm, mg_, ok_m, be, me_, ok_e))

    hdr = f"{'mesaj':38s} {'bekl':9s} | {'M sim':>7s} {'marg':>6s} {'ok':>4s} | {'E5s sim':>8s} {'marg':>6s} {'ok':>4s}"
    print("\n" + hdr); print("-"*len(hdr))
    for msg, exp, bm, mg, okm, be, me, oke in rows:
        print(f"{msg[:36]:38s} {exp:9s} | {bm:7.3f} {mg:6.3f} {str(okm):>4s} | {be:8.3f} {me:6.3f} {str(oke):>4s}")

    import statistics
    mm=[r[3] for r in rows]; me=[r[6] for r in rows]
    thin_m=sum(1 for x in mm if x<0.10); thin_e=sum(1 for x in me if x<0.10)
    acc_m=sum(1 for r in rows if r[2]>=0.50 and r[4]); acc_e=sum(1 for r in rows if r[5]>=0.50 and r[7])
    print(f"\nORT MARGIN : MiniLM={statistics.mean(mm):.3f}  E5s={statistics.mean(me):.3f}")
    print(f"İNCE(<0.10): MiniLM={thin_m}/14  E5s={thin_e}/14")
    print(f"GÜVENLİ    : MiniLM={acc_m}/14  E5s={acc_e}/14")

if __name__ == "__main__":
    main()
