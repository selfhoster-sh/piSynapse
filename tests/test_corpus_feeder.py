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
    """Insert a user message (id cid-1) followed by an assistant message (id cid).

    Mirrors the real schema where tool_audit_log.conversation_id points to the
    ASSISTANT message; the feeder walks back to the preceding user message, so
    cid must be ≥ 2 and the user text sits at cid-1.
    """
    conn = sqlite3.connect(conn_str)
    conn.execute(
        "INSERT INTO conversations (id, session_id, role, content) VALUES (?, 'test', 'user', ?)",
        (cid - 1, text),
    )
    conn.execute(
        "INSERT INTO conversations (id, session_id, role, content) VALUES (?, 'test', 'assistant', ?)",
        (cid, "Merhaba! İşte sonuçlar: 1. deneme 2. deneme 3. deneme"),
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

    def test_additional_corpus_parses_additions(self, tmp_path, monkeypatch):
        import llm.intent as li
        ap = tmp_path / "corpus_data" / "additions.jsonl"
        ap.parent.mkdir(parents=True)
        ap.write_text(json.dumps(
            {"text": "yarınki etkinliği sil", "group": "calendar"}, ensure_ascii=False) + "\n")
        monkeypatch.setattr(li, "_ADDITIONS_PATH", ap)
        parsed = li._additional_corpus()
        assert ("calendar", "yarınki etkinliği sil") in parsed

    def test_base_corpus_empty_additions(self, monkeypatch):
        import llm.intent as li

        monkeypatch.setattr(Path, "exists", lambda self: False)
        assert li._additional_corpus() == []


class TestBug1UserMessageResolution:
    """C-1: corpus must be fed the USER command, not the assistant reply."""

    def _run_single(self, audit_db, corpus_data_dir, monkeypatch,
                    user_text, tool="get_weather", group="weather",
                    conversation_id=5, assistant_reply=None):
        # assistant message at `conversation_id`, user text at conversation_id-1
        conn = sqlite3.connect(audit_db)
        conn.execute(
            "INSERT INTO conversations (id, session_id, role, content) VALUES (?, 'test', 'user', ?)",
            (conversation_id - 1, user_text),
        )
        conn.execute(
            "INSERT INTO conversations (id, session_id, role, content) VALUES (?, 'test', 'assistant', ?)",
            (conversation_id, assistant_reply or "Merhaba! Elbette, işte sonuçlar: 1 2 3"),
        )
        conn.commit()
        conn.close()
        _seed_rows(audit_db, [{"tool_name": tool, "conversation_id": conversation_id,
                               "confirmed_at": "2026-08-31T12:00:00"}])

        monkeypatch.setattr(cf, "_load_base_corpus_embeddings", _fake_base_corpus)
        monkeypatch.setattr(cf, "_load_addition_embeddings", lambda: ([], None))
        monkeypatch.setattr(cf, "_is_duplicate", lambda *a, **kw: False)
        monkeypatch.setattr(cf, "_check_conflict", lambda *a, **kw: None)
        import tools.definitions as td
        monkeypatch.setattr(td, "TOOL_TO_GROUP", {tool: group})
        import embedding as emb
        monkeypatch.setattr(emb, "embed", _fake_embed)
        return asyncio.run(cf.run(db_path=audit_db))

    def test_feeds_user_command_not_assistant_reply(self, audit_db, corpus_data_dir, monkeypatch):
        # The assistant reply is the kind of output that previously poisoned the
        # corpus. The feeder must resolve and feed the preceding USER command.
        summary = self._run_single(audit_db, corpus_data_dir, monkeypatch,
                                   user_text="Notları listele",
                                   assistant_reply="Merhaba! Elbette, notların listesi: 1. Mobil 2. deneme")
        assert summary["added"] == 1
        additions = cf._load_jsonl(cf.ADDITIONS_FILE)
        assert additions[0]["text"] == "Notları listele"  # user command, NOT the reply

    def test_assistant_output_like_text_rejected(self, audit_db, corpus_data_dir, monkeypatch):
        # Even if the resolved text looks like an assistant reply, reject it.
        summary = self._run_single(audit_db, corpus_data_dir, monkeypatch,
                                   user_text="Merhaba! Elbette, notların listesini aşağıda bulabilirsin")
        assert summary["added"] == 0
        assert summary["ambiguous"] == 1
        ga = cf._load_genuinely_ambiguous()
        assert len(ga) == 1
        assert ga[0]["reason"] == "not_user_command"

    def test_single_word_rejected(self, audit_db, corpus_data_dir, monkeypatch):
        summary = self._run_single(audit_db, corpus_data_dir, monkeypatch, user_text="evet")
        assert summary["added"] == 0
        assert summary["ambiguous"] == 1

    def test_no_user_message_skips(self, audit_db, corpus_data_dir, monkeypatch):
        # Only an assistant row with no preceding user message → skip_no_text
        conn = sqlite3.connect(audit_db)
        conn.execute(
            "INSERT INTO conversations (id, session_id, role, content) VALUES (?, 'test', 'assistant', ?)",
            (10, "response"),
        )
        conn.commit()
        conn.close()
        _seed_rows(audit_db, [{"tool_name": "get_weather", "conversation_id": 10,
                               "confirmed_at": "2026-08-31T12:00:00"}])
        monkeypatch.setattr(cf, "_load_base_corpus_embeddings", _fake_base_corpus)
        monkeypatch.setattr(cf, "_load_addition_embeddings", lambda: ([], None))
        monkeypatch.setattr(cf, "_is_duplicate", lambda *a, **kw: False)
        monkeypatch.setattr(cf, "_check_conflict", lambda *a, **kw: None)
        import tools.definitions as td
        monkeypatch.setattr(td, "TOOL_TO_GROUP", {"get_weather": "weather"})
        import embedding as emb
        monkeypatch.setattr(emb, "embed", _fake_embed)
        summary = asyncio.run(cf.run(db_path=audit_db))
        assert summary["added"] == 0
        assert summary["skipped"] == 1
        assert summary["details"][0]["status"] == "skip_no_text"

    def test_is_user_command_like_heuristics(self):
        assert cf._is_user_command_like("notları listele") is True
        assert cf._is_user_command_like("bugün hava nasıl") is True
        assert cf._is_user_command_like("son 10 e-postayı göster") is True
        # rejected
        assert cf._is_user_command_like("Merhaba! Elbette, notların listesini aşağıda bulabilirsin") is False
        assert cf._is_user_command_like("evet") is False
        assert cf._is_user_command_like("") is False
        assert cf._is_user_command_like("1. Birinci\n2. İkinci\n3. Üçüncü") is False
        assert cf._is_user_command_like("x" * 300) is False


class TestBug2Alignment:
    """C-2: jsonl ↔ npy must stay index-aligned; write atomically; guard embed."""

    def test_rebuild_on_count_mismatch(self, corpus_data_dir, monkeypatch):
        import corpus_feeder as cf

        # 2 records in jsonl but only 1 vector in npy (simulated partial write)
        cf._append_jsonl(cf.ADDITIONS_FILE, {"text": "notları listele", "group": "notes", "audit_id": 1})
        cf._append_jsonl(cf.ADDITIONS_FILE, {"text": "hava durumu", "group": "weather", "audit_id": 2})
        ev = _fake_embed("notları listele")
        cf._ensure_data_dir()
        np.save(str(cf.EMBEDDINGS_FILE),
                np.frombuffer(ev, dtype="float32").reshape(1, -1))

        monkeypatch.setattr("embedding.embed", _fake_embed)

        additions, matrix = cf._load_addition_embeddings()

        assert len(additions) == 2
        assert matrix is not None and len(matrix) == 2
        # index-aligned: row order must match jsonl order
        expected_row0 = np.frombuffer(_fake_embed("notları listele"), dtype="float32")
        np.testing.assert_allclose(matrix[0], expected_row0)

    def test_missing_npy_rebuilds_and_persists(self, corpus_data_dir, monkeypatch):
        import corpus_feeder as cf

        cf._append_jsonl(cf.ADDITIONS_FILE, {"text": "notları listele", "group": "notes", "audit_id": 1})
        monkeypatch.setattr("embedding.embed", _fake_embed)

        additions, matrix = cf._load_addition_embeddings()

        assert len(additions) == 1
        assert matrix is not None and len(matrix) == 1
        # rebuild must have persisted a fresh npy atomically
        assert cf.EMBEDDINGS_FILE.exists()

    def test_embed_error_rolls_back_jsonl(self, audit_db, corpus_data_dir, monkeypatch):
        import corpus_feeder as cf

        _seed_conversation(audit_db, 5, "notları listele")
        _seed_rows(audit_db, [{"tool_name": "list_notes", "conversation_id": 5,
                               "confirmed_at": "2026-08-31T12:00:00"}])

        monkeypatch.setattr(cf, "_load_base_corpus_embeddings", _fake_base_corpus)
        monkeypatch.setattr(cf, "_load_addition_embeddings", lambda: ([], None))
        monkeypatch.setattr(cf, "_is_duplicate", lambda *a, **kw: False)
        monkeypatch.setattr(cf, "_check_conflict", lambda *a, **kw: None)
        import tools.definitions as td
        monkeypatch.setattr(td, "TOOL_TO_GROUP", {"list_notes": "notes"})

        def _boom(text):
            raise RuntimeError("embed unavailable")
        monkeypatch.setattr("embedding.embed", _boom)

        summary = asyncio.run(cf.run(db_path=audit_db))

        assert summary["added"] == 0
        assert summary["skipped"] == 1
        # jsonl must not contain the rolled-back record; npy stays aligned
        assert cf._load_jsonl(cf.ADDITIONS_FILE) == []
        additions, matrix = cf._load_addition_embeddings()
        assert additions == []
        assert matrix is None


class TestBug3LiveReload:
    """C-3: intent cache rebuilds live when additions.jsonl changes (no restart)."""

    def test_cache_rebuilds_when_additions_change(self, monkeypatch, tmp_path):
        import llm.intent as li

        ap = tmp_path / "corpus_data" / "additions.jsonl"
        ap.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(li, "_ADDITIONS_PATH", ap)

        async def _fake_embed_batch_async(descs):
            import numpy as np
            out = []
            for d in descs:
                rng = np.random.RandomState(hash(d) % (2**31))
                v = rng.randn(384).astype("float32")
                v /= np.linalg.norm(v) + 1e-9
                out.append(v.tobytes())
            return out

        monkeypatch.setattr("embedding.embed_batch_async", _fake_embed_batch_async)

        async def scenario():
            li.reset_tool_embed_cache()          # clean slate: no additions file
            base = await li._get_tool_embeddings()   # mtime=file-absent (None)
            base_count = len(base)
            ap.write_text(json.dumps({"text": "notları listele", "group": "notes"},
                                     ensure_ascii=False) + "\n")
            fresh = await li._get_tool_embeddings()  # mtime changed -> rebuild
            return base_count, fresh

        try:
            base_count, fresh = asyncio.run(scenario())
        finally:
            li.reset_tool_embed_cache()

        added_groups = {g for g, _d, _v in fresh}
        assert len(fresh) == base_count + 1
        assert "notes" in added_groups

    def test_reset_tool_embed_cache_forces_rebuild(self, monkeypatch, tmp_path):
        import llm.intent as li

        ap = tmp_path / "corpus_data" / "additions.jsonl"
        ap.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(li, "_ADDITIONS_PATH", ap)

        async def _fake_embed_batch_async(descs):
            import numpy as np
            out = []
            for d in descs:
                rng = np.random.RandomState(hash(d) % (2**31))
                v = rng.randn(384).astype("float32")
                out.append(v.tobytes())
            return out

        monkeypatch.setattr("embedding.embed_batch_async", _fake_embed_batch_async)

        async def scenario():
            li.reset_tool_embed_cache()
            c1 = await li._get_tool_embeddings()
            # no additions file, same mtime (None) -> no auto rebuild
            c2 = await li._get_tool_embeddings()
            assert c1 is c2  # cache stable without any change
            li.reset_tool_embed_cache()
            c3 = await li._get_tool_embeddings()
            return c1, c3

        try:
            c1, c3 = asyncio.run(scenario())
        finally:
            li.reset_tool_embed_cache()

        # reset forced a rebuild (new object) but content is identical (no
        # additions yet) — the reload path is exercised and stable.
        assert c1 is not c3
        assert c1 == c3


class TestBug4ConflictThreshold:
    """C-4: conflict check uses a calibrated, configurable cosine threshold."""

    def _run(self, text, proposed, base_groups, base_matrix,
             addrecs=(), addmat=None, threshold=None, monkeypatch=None):
        import corpus_feeder as cf
        monkeypatch.setattr("embedding.embed", _fake_embed)
        return cf._check_conflict(
            text, proposed, base_groups, base_matrix, list(addrecs), addmat,
            conflict_threshold=threshold,
        )

    def test_default_threshold_from_config(self):
        import config
        import corpus_feeder as cf
        assert getattr(config, "CONFLICT_COSINE", None) == 0.50
        # signature default is None -> resolves to config.CONFLICT_COSINE
        assert cf._check_conflict.__defaults__[0] is None

    def test_conflict_when_different_group_above_threshold(self, monkeypatch):
        import numpy as np
        # base corpus: one 'weather' row that is highly similar to the query
        base_groups = ["weather"]
        # _fake_embed("hava durumu") is deterministic; use it as the base row too
        base_matrix = np.frombuffer(_fake_embed("hava durumu"), dtype="float32").reshape(1, -1)
        res = self._run("hava durumu", "notes", base_groups, base_matrix,
                        threshold=0.5, monkeypatch=monkeypatch)
        assert res is not None
        assert res["source"] == "base_corpus"
        assert res["conflicts_with_group"] == "weather"

    def test_no_conflict_below_threshold(self, monkeypatch):
        import numpy as np
        # unrelated target -> very low cosine
        base_groups = ["calendar"]
        base_matrix = np.frombuffer(_fake_embed("etkinlik oluştur her öğlen"), dtype="float32").reshape(1, -1)
        res = self._run("hava durumu raporu çıkart", "weather", base_groups, base_matrix,
                        threshold=0.5, monkeypatch=monkeypatch)
        assert res is None

    def test_same_group_never_conflicts(self, monkeypatch):
        import numpy as np
        base_groups = ["weather"]
        base_matrix = np.frombuffer(_fake_embed("hava durumu"), dtype="float32").reshape(1, -1)
        res = self._run("hava durumu", "weather", base_groups, base_matrix,
                        threshold=0.5, monkeypatch=monkeypatch)
        assert res is None  # nearest group == proposed -> no conflict


class TestBug5NoopCorrection:
    """C-5: same-group 'corrections' are no-ops and must not feed the corpus."""

    def test_same_group_correction_skipped(self, audit_db, corpus_data_dir, monkeypatch):
        import corpus_feeder as cf

        # list_notes -> group 'notes'; user "corrects" to 'notes' (same group)
        _seed_conversation(audit_db, 6, "notları göster")
        _seed_rows(audit_db, [{"tool_name": "list_notes", "conversation_id": 6,
                               "corrected_at": "2026-08-31T12:00:00",
                               "expected_group": "notes",
                               "expected_tool": "list_notes"}])

        monkeypatch.setattr(cf, "_load_base_corpus_embeddings", _fake_base_corpus)
        monkeypatch.setattr(cf, "_load_addition_embeddings", lambda: ([], None))
        import tools.definitions as td
        monkeypatch.setattr(td, "TOOL_TO_GROUP", {"list_notes": "notes"})
        import embedding as emb
        monkeypatch.setattr(emb, "embed", _fake_embed)

        summary = asyncio.run(cf.run(db_path=audit_db))

        assert summary["added"] == 0
        assert summary["skipped"] == 1
        assert summary["details"][0]["status"] == "skip_noop_negative"
        assert cf._load_jsonl(cf.ADDITIONS_FILE) == []

    def test_real_cross_group_correction_still_adds(self, audit_db, corpus_data_dir, monkeypatch):
        import corpus_feeder as cf

        # get_weather -> 'weather'; user corrects to 'notes' (real signal)
        _seed_conversation(audit_db, 7, "notları göster")
        _seed_rows(audit_db, [{"tool_name": "get_weather", "conversation_id": 7,
                               "corrected_at": "2026-08-31T12:00:00",
                               "expected_group": "notes",
                               "expected_tool": "list_notes"}])

        monkeypatch.setattr(cf, "_load_base_corpus_embeddings", _fake_base_corpus)
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


class TestContextDependentExamples:
    """C-7: anaphoric follow-ups ('devam edelim en son X yapıyordun') must NOT
    be fed to the corpus — they are meaningless outside their conversation and
    warp embedding routing toward the referenced tool.
    """

    def test_filter_rejects_anaphoric_phrases(self):
        import corpus_feeder as cf
        assert cf._is_context_dependent("devam edelim en son epostayı gönderiyordun")
        assert cf._is_context_dependent("devam edelim en son notu düzenliyordun")
        assert cf._is_context_dependent("devam edelim son yaptığımız işe")
        assert cf._is_context_dependent("devam edelim")
        assert cf._is_context_dependent("kaldığımız yerden devam edelim")
        assert cf._is_context_dependent("en son konuştuğumuz etkinliği göster")
        assert cf._is_context_dependent("az önce bahsettiğim hava durumunu göster")

    def test_filter_keeps_standalone_commands(self):
        import corpus_feeder as cf
        assert not cf._is_context_dependent("Bugün hava nasıl?")
        assert not cf._is_context_dependent("Notları listele")
        assert not cf._is_context_dependent("en son mailleri göster")
        assert not cf._is_context_dependent("yarınki etkinliği sil")
        assert not cf._is_context_dependent("gönderilmiş 10 maili listele")

    def test_audit_232_skipped_not_added(self, audit_db, corpus_data_dir, monkeypatch):
        import corpus_feeder as cf

        # BUG-7 repro: audit 232 = "devam edelim en son epostayı gönderiyordun"
        _seed_conversation(audit_db, 8, "devam edelim en son epostayı gönderiyordun")
        _seed_rows(audit_db, [{"tool_name": "send_email", "conversation_id": 8,
                               "confirmed_at": "2026-08-31T12:00:00"}])

        monkeypatch.setattr(cf, "_load_base_corpus_embeddings", _fake_base_corpus)
        monkeypatch.setattr(cf, "_load_addition_embeddings", lambda: ([], None))
        import tools.definitions as td
        monkeypatch.setattr(td, "TOOL_TO_GROUP", {"send_email": "email"})
        import embedding as emb
        monkeypatch.setattr(emb, "embed", _fake_embed)

        summary = asyncio.run(cf.run(db_path=audit_db))

        assert summary["added"] == 0
        assert summary["skipped"] == 1
        assert summary["details"][0]["status"] == "skip_context_dependent"
        assert cf._load_jsonl(cf.ADDITIONS_FILE) == []
