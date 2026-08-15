"""Tests for the media router: TTS validation, synthesis and markdown
stripping. Transcription (whisper) is covered by the live smoke test.
"""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import media


@pytest.fixture
def media_client():
    app = FastAPI()
    app.include_router(media.router)
    return TestClient(app, base_url="http://localhost")


class _FakeVoice:
    def __init__(self):
        self.text = None

    def synthesize_wav(self, text, wf):
        self.text = text
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"\x00\x00" * 100)


def test_tts_missing_text(media_client):
    r = media_client.post("/chat/tts", json={"voice": "en_US-amy-medium"})
    assert r.status_code == 400


def test_tts_empty_text(media_client):
    r = media_client.post("/chat/tts", json={"text": "", "voice": "en_US-amy-medium"})
    assert r.status_code == 400


def test_tts_invalid_voice(media_client):
    r = media_client.post("/chat/tts", json={"text": "hi", "voice": "bad-voice"})
    assert r.status_code == 400


def test_tts_invalid_json(media_client):
    r = media_client.post("/chat/tts", content=b"not json")
    assert r.status_code == 400


def test_tts_unavailable_model_returns_503(media_client, monkeypatch):
    async def none_tts(voice):
        return None

    monkeypatch.setattr(media, "_get_tts", none_tts)
    r = media_client.post("/chat/tts", json={"text": "hi"})
    assert r.status_code == 503


def test_tts_synthesizes_audio(media_client, monkeypatch):
    voice = _FakeVoice()

    async def get_tts(voice_name):
        return voice

    monkeypatch.setattr(media, "_get_tts", get_tts)
    r = media_client.post("/chat/tts", json={"text": "Hello there", "voice": "en_US-amy-medium"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    assert voice.text == "Hello there"


def test_tts_truncates_text_to_2000_chars(media_client, monkeypatch):
    voice = _FakeVoice()

    async def get_tts(voice_name):
        return voice

    monkeypatch.setattr(media, "_get_tts", get_tts)
    r = media_client.post("/chat/tts", json={"text": "x" * 5000})
    assert r.status_code == 200
    assert len(voice.text) <= 2000


def test_strip_markdown():
    assert media._strip_markdown("**bold** and *italic* and [a](url)") == "bold and italic and a"


class _FakeUpload:
    def __init__(self, data: bytes, filename="a.webm", content_length=None):
        self._data = data
        self.filename = filename
        self.headers = {"content-length": str(content_length)} if content_length is not None else {}
        self._pos = 0

    async def read(self, n=-1):
        if self._pos >= len(self._data):
            return b""
        chunk = self._data[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk


@pytest.mark.asyncio
async def test_save_upload_streams_small_file(monkeypatch):
    monkeypatch.setattr(media, "_upload_max_bytes", lambda: 1024 * 1024)
    path = await media._save_upload(_FakeUpload(b"abc123", content_length=6))
    try:
        with open(path, "rb") as f:
            assert f.read() == b"abc123"
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_save_upload_rejects_oversized_via_content_length(monkeypatch):
    monkeypatch.setattr(media, "_upload_max_bytes", lambda: 100)
    with pytest.raises(media._UploadTooLargeError) as exc:
        await media._save_upload(_FakeUpload(b"x" * 200, content_length=200))
    assert exc.value.max_bytes == 100


@pytest.mark.asyncio
async def test_save_upload_aborts_mid_stream_without_content_length(monkeypatch):
    monkeypatch.setattr(media, "_upload_max_bytes", lambda: 100)
    with pytest.raises(media._UploadTooLargeError) as exc:
        await media._save_upload(_FakeUpload(b"x" * 1000, content_length=None))
    assert exc.value.max_bytes == 100


def test_upload_max_bytes_tracks_media_max_mb(monkeypatch):
    import config

    monkeypatch.setattr(config, "MEDIA_MAX_MB", 50)
    assert media._upload_max_bytes() == 50 * 1024 * 1024
    monkeypatch.setattr(config, "MEDIA_MAX_MB", 100)
    assert media._upload_max_bytes() == 100 * 1024 * 1024
