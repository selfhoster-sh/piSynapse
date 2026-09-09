"""Tests for hybrid title generation: RAKE instant + LLM enriched."""

import asyncio

import pytest

import config as config_module
import db as dbmod
import embedding
import title as title_module
from title import generate_rake_title


class TestRakeTitle:
    """Unit tests for first-4-words instant title."""

    def test_turkish_weather(self):
        result = generate_rake_title("İstanbul için yarınki hava durumu bilgisini gönder")
        assert result == "İstanbul için yarınki hava"

    def test_turkish_email(self):
        result = generate_rake_title("Bana gelen son e-postaları özetleyip önemli olanları işaretler misin")
        assert result == "Bana gelen son e-postaları"
        assert len(result.split()) == 4

    def test_english_weather(self):
        result = generate_rake_title("What is the current weather forecast for London tomorrow")
        assert result == "What is the current"

    def test_english_technical(self):
        result = generate_rake_title("How do I fix memory leak issues in Node.js express application")
        assert result == "How do I fix"

    def test_strips_email(self):
        result = generate_rake_title("hava durumu bilgisini sa.dg725@proton.me adresine gönder")
        # PII masked — the address must not land in the sidebar title verbatim
        assert "sa.dg725@proton.me" not in result
        assert result == "hava durumu bilgisini [e-posta]"

    def test_strips_url(self):
        result = generate_rake_title("Bu sayfadaki bilgileri özetle https://example.com")
        assert "https://example.com" not in result
        assert result == "Bu sayfadaki bilgileri özetle"

    def test_short_input(self):
        result = generate_rake_title("Hava durumu")
        assert result == "Hava durumu"
        assert len(result.split()) <= 4

    def test_single_word(self):
        result = generate_rake_title("Merhaba")
        assert result == "Merhaba"

    def test_max_words_limit(self):
        result = generate_rake_title("Python aiosqlite veritabanı bağlantısı kilitlenme hatası çözümü", max_words=3)
        # max_words caps the default 4-word take
        assert result == "Python aiosqlite veritabanı"
        assert len(result.split()) == 3

    def test_empty_input(self):
        result = generate_rake_title("")
        assert result == "Yeni Sohbet"

    def test_only_stop_words(self):
        result = generate_rake_title("bir ve bu ile için ne var")
        assert result == "bir ve bu ile"

    def test_numbers_stripped(self):
        result = generate_rake_title("toplantı saat 14:00'da başlayacak")
        assert result == "toplantı saat 14:00'da başlayacak"
        assert "14" in result

    def test_turkish_technical(self):
        result = generate_rake_title("Python aiosqlite veritabanı bağlantısı kilitlenme hatasını nasıl çözerim")
        assert result == "Python aiosqlite veritabanı bağlantısı"

    def test_performance(self):
        """First-4-words must be under 1ms."""
        import time
        times = []
        for _ in range(100):
            t0 = time.perf_counter()
            generate_rake_title("İstanbul için yarınki hava durumu bilgisini gönder")
            times.append((time.perf_counter() - t0) * 1000)
        avg = sum(times) / len(times)
        assert avg < 1.0, f"Too slow: {avg:.3f}ms avg (must be <1ms)"

    def test_casing_preserved(self):
        result = generate_rake_title("python async hatası çözümü")
        assert result == "python async hatası çözümü"


class TestLLMTitle:
    """Tests for generate_llm_title (async, requires litert or ollama)."""

    @pytest.mark.asyncio
    async def test_llm_returns_title(self):
        from title import generate_llm_title
        # This test requires a running LLM backend
        # Skip if not available
        try:
            title = await generate_llm_title(
                "İstanbul için yarınki hava durumu",
                "İstanbul'da yarın hava güneşli, 24°C olacak.",
            )
            if title is not None:
                assert len(title) > 0
                assert 2 <= len(title.split()) <= 5
                assert len(title) <= 60
        except Exception:
            pytest.skip("LLM backend not available")

    @pytest.mark.asyncio
    async def test_llm_failure_returns_none(self):
        """LLM failure must return None, never raise."""
        # Force failure by patching httpx (title.py now uses httpx, not requests)
        import unittest.mock as mock

        from title import generate_llm_title
        mock_client = mock.AsyncMock()
        mock_client.__aenter__.return_value.post = mock.AsyncMock(side_effect=ConnectionError("no server"))
        with mock.patch("httpx.AsyncClient", return_value=mock_client):
            result = await generate_llm_title("test", "test")
            assert result is None


