"""piSynapse — Corpus Feeder

Batch script that mines tool_audit_log for correction/confirmation signals
and feeds them into the intent-classification corpus as new examples.

Usage:
    python corpus_feeder.py [--dry-run] [--db PATH]

State tracking: corpus_data/state.json stores last processed audit_id so
each run only processes new rows.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "corpus_data"
STATE_FILE = DATA_DIR / "state.json"
ADDITIONS_FILE = DATA_DIR / "additions.jsonl"
EMBEDDINGS_FILE = DATA_DIR / "additions_embeddings.npy"
PENDING_REVIEW_FILE = DATA_DIR / "pending_review.json"
GENUINELY_AMBIGUOUS_FILE = DATA_DIR / "genuinely_ambiguous.json"

# ── logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("corpus_feeder")

# ── helpers ────────────────────────────────────────────────────────────────────
# Import config after ROOT is on sys.path so config.py can be found.
sys.path.insert(0, str(ROOT))
import config  # noqa: E402


def _db_path(args_db: str | None = None) -> str:
    return args_db or os.getenv("DB_PATH", config.DB_PATH)


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_audit_id": 0, "last_run": None}


def _save_state(state: dict):
    _ensure_data_dir()
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _append_jsonl(path: Path, record: dict):
    _ensure_data_dir()
    with open(path, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_jsonl(path: Path, records: list[dict]):
    """Atomically replace the JSONL file with the given records (temp + rename)."""
    _ensure_data_dir()
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.replace(str(tmp), str(path))


def _remove_addition_by_audit_id(audit_id):
    """Drop the addition record for ``audit_id`` from ADDITIONS_FILE.

    Used to roll back a jsonl append when its embedding could not be computed,
    keeping additions.jsonl and additions_embeddings.npy index-aligned.
    """
    rows = _load_jsonl(ADDITIONS_FILE)
    kept = [r for r in rows if r.get("audit_id") != audit_id]
    if len(kept) != len(rows):
        _write_jsonl(ADDITIONS_FILE, kept)


def _load_pending_review() -> list[dict]:
    return _load_jsonl(PENDING_REVIEW_FILE)


def _append_pending_review(record: dict):
    _append_jsonl(PENDING_REVIEW_FILE, record)


def _load_genuinely_ambiguous() -> list[dict]:
    return _load_jsonl(GENUINELY_AMBIGUOUS_FILE)


def _append_genuinely_ambiguous(record: dict):
    _append_jsonl(GENUINELY_AMBIGUOUS_FILE, record)


# ── DB helpers ─────────────────────────────────────────────────────────────────
import sqlite3  # noqa: E402


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_new_audits(conn: sqlite3.Connection, last_id: int) -> list[dict]:
    """Fetch audit rows with confirmed_at or expected_group newer than last_id."""
    rows = conn.execute(
        """
        SELECT a.id, a.tool_name, a.conversation_id, a.expected_group,
               a.expected_tool, a.confirmed_at, a.corrected_at
        FROM tool_audit_log a
        WHERE a.id > ?
          AND (a.confirmed_at IS NOT NULL OR a.expected_group IS NOT NULL)
        ORDER BY a.id ASC
        """,
        (last_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _resolve_message_text(conn: sqlite3.Connection, conversation_id: int | None) -> str | None:
    """Resolve the USER message that triggered a given audit row.

    `tool_audit_log.conversation_id` is the *assistant* message id (see
    `link_audits_to_message`); the corpus must NOT be fed the assistant reply
    (that is tool output, not a user intent). We therefore walk back to the
    preceding `user` message in the same session. Returns None when unresolved.
    """
    if conversation_id is None:
        return None
    row = conn.execute(
        "SELECT session_id FROM conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    if row is None or not row["session_id"]:
        return None
    session_id = row["session_id"]
    user_row = conn.execute(
        """SELECT content FROM conversations
           WHERE session_id = ? AND id < ? AND role = 'user'
           ORDER BY id DESC LIMIT 1""",
        (session_id, conversation_id),
    ).fetchone()
    if user_row is None:
        return None
    return user_row["content"]


# Assistant outputs (list dumps, greetings, tool-summary prose) are NOT valid
# intent examples even after user-message resolution; they indicate the resolved
# text was the reply itself or a degenerate short message. Multi-line list
# markers, assistant-style greetings, and a heavy prose ratio mark such rows.
_ASST_GREETINGS = ("merhaba", "elbette", "işte", "aşağıda", "tamam,", "tabii,",
                   "hazırlıyorum", "listeliyorum", "bulabilirsin", "gönderdim",
                   "oldu", "kaydedildi", "eklendi", "silindi", "hatırlatıcı kuruldu")


def _is_user_command_like(text: str) -> bool:
    """Heuristics to reject assistant-output / degenerate text as an intent example.

    Returns True when the text plausibly is a user command suitable as a corpus
    example. Conservative: when in doubt, returns False (the row is skipped to
    genuinely_ambiguous instead of poisoning the corpus).
    """
    t = text.strip().lower()
    if not t:
        return False
    if "\n" in t and len(t.splitlines()) > 1:
        return False  # multi-line output/response
    if len(t) > 200:
        return False  # long prose — almost certainly a reply
    # A single word that is not a clear verb-like command is too ambiguous.
    if len(t.split()) <= 1:
        return False
    # Assistant-style openers strongly suggest a reply, not a command.
    for g in _ASST_GREETINGS:
        if t.startswith(g):
            return False
    return True


# ── TOOL_TO_GROUP (mirrors tools/definitions.py) ──────────────────────────────
def _load_tool_to_group() -> dict[str, str]:
    from tools.definitions import TOOL_TO_GROUP
    return TOOL_TO_GROUP


def _load_corpus_groups() -> set[str]:
    """All group labels that exist in the hardcoded corpus."""
    from llm.intent import _TOOL_EMBED_CORPUS
    return {g for g, _ in _TOOL_EMBED_CORPUS if g is not None}


# ── conflict detection ────────────────────────────────────────────────────────
def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


async def _load_base_corpus_embeddings() -> tuple[list[str], np.ndarray | None]:
    """Load the base corpus texts and embed them. Returns (groups, matrix or None)."""
    from embedding import embed_batch_async
    from llm.intent import _TOOL_EMBED_CORPUS

    groups = [g for g, _ in _TOOL_EMBED_CORPUS]
    texts = [desc for _, desc in _TOOL_EMBED_CORPUS]
    try:
        vecs = await embed_batch_async(texts)
        matrix = np.array([np.frombuffer(v, dtype="float32") for v in vecs])
        return groups, matrix
    except Exception as e:
        log.warning(f"Could not embed base corpus: {e}")
        return groups, None


def _rebuild_matrix(records: list[dict]) -> np.ndarray | None:
    """Re-embed every record text in jsonl order → index-aligned matrix.

    additons_embeddings.npy stores vectors positionally; rebuilding the whole
    matrix from the JSONL (the source of truth) guarantees rows and records
    never slip out of alignment after a partial write or a crash.
    """
    from embedding import embed as embed_one

    if not records:
        return None
    vecs = []
    for rec in records:
        try:
            v = np.frombuffer(embed_one(rec["text"]), dtype="float32").reshape(1, -1)
        except Exception as exc:  # noqa: BLE001
            log.error("embed failed during rebuild for record=%r: %s", rec.get("audit_id"), exc)
            return None
        vecs.append(v)
    return np.vstack(vecs)


def _load_addition_embeddings() -> tuple[list[dict], np.ndarray | None]:
    """Load persisted addition records and their embeddings, self-healing drift.

    If the persisted vector count does not match the JSONL record count (a crash
    or a failed embed may have slipped jsonl ahead of npy), the matrix is rebuilt
    index-aligned from the JSONL and atomically persisted before being returned.
    """
    additions = _load_jsonl(ADDITIONS_FILE)
    if not additions:
        if EMBEDDINGS_FILE.exists():
            EMBEDDINGS_FILE.unlink(missing_ok=True)
        return additions, None
    if not EMBEDDINGS_FILE.exists():
        matrix = _rebuild_matrix(additions)
        if matrix is not None:
            _save_addition_embeddings(matrix)
        return additions, matrix
    matrix = np.load(str(EMBEDDINGS_FILE))
    if matrix.ndim == 1:
        matrix = matrix.reshape(-1, 1)
    if len(matrix) != len(additions):
        log.warning(
            "jsonl/npy misalignment: %d records vs %d vectors — rebuilding index-aligned",
            len(additions), len(matrix),
        )
        matrix = _rebuild_matrix(additions)
        if matrix is not None:
            _save_addition_embeddings(matrix)
    return additions, matrix if (matrix is not None and len(matrix) > 0) else None


def _save_addition_embeddings(matrix: np.ndarray):
    _ensure_data_dir()
    tmp = EMBEDDINGS_FILE.with_name(EMBEDDINGS_FILE.name + ".tmp.npy")
    np.save(str(tmp), matrix)
    os.replace(str(tmp), str(EMBEDDINGS_FILE))


def _check_conflict(
    text: str,
    proposed_group: str,
    base_groups: list[str],
    base_matrix: np.ndarray | None,
    addition_records: list[dict],
    addition_matrix: np.ndarray | None,
    conflict_threshold: float | None = None,
) -> dict | None:
    """Check if text conflicts with existing corpus or additions.

    A "conflict" is flagged when the text's nearest example of a DIFFERENT
    group scores at or above the (configurable) cosine threshold — i.e. when
    the existing corpus routing would disagree with the user's proposed group.
    The threshold defaults to config.CONFLICT_COSINE (calibrated, see config.py)
    so this flow fires on real data instead of sitting dead at an unreachable
    0.85. Returns a conflict dict or None.
    """
    from embedding import embed as embed_one

    if conflict_threshold is None:
        conflict_threshold = float(getattr(config, "CONFLICT_COSINE", 0.50))

    vec = np.frombuffer(embed_one(text), dtype="float32")

    # Check against base corpus
    if base_matrix is not None and len(base_matrix) > 0:
        sims = np.array([_cosine(vec, row) for row in base_matrix])
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        best_group = base_groups[best_idx]
        if best_group != proposed_group and best_sim >= conflict_threshold:
            return {
                "text": text,
                "proposed_group": proposed_group,
                "conflicts_with_group": best_group,
                "similarity": round(best_sim, 4),
                "source": "base_corpus",
            }

    # Check against existing additions
    if addition_matrix is not None and len(addition_matrix) > 0:
        sims = np.array([_cosine(vec, row) for row in addition_matrix])
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        best_group = addition_records[best_idx].get("group")
        if best_group != proposed_group and best_sim >= conflict_threshold:
            return {
                "text": text,
                "proposed_group": proposed_group,
                "conflicts_with_group": best_group,
                "similarity": round(best_sim, 4),
                "source": "additions",
                "conflict_audit_id": addition_records[best_idx].get("audit_id"),
            }

    return None


# ── duplicate check ────────────────────────────────────────────────────────────
def _is_duplicate(
    text: str,
    base_groups: list[str],
    base_matrix: np.ndarray | None,
    addition_records: list[dict],
    addition_matrix: np.ndarray | None,
    dup_threshold: float = 0.98,
) -> bool:
    """Check if text already exists in corpus or additions (near-exact match)."""
    from embedding import embed as embed_one

    vec = np.frombuffer(embed_one(text), dtype="float32")

    if base_matrix is not None and len(base_matrix) > 0:
        sims = np.array([_cosine(vec, row) for row in base_matrix])
        if float(np.max(sims)) >= dup_threshold:
            return True

    if addition_matrix is not None and len(addition_matrix) > 0:
        sims = np.array([_cosine(vec, row) for row in addition_matrix])
        if float(np.max(sims)) >= dup_threshold:
            return True

    return False


# ── LLM auto-resolution ────────────────────────────────────────────────────────
async def _llm_resolve(text: str, group_a: str, group_b: str) -> str | None:
    """Ask the LLM which group fits the text better. Returns chosen group or None."""
    prompt = (
        f'Bu cümle daha çok hangi konuya ait?\n'
        f'  A) {group_a}\n'
        f'  B) {group_b}\n\n'
        f'Cümle: "{text}"\n\n'
        f'Sadece tek kelime yaz: {group_a} veya {group_b}'
    )
    try:
        client = httpx.AsyncClient(timeout=30)
        backend = getattr(config, "LLM_BACKEND", "litert").strip().lower()
        model = getattr(config, "LLM_MODEL", "gemma4-e2b")

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Sen bir sınıflandırma asistanısın. "
                 "Verilen cümleyi iki kategoriden birine sınıflandır. "
                 "SADECE kategori adını yaz, başka bir şey yazma."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "max_tokens": 20,
            "max_completion_tokens": 20,
        }

        if backend == "litert":
            url = f"{getattr(config, 'LITERT_BASE_URL', 'http://localhost:9379')}/v1/chat/completions"
        else:
            payload["think"] = False
            payload["options"] = {"temperature": 0, "num_predict": 20, "num_ctx": 512}
            payload["keep_alive"] = getattr(config, "LLM_KEEP_ALIVE", "4h")
            url = f"{getattr(config, 'OLLAMA_BASE_URL', 'http://localhost:11434')}/api/chat"

        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        rj = resp.json()

        if backend == "litert":
            answer = rj["choices"][0]["message"]["content"].strip().lower()
        else:
            answer = rj["message"]["content"].strip().lower()

        await client.aclose()

        # Normalize: the LLM might output the group name or a nearby string
        if group_a.lower() in answer and group_b.lower() not in answer:
            return group_a
        if group_b.lower() in answer and group_a.lower() not in answer:
            return group_b
        return None  # ambiguous / unrecognizable

    except Exception as e:
        log.warning(f"LLM resolution failed: {e}")
        return None


# ── main logic ─────────────────────────────────────────────────────────────────
async def _process_audit_row(
    row: dict,
    tool_to_group: dict[str, str],
    conn: sqlite3.Connection,
    base_groups: list[str],
    base_matrix: np.ndarray | None,
    existing_additions: list[dict],
    addition_matrix: np.ndarray | None,
    dry_run: bool = False,
) -> dict:
    """Process a single audit row. Returns a summary dict."""
    audit_id = row["id"]
    tool_name = row["tool_name"]
    conversation_id = row["conversation_id"]
    confirmed = row["confirmed_at"] is not None
    corrected = row["expected_group"] is not None
    expected_group = row.get("expected_group")

    message_text = _resolve_message_text(conn, conversation_id)
    if not message_text:
        return {"id": audit_id, "status": "skip_no_text"}

    # Determine the proposed group
    if corrected and expected_group:
        proposed_group = expected_group
        signal = "negative"
    elif confirmed:
        proposed_group = tool_to_group.get(tool_name)
        if not proposed_group:
            return {"id": audit_id, "status": "skip_no_group_mapping"}
        signal = "positive"
    else:
        return {"id": audit_id, "status": "skip_no_signal"}

    # Normalize text: strip whitespace, lowercase for dedup
    text = message_text.strip()
    if not text:
        return {"id": audit_id, "status": "skip_empty_text"}

    # Reject assistant-output / degenerate text: feeding the model's own reply
    # or a context-only fragment as an intent example would poison routing.
    if not _is_user_command_like(text):
        record = {
            "text": text,
            "proposed_group": proposed_group,
            "audit_id": audit_id,
            "reason": "not_user_command",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if not dry_run:
            _append_genuinely_ambiguous(record)
        return {"id": audit_id, "status": "genuinely_ambiguous_not_command",
                "group": proposed_group, "text": text}

    # Check exact duplicate
    if _is_duplicate(text, base_groups, base_matrix, existing_additions, addition_matrix):
        return {"id": audit_id, "status": "skip_duplicate", "group": proposed_group}

    # Check conflict
    conflict = _check_conflict(
        text, proposed_group, base_groups, base_matrix,
        existing_additions, addition_matrix,
    )

    if conflict:
        # For corrections: the original tool_name maps to a group — that's the "wrong" group
        original_group = tool_to_group.get(tool_name) if corrected else None

        # LLM auto-resolution: ask which group is correct
        if original_group and original_group != proposed_group:
            llm_choice = await _llm_resolve(text, proposed_group, original_group)
        elif conflict["conflicts_with_group"] != proposed_group:
            llm_choice = await _llm_resolve(text, proposed_group, conflict["conflicts_with_group"])
        else:
            llm_choice = None

        if llm_choice == proposed_group:
            # LLM agrees with user — auto-add, resolve the conflict
            record = {
                "text": text,
                "group": proposed_group,
                "source": signal,
                "audit_id": audit_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resolution": "llm_confirmed",
                "original_conflict": conflict,
            }
            if not dry_run:
                _append_jsonl(ADDITIONS_FILE, record)
            return {"id": audit_id, "status": "added_llm_resolved", "group": proposed_group,
                    "text": text, "conflict": conflict, "llm_choice": llm_choice}
        else:
            # LLM disagrees or ambiguous → genuinely ambiguous
            record = {
                "text": text,
                "proposed_group": proposed_group,
                "conflicts_with": conflict,
                "audit_id": audit_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "llm_choice": llm_choice,
            }
            if not dry_run:
                _append_genuinely_ambiguous(record)
            return {"id": audit_id, "status": "genuinely_ambiguous", "group": proposed_group,
                    "conflict": conflict, "llm_choice": llm_choice}

    # No conflict → add directly
    record = {
        "text": text,
        "group": proposed_group,
        "source": signal,
        "audit_id": audit_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if not dry_run:
        _append_jsonl(ADDITIONS_FILE, record)
    return {"id": audit_id, "status": "added", "group": proposed_group, "text": text}


async def run(db_path: str | None = None, dry_run: bool = False) -> dict:
    """Main entry point. Returns summary dict."""
    _ensure_data_dir()
    state = _load_state()
    last_id = state.get("last_audit_id", 0)

    resolved_db = _db_path(db_path)
    conn = _connect(resolved_db)

    rows = _fetch_new_audits(conn, last_id)
    if not rows:
        log.info("No new audit rows to process.")
        conn.close()
        return {"processed": 0, "added": 0, "conflicts": 0, "ambiguous": 0}

    log.info(f"Found {len(rows)} new audit rows (id > {last_id})")

    tool_to_group = _load_tool_to_group()
    base_groups, base_matrix = await _load_base_corpus_embeddings()
    existing_additions, addition_matrix = _load_addition_embeddings()

    summary = {"processed": 0, "added": 0, "skipped": 0, "conflicts": 0, "ambiguous": 0,
               "details": []}

    for row in rows:
        result = await _process_audit_row(
            row, tool_to_group, conn,
            base_groups, base_matrix,
            existing_additions, addition_matrix,
            dry_run=dry_run,
        )
        summary["processed"] += 1

        status = result["status"]
        if status in ("added", "added_llm_resolved"):
            text = result.get("text") or ""
            group = result.get("group") or ""
            if dry_run:
                summary["added"] += 1
            else:
                # Guard the embed: _process_audit_row already appended the jsonl
                # record; if its vector cannot be computed we roll the record back
                # so jsonl and npy never diverge for this run.
                try:
                    from embedding import embed as embed_one
                    vec = np.frombuffer(embed_one(text), dtype="float32")
                except Exception as exc:  # noqa: BLE001
                    log.error("embed failed for audit=%s [%s]: %s — rolling back jsonl",
                              result.get("id"), status, exc)
                    _remove_addition_by_audit_id(result.get("id"))
                    summary["skipped"] += 1
                    result["status"] = "skip_embed_error"
                else:
                    summary["added"] += 1
                    existing_additions.append({"text": text, "group": group})
                    if addition_matrix is None:
                        addition_matrix = vec.reshape(1, -1)
                    else:
                        addition_matrix = np.vstack([addition_matrix, vec.reshape(1, -1)])
        elif status == "genuinely_ambiguous":
            summary["ambiguous"] += 1
        elif status == "genuinely_ambiguous_not_command":
            summary["ambiguous"] += 1
        elif status == "skip_duplicate":
            summary["skipped"] += 1
            summary["conflicts"] += 1
        else:
            summary["skipped"] += 1

        summary["details"].append(result)

    # Persist embeddings
    if not dry_run and addition_matrix is not None:
        _save_addition_embeddings(addition_matrix)

    # Update state
    max_id = max(r["id"] for r in rows)
    if not dry_run:
        _save_state({
            "last_audit_id": max_id,
            "last_run": datetime.now(timezone.utc).isoformat(),
        })

    conn.close()

    log.info(
        f"Done: {summary['processed']} processed, {summary['added']} added, "
        f"{summary['conflicts']} conflicts, {summary['ambiguous']} genuinely ambiguous, "
        f"{summary['skipped']} skipped"
    )
    return summary


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    import asyncio

    parser = argparse.ArgumentParser(description="piSynapse corpus feeder")
    parser.add_argument("--dry-run", action="store_true",
                        help="Process but don't write any files")
    parser.add_argument("--db", type=str, default=None,
                        help="Path to assistant.db (default: config.DB_PATH)")
    parser.add_argument("--reset", action="store_true",
                        help="Reset state to reprocess all rows")
    args = parser.parse_args()

    if args.reset:
        _ensure_data_dir()
        _save_state({"last_audit_id": 0, "last_run": None})
        log.info("State reset. Next run will reprocess all rows.")
        return

    summary = asyncio.run(run(db_path=args.db, dry_run=args.dry_run))

    # Pretty-print summary
    print("\n" + "=" * 60)
    print("CORPUS FEEDER SUMMARY")
    print("=" * 60)
    print(f"  Processed:          {summary['processed']}")
    print(f"  Added to corpus:    {summary['added']}")
    print(f"  Conflicts resolved: {summary['conflicts']}")
    print(f"  Genuinely ambiguous:{summary['ambiguous']}")
    print(f"  Skipped:            {summary['skipped']}")
    if summary.get("details"):
        print("\n  Details:")
        for d in summary["details"]:
            status = d.get("status", "unknown")
            group = d.get("group", "?")
            aid = d.get("id", "?")
            if status == "added":
                print(f"    #{aid} → +{group} (positive/negative)")
            elif status == "added_llm_resolved":
                print(f"    #{aid} → +{group} (conflict resolved by LLM)")
            elif status == "genuinely_ambiguous":
                print(f"    #{aid} → AMBIGUOUS (proposed {group}, LLM disagreed)")
            elif status == "genuinely_ambiguous_not_command":
                print(f"    #{aid} → AMBIGUOUS (not a user command: {group!r})")
            elif status.startswith("skip"):
                print(f"    #{aid} → {status}")
    print("=" * 60)


if __name__ == "__main__":
    main()
