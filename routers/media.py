#!/usr/bin/env python3
"""piSynapse Media API Router
Handles audio transcription (Whisper, Gemma4) and text-to-speech (Piper).
"""

import asyncio
import base64
import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import wave

import httpx
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from starlette.responses import Response

logger = logging.getLogger("piSynapse")

router = APIRouter(prefix="/chat", tags=["chat"])


# -- Whisper Transcription --

_whisper_model = None
_whisper_backend = None

def _get_whisper():
    global _whisper_model, _whisper_backend
    if _whisper_model is not None:
        return _whisper_model

    try:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        _whisper_backend = "faster_whisper"
        logger.info("Whisper model loaded (faster-whisper tiny, CPU)")
        return _whisper_model
    except ImportError:
        logger.info("faster-whisper not installed, trying openai-whisper...")
    except Exception as e:
        logger.warning(f"faster-whisper load failed: {e}, trying openai-whisper...")

    try:
        import whisper as _ow
        _whisper_model = _ow.load_model("tiny")
        _whisper_backend = "openai_whisper"
        logger.info("Whisper model loaded (openai-whisper tiny)")
        return _whisper_model
    except ImportError:
        logger.warning("openai-whisper not installed either — transcription unavailable")
    except Exception as e:
        logger.error(f"openai-whisper load failed: {e}")

    return None


def _transcribe_faster(model, path: str, kwargs: dict) -> tuple[str, str]:
    """Run faster-whisper transcription (incl. lazy segment iteration) in a thread."""
    segments, info = model.transcribe(path, **kwargs)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    return text, info.language


_ffmpeg_available = None

def _check_ffmpeg() -> bool:
    global _ffmpeg_available
    if _ffmpeg_available is not None:
        return _ffmpeg_available
    _ffmpeg_available = shutil.which("ffmpeg") is not None
    if not _ffmpeg_available:
        logger.warning("ffmpeg not found — gemma4 audio transcription unavailable")
    return _ffmpeg_available


_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _convert_to_wav(src: str, dst: str, pcm_f32le: bool = False) -> subprocess.CompletedProcess:
    """Run ffmpeg conversion off the event loop (caller wraps in to_thread)."""
    cmd = ["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1"]
    if pcm_f32le:
        cmd += ["-acodec", "pcm_f32le"]
    cmd += ["-f", "wav", dst]
    return subprocess.run(cmd, capture_output=True, timeout=30)

_GEMMA4_ASR_PROMPT = (
    "Transcribe the following speech segment in {lang} into {lang} text.\n\n"
    "Follow these specific instructions for formatting the answer:\n"
    "* Only output the transcription, with no newlines.\n"
    "* When transcribing numbers, write the digits, i.e. write 1.7 and not one point seven, and write 3 instead of three."
)

