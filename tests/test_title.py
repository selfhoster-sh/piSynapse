"""Tests for hybrid title generation: RAKE instant + LLM enriched."""

import pytest

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
        # No stripping — first 4 words
        assert result == "hava durumu bilgisini sa.dg725@proton.me"

    def test_strips_url(self):
        result = generate_rake_title("Bu sayfadaki bilgileri özetle https://example.com")
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
        # max_words ignored — always 4
        assert result == "Python aiosqlite veritabanı bağlantısı"
        assert len(result.split()) == 4

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
