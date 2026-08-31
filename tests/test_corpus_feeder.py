"""Tests for corpus_feeder: positive/negative additions, conflict detection,
embedding-only-new, and LLM auto-resolution.
"""

import asyncio
import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock

import numpy as np
import pytest

# ── fixtures ───────────────────────────────────────────────────────────────────

def _seed_audit_db(conn: sqlite3.Connection):
    """Set up minimal tables matching the real schema."""
    conn.execute("""
        CREATE TABLE tool_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL, params TEXT, success INTEGER NOT NULL,
            duration_ms REAL, error TEXT, is_summary INTEGER NOT NULL DEFAULT 0,
            day TEXT, total_calls INTEGER, success_count INTEGER,
            error_count INTEGER, tool_breakdown TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expected_tool TEXT, corrected_at DATETIME,
            expected_group TEXT, verification_status TEXT,
            confirmed_at DATETIME, conversation_id INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL, role TEXT NOT NULL,
            content TEXT, images TEXT, reasoning TEXT,
            embedding BLOB, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


@pytest.fixture
def audit_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    _seed_audit_db(conn)
    conn.close()
    return db_path


@pytest.fixture
def corpus_data_dir(tmp_path, monkeypatch):
    """Redirect corpus_feeder's DATA_DIR to a temp directory."""
    import corpus_feeder as cf
    monkeypatch.setattr(cf, "DATA_DIR", tmp_path / "corpus_data")
    monkeypatch.setattr(cf, "STATE_FILE", tmp_path / "corpus_data" / "state.json")
    monkeypatch.setattr(cf, "ADDITIONS_FILE", tmp_path / "corpus_data" / "additions.jsonl")
    monkeypatch.setattr(cf, "EMBEDDINGS_FILE", tmp_path / "corpus_data" / "additions_embeddings.npy")
    monkeypatch.setattr(cf, "PENDING_REVIEW_FILE", tmp_path / "corpus_data" / "pending_review.json")
    monkeypatch.setattr(cf, "GENUINELY_AMBIGUOUS_FILE", tmp_path / "corpus_data" / "genuinely_ambiguous.json")
    (tmp_path / "corpus_data").mkdir(exist_ok=True)
    return tmp_path / "corpus_data"


def _fake_embed(text: str) -> bytes:
    """Deterministic fake embedding based on text hash."""
    rng = np.random.RandomState(hash(text) % (2**31))
    vec = rng.randn(384).astype("float32")
    vec /= np.linalg.norm(vec) + 1e-9
    return vec.tobytes()


def _fake_embed_batch(texts: list[str]) -> list[bytes]:
    return [_fake_embed(t) for t in texts]


async def _fake_base_corpus(groups=("weather",), text="weather"):
    return (list(groups), np.array([_fake_embed(text)]))


# ── helpers ────────────────────────────────────────────────────────────────────
import corpus_feeder as cf


def _seed_rows(conn_str: str, rows: list[dict]):
    conn = sqlite3.connect(conn_str)
    for r in rows:
        conn.execute(
            """INSERT INTO tool_audit_log
               (tool_name, conversation_id, confirmed_at, corrected_at,
                expected_group, expected_tool, success)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (r["tool_name"], r.get("conversation_id"),
             r.get("confirmed_at"), r.get("corrected_at"),
             r.get("expected_group"), r.get("expected_tool")),
        )
    conn.commit()
    conn.close()


def _seed_conversation(conn_str: str, cid: int, text: str):
    conn = sqlite3.connect(conn_str)
    conn.execute(
        "INSERT INTO conversations (id, session_id, role, content) VALUES (?, 'test', 'user', ?)",
        (cid, text),
    )
    conn.commit()
    conn.close()


# ── tests ──────────────────────────────────────────────────────────────────────

class TestCorpusFeederPositive:
    """Positive: confirmed_at rows → add to corpus."""

    def test_positive_addition(self, audit_db, corpus_data_dir, monkeypatch):
        _seed_conversation(audit_db, 1, "hava durumu nasıl")
        _seed_rows(audit_db, [{"tool_name": "get_weather", "conversation_id": 1,
                               "confirmed_at": "2026-08-31T12:00:00"}])

        monkeypatch.setattr(cf, "_load_base_corpus_embeddings",
                            _fake_base_corpus)
        monkeypatch.setattr(cf, "_load_addition_embeddings", lambda: ([], None))
        monkeypatch.setattr(cf, "_is_duplicate", lambda *a, **kw: False)
        monkeypatch.setattr(cf, "_check_conflict", lambda *a, **kw: None)

        # Patch TOOL_TO_GROUP
        import tools.definitions as td
        monkeypatch.setattr(td, "TOOL_TO_GROUP", {"get_weather": "weather"})

        # Patch embed_one inside _process_audit_row via embedding module
        import embedding as emb
        monkeypatch.setattr(emb, "embed", _fake_embed)

        summary = asyncio.run(cf.run(db_path=audit_db))

        assert summary["added"] == 1
        assert summary["processed"] == 1

        additions = cf._load_jsonl(cf.ADDITIONS_FILE)
        assert len(additions) == 1
        assert additions[0]["group"] == "weather"
        assert additions[0]["source"] == "positive"
        assert additions[0]["audit_id"] == 1


class TestCorpusFeederNegative:
    """Negative: expected_group rows → add to expected_group corpus."""

    def test_negative_addition(self, audit_db, corpus_data_dir, monkeypatch):
        _seed_conversation(audit_db, 2, "notlarımı göster")
        _seed_rows(audit_db, [{"tool_name": "get_weather", "conversation_id": 2,
                               "corrected_at": "2026-08-31T12:00:00",
                               "expected_group": "notes",
                               "expected_tool": "list_notes"}])

        monkeypatch.setattr(cf, "_load_base_corpus_embeddings",
                            _fake_base_corpus)
        monkeypatch.setattr(cf, "_load_addition_embeddings", lambda: ([], None))
        monkeypatch.setattr(cf, "_is_duplicate", lambda *a, **kw: False)
        monkeypatch.setattr(cf, "_check_conflict", lambda *a, **kw: None)
        import tools.definitions as td
        monkeypatch.setattr(td, "TOOL_TO_GROUP", {"get_weather": "weather"})
        import embedding as emb
        monkeypatch.setattr(emb, "embed", _fake_embed)

        summary = asyncio.run(cf.run(db_path=audit_db))

        assert summary["added"] == 1
        additions = cf._load_jsonl(cf.ADDITIONS_FILE)
        assert additions[0]["group"] == "notes"
        assert additions[0]["source"] == "negative"


class TestCorpusFeederConflict:
    """Conflict: message is similar to wrong-group corpus → flagged."""

    def test_conflict_detected_and_llm_resolves(self, audit_db, corpus_data_dir, monkeypatch):
        _seed_conversation(audit_db, 3, "yarınki etkinliği sil")
        _seed_rows(audit_db, [{"tool_name": "create_task", "conversation_id": 3,
                               "corrected_at": "2026-08-31T12:00:00",
                               "expected_group": "calendar",
                               "expected_tool": "delete_calendar_event"}])

        weather_vec = np.frombuffer(_fake_embed("weather text"), dtype="float32")

        async def _fake_base_weather():
            return (["weather"], weather_vec.reshape(1, -1))

        monkeypatch.setattr(cf, "_load_base_corpus_embeddings", _fake_base_weather)
        monkeypatch.setattr(cf, "_load_addition_embeddings", lambda: ([], None))

        # _check_conflict: simulate high similarity against wrong group
        def fake_conflict(text, proposed, bgroups, bmat, addrecs, addmat, **kw):
            if proposed == "calendar":
                return {"text": text, "proposed_group": proposed,
                        "conflicts_with_group": "weather", "similarity": 0.92,
                        "source": "base_corpus"}
            return None
        monkeypatch.setattr(cf, "_check_conflict", fake_conflict)
        monkeypatch.setattr(cf, "_is_duplicate", lambda *a, **kw: False)

        import tools.definitions as td
        monkeypatch.setattr(td, "TOOL_TO_GROUP", {"create_task": "tasks"})
        import embedding as emb
        monkeypatch.setattr(emb, "embed", _fake_embed)

        # Mock LLM: agrees with user (calendar)
        async def fake_llm(text, a, b):
            return "calendar"
        monkeypatch.setattr(cf, "_llm_resolve", fake_llm)

        summary = asyncio.run(cf.run(db_path=audit_db))

        assert summary["added"] == 1
        details = summary["details"][0]
        assert details["status"] == "added_llm_resolved"

    def test_conflict_llm_disagrees_genuinely_ambiguous(self, audit_db, corpus_data_dir, monkeypatch):
        _seed_conversation(audit_db, 4, "hava durumunu değiştir")
        _seed_rows(audit_db, [{"tool_name": "create_task", "conversation_id": 4,
                               "corrected_at": "2026-08-31T12:00:00",
                               "expected_group": "calendar",
                               "expected_tool": "update_calendar_event"}])

        monkeypatch.setattr(cf, "_load_base_corpus_embeddings",
                            _fake_base_corpus)
        monkeypatch.setattr(cf, "_load_addition_embeddings", lambda: ([], None))

        def fake_conflict(text, proposed, bgroups, bmat, addrecs, addmat, **kw):
            return {"text": text, "proposed_group": proposed,
                    "conflicts_with_group": "weather", "similarity": 0.92,
                    "source": "base_corpus"}
        monkeypatch.setattr(cf, "_check_conflict", fake_conflict)
        monkeypatch.setattr(cf, "_is_duplicate", lambda *a, **kw: False)

        import tools.definitions as td
        monkeypatch.setattr(td, "TOOL_TO_GROUP", {"create_task": "tasks"})
        import embedding as emb
        monkeypatch.setattr(emb, "embed", _fake_embed)

        # Mock LLM: disagrees → ambiguous
        async def fake_llm(text, a, b):
            return "weather"
        monkeypatch.setattr(cf, "_llm_resolve", fake_llm)

        summary = asyncio.run(cf.run(db_path=audit_db))

        assert summary["ambiguous"] == 1
        details = summary["details"][0]
        assert details["status"] == "genuinely_ambiguous"

        # Should be in genuinely_ambiguous.json
        ga = cf._load_genuinely_ambiguous()
        assert len(ga) == 1
        assert ga[0]["proposed_group"] == "calendar"


class TestCorpusFeederEmbeddingOnlyNew:
    """Verify that only new additions are embedded, not the entire corpus."""

    def test_embeddings_only_for_new(self, audit_db, corpus_data_dir, monkeypatch):
        _seed_conversation(audit_db, 5, "bugün hava nasıl")
        _seed_rows(audit_db, [{"tool_name": "get_weather", "conversation_id": 5,
                               "confirmed_at": "2026-08-31T12:00:00"}])

        monkeypatch.setattr(cf, "_load_base_corpus_embeddings",
                            _fake_base_corpus)
        monkeypatch.setattr(cf, "_load_addition_embeddings", lambda: ([], None))
        monkeypatch.setattr(cf, "_is_duplicate", lambda *a, **kw: False)
        monkeypatch.setattr(cf, "_check_conflict", lambda *a, **kw: None)

        import tools.definitions as td
        monkeypatch.setattr(td, "TOOL_TO_GROUP", {"get_weather": "weather"})

        # Track embed calls
        embed_calls = []
        import embedding as emb
        def track_embed(text):
            embed_calls.append(text)
            return _fake_embed(text)
        monkeypatch.setattr(emb, "embed", track_embed)
        monkeypatch.setattr(emb, "embed_batch_async", AsyncMock(side_effect=lambda t: _fake_embed_batch(t)))

        summary = asyncio.run(cf.run(db_path=audit_db))

        assert summary["added"] == 1
        # embed() should be called exactly once for the new addition's conflict check
        assert "bugün hava nasıl" in embed_calls

        # Verify .npy was written with 1 vector
        assert cf.EMBEDDINGS_FILE.exists()
        mat = np.load(str(cf.EMBEDDINGS_FILE))
        assert mat.shape == (1, 384)


class TestCorpusFeederDuplicate:
    """Duplicate: exact match in existing corpus → skip."""

    def test_duplicate_skipped(self, audit_db, corpus_data_dir, monkeypatch):
        _seed_conversation(audit_db, 6, "what is the weather")
        _seed_rows(audit_db, [{"tool_name": "get_weather", "conversation_id": 6,
                               "confirmed_at": "2026-08-31T12:00:00"}])

        def fake_is_dup(text, bgroups, bmat, addrecs, addmat, dup_threshold=0.98):
            return True  # pretend it's a duplicate
        monkeypatch.setattr(cf, "_is_duplicate", fake_is_dup)
        monkeypatch.setattr(cf, "_load_base_corpus_embeddings",
                            _fake_base_corpus)
        monkeypatch.setattr(cf, "_load_addition_embeddings", lambda: ([], None))

        import tools.definitions as td
        monkeypatch.setattr(td, "TOOL_TO_GROUP", {"get_weather": "weather"})
        import embedding as emb
        monkeypatch.setattr(emb, "embed", _fake_embed)

        summary = asyncio.run(cf.run(db_path=audit_db))

        assert summary["added"] == 0
        assert summary["skipped"] == 1
        assert not cf.ADDITIONS_FILE.exists() or cf.ADDITIONS_FILE.read_text().strip() == ""


class TestCorpusFeederStateTracking:
    """State: only processes rows newer than last_audit_id."""

    def test_state_prevents_reprocessing(self, audit_db, corpus_data_dir, monkeypatch):
        _seed_conversation(audit_db, 7, "saat kaç")
        _seed_rows(audit_db, [{"tool_name": "get_datetime", "conversation_id": 7,
                               "confirmed_at": "2026-08-31T12:00:00"}])

        # First run
        async def _fake_empty_base():
            return ([], None)
        monkeypatch.setattr(cf, "_load_base_corpus_embeddings", _fake_empty_base)
        monkeypatch.setattr(cf, "_load_addition_embeddings", lambda: ([], None))
        monkeypatch.setattr(cf, "_is_duplicate", lambda *a, **kw: False)
        monkeypatch.setattr(cf, "_check_conflict", lambda *a, **kw: None)

        import tools.definitions as td
        monkeypatch.setattr(td, "TOOL_TO_GROUP", {"get_datetime": None})
        import embedding as emb
        monkeypatch.setattr(emb, "embed", _fake_embed)

        # Since get_datetime maps to None, it will skip
        summary1 = asyncio.run(cf.run(db_path=audit_db))
        assert summary1["processed"] == 1

        # State is updated even if skipped
        state = cf._load_state()
        assert state["last_audit_id"] == 1

        # Second run: no new rows
        summary2 = asyncio.run(cf.run(db_path=audit_db))
        assert summary2["processed"] == 0


class TestIntelAdditionsLoading:
    """Verify llm.intent loads corpus additions into the embedding cache."""

    def test_additional_corpus_parses_additions(self, monkeypatch):
        import llm.intent as li
        repo_corpus = Path(__file__).resolve().parent.parent / "corpus_data"
        additions_path = repo_corpus / "additions.jsonl"
        additions_path.write_text(json.dumps(
            {"text": "yarınki etkinliği sil", "group": "calendar"}, ensure_ascii=False) + "\n")
        try:
            parsed = li._additional_corpus()
            assert ("calendar", "yarınki etkinliği sil") in parsed
        finally:
            additions_path.unlink(missing_ok=True)

    def test_base_corpus_empty_additions(self, monkeypatch):
        import llm.intent as li

        monkeypatch.setattr(Path, "exists", lambda self: False)
        assert li._additional_corpus() == []