_GEMMA4_ASR_EMOTION_PROMPT = (
    "Analyze the following audio clip.\n\n"
    "1. Transcribe the speech in {lang} into {lang} text. Only output the transcription, with no newlines. "
    "When transcribing numbers, write the digits.\n"
    "2. On a NEW line after the transcription, output exactly this format on one line:\n"
    "EMOTION:{{emotion}} TONE:{{tone}} MOOD:{{mood}}\n\n"
    "Where emotion is one word (happy, sad, angry, neutral, excited, worried, frustrated, grateful, surprised, tired), "
    "tone is one word (formal, casual, sarcastic, earnest, playful, serious, gentle, demanding), "
    "and mood is one word (positive, negative, neutral, anxious, calm).\n\n"
    "Example output:\n"
    "Hava durumunu kontrol et\n"
    "EMOTION:neutral TONE:casual MOOD:calm"
)


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    lang: str = Query(default=""),
):
    model = _get_whisper()
    if model is None:
        raise HTTPException(status_code=503, detail="Transcription service unavailable. Install faster-whisper or openai-whisper.")
    suffix = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"
    data = await audio.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large (max 25 MB)")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    whisper_lang = None
    if lang:
        whisper_lang = lang

    try:
        audio_size = len(data)
        logger.info(f"Whisper input: {audio_size} bytes, suffix={suffix}, lang={whisper_lang}")

        wav_path = tmp_path + ".wav"
        conv = await asyncio.to_thread(_convert_to_wav, tmp_path, wav_path)
        if conv.returncode == 0 and os.path.exists(wav_path):
            wav_size = os.path.getsize(wav_path)
            logger.info(f"WAV conversion: {audio_size}b webm → {wav_size}b wav (16kHz mono)")
            transcribe_path = wav_path
        else:
            logger.warning(f"ffmpeg conversion failed for whisper, using raw file: {conv.stderr.decode()[:200]}")
            transcribe_path = tmp_path

        try:
            if _whisper_backend == "openai_whisper":
                import asyncio as _aio
                kwargs = {
                    "beam_size": 5,
                    "condition_on_previous_text": False,
                    "fp16": False,
                }
                if whisper_lang:
                    kwargs["language"] = whisper_lang
                result = await _aio.to_thread(model.transcribe, transcribe_path, **kwargs)
                text = result["text"].strip()
                lang_out = result.get("language", "unknown")
            else:
                kwargs = {
                    "beam_size": 5,
                    "condition_on_previous_text": False,
                }
                if whisper_lang:
                    kwargs["language"] = whisper_lang
                text, lang_out = await asyncio.to_thread(
                    _transcribe_faster, model, transcribe_path, kwargs
                )
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)
        logger.info(f"Whisper result ({lang_out}): {text[:100]!r}" if text else "Whisper: empty transcription")
        if not text:
            raise HTTPException(status_code=422, detail="Whisper returned empty transcription")
        return {"text": text, "language": lang_out}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")
    finally:
        os.unlink(tmp_path)


