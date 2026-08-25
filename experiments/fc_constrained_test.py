#!/usr/bin/env python3
"""ROADMAP #1/#2 experiment: constrained decoding + automatic schema FC.

Runs gemma4-E2B twice (unconstrained vs LL_GUIDANCE-constrained) over the
same prompts using REAL Python functions as tools (automatic schema path).
Records wall time per turn and whether create_task executed with VALID args.

Run:  sudo systemctl stop pisynapse   # free RAM first if needed
      ./venv/bin/python experiments/fc_constrained_test.py [model_path]
"""
import json
import sys
import time

sys.path.insert(0, "/home/salih/.local/share/uv/tools/litert-lm/lib/python3.11/site-packages")
from litert_lm import Backend, ConstrainedDecodingConfig, Engine, LiteRtLmConstraintProviderType

CFG = json.load(open("/home/salih/piSynapse/litert_serve/config.json"))
if len(sys.argv) > 1:
    CFG["model_path"] = sys.argv[1]

CALLS: list = []

def create_task(summary: str, due: str = "", notes: str = "") -> str:
    """Create a new task for the user.

    Args:
        summary: what the task is (short title).
        due: when it is due, ISO 8601 (e.g. 2026-08-25T14:00). Empty if unknown.
        notes: extra details.
    """
    CALLS.append({"tool": "create_task", "summary": summary,
                  "due": due, "notes_len": len(notes or "")})
    return f"OK: task '{summary}' created."

def get_datetime() -> str:
    """Get the current date and time."""
    import datetime
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M (%A)")

TOOLS = [create_task, get_datetime]
SYSTEM = ("You are piSynapse, a helpful assistant. Always answer in the same "
          "language the user writes in.")

def build_engine():
    return Engine(
        model_path=CFG["model_path"],
        max_num_tokens=int(CFG["max_num_tokens"]),
        enable_speculative_decoding=bool(CFG["speculative_decoding"]),
        use_ringbuffers_local_attention=bool(CFG["use_ringbuffers_local_attention"]),
        enable_ynnpack=bool(CFG["enable_ynnpack"]),
        vision_backend=Backend.CPU(), audio_backend=Backend.CPU(),
    )

def run_variant(name: str, constrained: bool, prompts, engine):
    print(f"\n===== {name} =====", flush=True)
    cdc = None
    if constrained:
        cdc = ConstrainedDecodingConfig(
            enable=True,
            provider=LiteRtLmConstraintProviderType.LL_GUIDANCE,
        )
    conv = engine.create_conversation(
        system_message=SYSTEM,
        tools=TOOLS,
        automatic_tool_calling=True,
        constrained_decoding_config=cdc,
        max_output_tokens=512,
    )
    results = []
    for label, prompt in prompts:
        CALLS.clear()
        t0 = time.perf_counter()
        resp = conv.send_message(prompt, max_output_tokens=400)
        dt = time.perf_counter() - t0
        txt = ""
        try:
            txt = str(resp.get("text", ""))[:120]
        except Exception:
            txt = str(resp)[:120]
        ok = any(c["tool"] == "create_task" and c["summary"] for c in CALLS)
        results.append((label, dt, list(CALLS), ok))
        print(f"  [{label}] {dt:6.2f}s calls={list(CALLS)}", flush=True)
        print(f"           text: {txt!r}", flush=True)
    conv.close()
    return results

PROMPTS = [
    ("TR-clean",  "Yarın saat 14:00 için 'toplantı' adında bir görev oluştur."),
    ("TR-detail", "Alışveriş listesi görevi oluştur, notlara da şunları yaz: süt, ekmek, çay"),
]

def main():
    variants = [("UNCONSTRAINED", False), ("CONSTRAINED", True)]
    results = {n: [] for n, _ in variants}
    engine = build_engine()
    for rnd in range(2):
        order = variants if rnd % 2 == 0 else variants[::-1]   # sıra yanlılığını kır
        for name, constrained in order:
            res = run_variant(name, constrained, PROMPTS, engine)
            results[name] += [(lab, d, ok) for lab, d, c, ok in res]
    print("\n===== ÖZET (2 tur ortalaması) =====")
    for name, res in results.items():
        for label in ("TR-clean", "TR-detail"):
            ds = [d for lab, d, ok in res if lab == label]
            oks = [ok for lab, d, ok in res if lab == label]
            avg = sum(ds)/len(ds)
            print(f"{name:12s} {label:9s} avg={avg:6.2f}s  valid={all(oks)} ({len(ds)} ölçüm)")
engine = None
if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
