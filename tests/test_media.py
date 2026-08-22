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


# -- /chat/upload (multipart image upload) --

import base64

from routers import chat as chat_router


@pytest.fixture
def upload_client():
    app = FastAPI()
    app.include_router(chat_router.router)
    return TestClient(app, base_url="http://localhost")


def test_upload_accepts_multipart(upload_client):
    raw = b"\xff\xd8\xff\xe0fakejpeg-bytes"
    r = upload_client.post("/chat/upload", files={"file": ("photo.jpg", raw, "image/jpeg")})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["size_bytes"] == len(raw)
    assert base64.b64decode(d["base64"]) == raw


def test_upload_rejects_oversized(upload_client, monkeypatch):
    import config

    real_get = config.get

    def fake_get(key, default=None):
        if key == "MEDIA_MAX_MB":
            return 1
        return real_get(key, default)

    monkeypatch.setattr(config, "get", fake_get)
    r = upload_client.post("/chat/upload", files={"file": ("big.jpg", b"x" * (1024 * 1024 + 1), "image/jpeg")})
    assert r.status_code == 413
    assert "max 1 MB" in r.json()["detail"]


def test_upload_requires_file_field(upload_client):
    r = upload_client.post("/chat/upload")
    assert r.status_code == 422


# -- gemma4 transcription: Ollama hardening + Whisper fallback --

class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient inside the gemma4 endpoint."""

    behavior = "ok"  # "ok" | "crash"
    calls = []
    response_json = {}

    def __init__(self, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        _FakeAsyncClient.calls.append((url, json))
        if _FakeAsyncClient.behavior == "crash":
            raise RuntimeError("ollama runner crashed")

        class _R:
            def raise_for_status(self):
                return None

            def json(self):
                return _FakeAsyncClient.response_json

        return _R()


def _patch_gemma4_happy_path(monkeypatch, tmp_path_factory, backend="ollama"):
    import config

    async def fake_save(upload):
        p = str(tmp_path_factory.mktemp("aud") / "rec.webm")
        with open(p, "wb") as f:
            f.write(b"webm-bytes")
        return p

    def fake_convert(src, dst, use_f32=False):
        with open(dst, "wb") as f:
            f.write(b"RIFF....WAVEfmt ")
        from subprocess import CompletedProcess
        return CompletedProcess([], 0, b"", b"")

    monkeypatch.setattr(config, "LLM_BACKEND", backend)
    monkeypatch.setattr(media, "_check_ffmpeg", lambda: True)
    monkeypatch.setattr(media, "_save_upload", fake_save)
    monkeypatch.setattr(media, "_convert_to_wav", fake_convert)
    monkeypatch.setattr(media.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.calls = []


def test_transcribe_gemma4_ollama_caps_num_ctx_and_falls_back_to_whisper(
    media_client, monkeypatch, tmp_path_factory
):
    _patch_gemma4_happy_path(monkeypatch, tmp_path_factory, backend="ollama")
    _FakeAsyncClient.behavior = "crash"

    class _FakeWhisper:
        def transcribe(self, path, **kw):
            assert kw.get("language") == "tr"
            return {"text": "  merhaba dünya  ", "language": "tr"}

    whisper_used = []

    def fake_get_whisper():
        whisper_used.append(True)
        return _FakeWhisper()

    monkeypatch.setattr(media, "_get_whisper", fake_get_whisper)
    monkeypatch.setattr(media, "_whisper_backend", "openai_whisper")

    r = media_client.post(
        "/chat/transcribe-gemma4?lang=tr&emotion=false",
        files={"audio": ("rec.webm", b"webm-bytes", "audio/webm")},
    )

    assert r.status_code == 200
    assert r.json()["text"] == "merhaba dünya"
    assert whisper_used == [True]
    url, payload = _FakeAsyncClient.calls[0]
    assert url.endswith("/api/chat")
    assert payload["options"]["num_ctx"] == 8192


def test_transcribe_gemma4_ollama_success_skips_whisper(
    media_client, monkeypatch, tmp_path_factory
):
    _patch_gemma4_happy_path(monkeypatch, tmp_path_factory, backend="ollama")
    _FakeAsyncClient.behavior = "ok"
    _FakeAsyncClient.response_json = {"message": {"content": "selam"}}

    def no_whisper():
        raise AssertionError("Whisper must not be loaded when gemma4 succeeds")

    monkeypatch.setattr(media, "_get_whisper", no_whisper)

    r = media_client.post(
        "/chat/transcribe-gemma4?lang=tr&emotion=false",
        files={"audio": ("rec.webm", b"webm-bytes", "audio/webm")},
    )

    assert r.status_code == 200
    assert r.json()["text"] == "selam"


def test_transcribe_gemma4_litert_empty_still_422_no_whisper(
    media_client, monkeypatch, tmp_path_factory
):
    _patch_gemma4_happy_path(monkeypatch, tmp_path_factory, backend="litert")
    _FakeAsyncClient.behavior = "ok"
    _FakeAsyncClient.response_json = {"choices": [{"message": {"content": ""}}]}

    def no_whisper():
        raise AssertionError("Whisper fallback is ollama-only")

    monkeypatch.setattr(media, "_get_whisper", no_whisper)

    r = media_client.post(
        "/chat/transcribe-gemma4?lang=tr&emotion=false",
        files={"audio": ("rec.webm", b"webm-bytes", "audio/webm")},
    )

    assert r.status_code == 422