@router.post("/transcribe-gemma4")
async def transcribe_gemma4(
    audio: UploadFile = File(...),
    lang: str = Query(default="tr"),
    emotion: bool = Query(default=True),
):
    if not _check_ffmpeg():
        raise HTTPException(status_code=503, detail="ffmpeg not installed — gemma4 audio transcription unavailable. Install ffmpeg or use whisper engine.")
    from config import LITERT_BASE_URL, LLM_BACKEND, LLM_MODEL, OLLAMA_BASE_URL
    suffix = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"
    data = await audio.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large (max 25 MB)")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    wav_path = tmp_path + ".wav"
    try:
        conv = await asyncio.to_thread(_convert_to_wav, tmp_path, wav_path, True)
        if conv.returncode != 0:
            logger.error(f"ffmpeg conversion failed: {conv.stderr.decode()[:200]}")
            raise HTTPException(status_code=500, detail="Audio conversion failed")

        if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
            raise HTTPException(status_code=500, detail="ffmpeg produced empty WAV file")

        with open(wav_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")

        lang_names = {"tr": "Turkish", "en": "English", "de": "German", "fr": "French",
                       "es": "Spanish", "ru": "Russian", "ar": "Arabic", "ja": "Japanese"}
        lang_name = lang_names.get(lang, lang)

        prompt = _GEMMA4_ASR_PROMPT.format(lang=lang_name)
        num_predict = 256

        if emotion:
            prompt = _GEMMA4_ASR_EMOTION_PROMPT.format(lang=lang_name)
            num_predict = 512

        model_name = LLM_MODEL.replace(":", "-") if LLM_BACKEND == "litert" else LLM_MODEL

        if LLM_BACKEND == "litert":
            payload = {
                "model": model_name,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "input_audio", "input_audio": {"data": audio_b64}},
                    ],
                }],
                "max_tokens": num_predict,
                "temperature": 0.1,
            }
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(f"{LITERT_BASE_URL}/v1/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        else:
            payload = {
                "model": model_name,
                "messages": [{
                    "role": "user",
                    "content": prompt,
                    "images": [audio_b64],
                }],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": num_predict},
            }
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
            text = data.get("message", {}).get("content", "").strip()

        logger.info(f"Gemma4 transcription ({lang_name}): {text[:100]!r}" if text else "Gemma4 transcription: empty response")
        if not text:
            raise HTTPException(status_code=422, detail="Gemma4 returned empty transcription")

        emotion_data = None
        if emotion:
            emotion_match = re.search(r"EMOTION:(\w+)\s+TONE:(\w+)\s+MOOD:(\w+)", text)
            if emotion_match:
                emotion_data = {
                    "emotion": emotion_match.group(1),
                    "tone": emotion_match.group(2),
                    "mood": emotion_match.group(3),
                }
                text = text[:emotion_match.start()].strip()
                logger.info(f"Gemma4 emotion: {emotion_data}")

        return {"text": text, "language": lang_name, "emotion": emotion_data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gemma4 transcription error: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")
    finally:
        for p in (tmp_path, wav_path):
            if os.path.exists(p):
                os.unlink(p)


# -- Piper TTS --

_tts_voices: dict[str, object] = {}
_tts_lock = asyncio.Lock()

PIPER_MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "piper")

ALLOWED_TTS_VOICES = {
    "tr_TR-dfki-medium",
    "en_US-lessac-medium",
    "en_US-amy-medium",
}

async def _get_tts(voice_name: str):
    if voice_name in _tts_voices:
        return _tts_voices[voice_name]
    async with _tts_lock:
        if voice_name in _tts_voices:
            return _tts_voices[voice_name]
        try:
            from piper import PiperVoice
            search_paths = [
                os.path.join(PIPER_MODELS_DIR, f"{voice_name}.onnx"),
                os.path.expanduser(f"~/.local/share/piper-voices/{voice_name}/{voice_name}.onnx"),
                os.path.expanduser(f"~/.config/piper-voices/{voice_name}/{voice_name}.onnx"),
            ]
            model_path = next((p for p in search_paths if os.path.exists(p)), None)
            if model_path is None:
                logger.warning(f"Piper voice not found: {voice_name}")
                return None
            voice = PiperVoice.load(model_path)
            _tts_voices[voice_name] = voice
            logger.info(f"Piper TTS loaded: {voice_name}")
            return voice
        except ImportError:
            logger.warning("piper-tts not installed, TTS unavailable")
            return None
        except Exception as e:
            logger.error(f"Failed to load Piper TTS ({voice_name}): {e}")
            return None


def _strip_markdown(text: str) -> str:
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'^[\-\*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\-\*\+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\|', ' ', text)
    text = re.sub(r'(?<!\w)[*_]{1,2}(?!\w)', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


@router.head("/tts")
async def tts_head():
    return Response(status_code=200, headers={"Content-Type": "audio/wav"})


@router.post("/tts")
async def text_to_speech(request: Request):
    from config import TTS_VOICE as default_voice
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    text = (body.get("text") or "")[:2000]
    voice_name = (body.get("voice") or default_voice)
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    text = _strip_markdown(text)
    if voice_name not in ALLOWED_TTS_VOICES:
        raise HTTPException(status_code=400, detail="Invalid voice name")
    model = await _get_tts(voice_name)
    if model is None:
        raise HTTPException(status_code=503, detail="TTS unavailable. Install piper-tts and download a voice model.")

    def _synthesize():
        audio_buf = io.BytesIO()
        with wave.open(audio_buf, "wb") as wf:
            model.synthesize_wav(text[:2000], wf)
        audio_buf.seek(0)
        return audio_buf.read()

    audio_data = await asyncio.to_thread(_synthesize)

    async def _stream_audio():
        yield audio_data

    return StreamingResponse(_stream_audio(), media_type="audio/wav",
                             headers={"Cache-Control": "no-cache"})