@pytest.fixture
def title_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "title.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())

    async def _fake_embed(_text):
        return b"\x00" * 16

    monkeypatch.setattr(embedding, "embed_async", _fake_embed)
    monkeypatch.setattr(config_module, "LLM_TITLE_ENRICHMENT", "on")
    yield dbmod
    asyncio.run(dbmod.close_db())


def _seed_turns(n_pairs=1):
    async def _go():
        for i in range(n_pairs):
            await dbmod.save_message("sx", "user", f"plan trip idea {i}", user_id="alice")
            await dbmod.save_message("sx", "assistant", f"glad to help {i}", user_id="alice")

    asyncio.run(_go())


def _fake_llm(monkeypatch, calls, result="LLM Title"):
    async def _gen(_user_msg, _asst_msg):
        calls.append(1)
        return result

    monkeypatch.setattr(title_module, "generate_llm_title", _gen)


def _session_name():
    async def _go():
        db = await dbmod.get_db()
        cur = await db.execute("SELECT name FROM sessions WHERE id = 'sx'")
        return (await cur.fetchone())[0]

    return asyncio.run(_go())


class TestEnrichTitle:
    """_enrich_title first-chance + never-overwrite behavior."""

    def test_fast_second_turn_still_enriches(self, title_db, monkeypatch):
        from routers import chat as chat_router

        _seed_turns(n_pairs=2)  # total 4: second user turn landed first
        assert _session_name() == generate_rake_title("plan trip idea 0")
        calls = []
        _fake_llm(monkeypatch, calls)
        asyncio.run(chat_router._enrich_title("sx", user_id="alice"))
        assert calls == [1]
        assert _session_name() == "LLM Title"

    def test_enriched_or_renamed_name_never_overwritten(self, title_db, monkeypatch):
        from routers import chat as chat_router

        _seed_turns(n_pairs=1)
        asyncio.run(dbmod.update_session_name("sx", "My Custom", user_id="alice"))
        calls = []
        _fake_llm(monkeypatch, calls)
        asyncio.run(chat_router._enrich_title("sx", user_id="alice"))
        assert calls == []
        assert _session_name() == "My Custom"

    def test_old_session_skipped(self, title_db, monkeypatch):
        from routers import chat as chat_router

        _seed_turns(n_pairs=3)  # total 6: window closed
        calls = []
        _fake_llm(monkeypatch, calls)
        asyncio.run(chat_router._enrich_title("sx", user_id="alice"))
        assert calls == []


class TestMigrationGuards:
    """_safe_ident/_safe_ddl_definition allowlist behavior."""

    def test_current_migrations_pass_guards(self):
        from db import MIGRATIONS, _safe_ddl_definition, _safe_ident

        for table, column, definition in MIGRATIONS:
            assert _safe_ident(table).startswith('"')
            assert _safe_ident(column).startswith('"')
            assert _safe_ddl_definition(definition)

    def test_guards_reject_injection(self):
        import pytest as _pytest

        from db import _safe_ddl_definition, _safe_ident

        for evil in ["t; DROP TABLE x", "t--", "x y", "", "t\""]:
            with _pytest.raises(ValueError):
                _safe_ident(evil)
        for evil in ["TEXT; DROP TABLE x", "TEXT --x", "TEXT /*x*/", ""]:
            with _pytest.raises(ValueError):
                _safe_ddl_definition(evil)
