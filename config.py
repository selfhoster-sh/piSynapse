"""piSynapse Configuration
Single source of truth for all settings. Reads from .env once at startup.
Every module imports from here instead of reading os.getenv() directly.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("piSynapse")


def _safe_int(key: str, default: int) -> int:
    """Parse an int env var with fallback and logging on invalid values."""
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        logger.warning(f"Invalid {key}={raw!r}, using default {default}")
        return default


def _safe_float(key: str, default: float) -> float:
    """Parse a float env var with fallback and logging on invalid values."""
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (ValueError, TypeError):
        logger.warning(f"Invalid {key}={raw!r}, using default {default}")
        return default

# -- Paths --
ENV_PATH = Path(os.getenv("ENV_PATH", ".env"))
DB_PATH = os.getenv("DB_PATH", "assistant.db")

# -- LLM Backend --
# "ollama" — Ollama server (default, http://localhost:11434)
# "litert" — LiteRT-LM server (http://localhost:9379, OpenAI-compatible)
LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama").lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LITERT_BASE_URL = os.getenv("LITERT_BASE_URL", "http://localhost:9379")
LLM_MODEL = os.getenv("LLM_MODEL", "gemma4:e2b")
LLM_NUM_CTX = _safe_int("LLM_NUM_CTX", 8192)
LLM_NUM_BATCH = _safe_int("LLM_NUM_BATCH", 256)
LLM_TEMPERATURE = _safe_float("LLM_TEMPERATURE", 0.6)
LLM_TOP_P = _safe_float("LLM_TOP_P", 0.85)
LLM_TOP_K = _safe_int("LLM_TOP_K", 40)
LLM_MAX_TOOL_ITERATIONS = _safe_int("LLM_MAX_TOOL_ITERATIONS", 5)
LLM_KEEP_ALIVE = os.getenv("LLM_KEEP_ALIVE", "4h")
LLM_TIMEOUT = _safe_int("LLM_TIMEOUT", 120)

# -- TTS (Piper) --
TTS_VOICE = os.getenv("TTS_VOICE", "en_US-lessac-medium")

# -- TTS Engine --
# "piper"  — Piper TTS local model (~50MB per voice, fully offline)
#            Pros: consistent quality, no internet needed, privacy-safe
#            Cons: limited voice selection, requires model download
# "browser" — Web Speech API (browser built-in, sends text to cloud)
#            Pros: many voices, no model download, responsive
#            Cons: sends text to Google/Apple servers, quality varies
TTS_ENGINE = os.getenv("TTS_ENGINE", "piper")

# -- STT (Speech-to-Text) --
# "gemma4" — Gemma 4 E2B/E4B native audio via /v1/chat/completions
#           Pros: captures emotion/tone, no extra model download, fully local
#           Cons: slower (~5-15s on Pi), less accurate transcription than Whisper
# "whisper" — faster-whisper (local Whisper C++ port, tiny model ~75MB)
#           Pros: fast (~1-2s), very accurate transcription, lightweight
#           Cons: no emotion/tone, text-only output
STT_ENGINE = os.getenv("STT_ENGINE", "whisper")

# -- Voice Input Behavior --
# "on" — auto-send message after voice transcription (no manual send needed)
# "off" — show transcription in input, user presses send
AUTO_SEND_ON_VOICE = os.getenv("AUTO_SEND_ON_VOICE", "off")
# "on" — auto-speak response when input was voice (uses TTS_ENGINE setting)
# "off" — text-only response even if input was voice
AUTO_TTS_ON_VOICE = os.getenv("AUTO_TTS_ON_VOICE", "off")

# -- Security --
API_KEY = os.getenv("API_KEY", "")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
TRUSTED_HOSTS = {h.strip() for h in os.getenv("TRUSTED_HOSTS", "*").split(",") if h.strip()}
MEDIA_MAX_MB = _safe_int("MEDIA_MAX_MB", 100)

# -- Chat --
HISTORY_LIMIT = _safe_int("HISTORY_LIMIT", 12)
MEMORY_LIMIT = _safe_int("MEMORY_LIMIT", 10)
SUMMARY_BATCH_SIZE = _safe_int("SUMMARY_BATCH_SIZE", 5)
SUMMARY_EARLY_TRIGGER = _safe_int("SUMMARY_EARLY_TRIGGER", 6)
INTENT_LLM_FALLBACK = os.getenv("INTENT_LLM_FALLBACK", "off")

# -- Memory --
DEFAULT_USER = os.getenv("ASSISTANT_USER", "default")
MEMORY_SIMILARITY_THRESHOLD = _safe_float("MEMORY_SIMILARITY_THRESHOLD", 0.68)
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# -- Weather --
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "")
WEATHER_TIMEOUT = _safe_int("WEATHER_TIMEOUT", 10)

# -- Nextcloud --
NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL", "")
NEXTCLOUD_USER = os.getenv("NEXTCLOUD_USER", "")
NEXTCLOUD_PASSWORD = os.getenv("NEXTCLOUD_PASSWORD", "")
NEXTCLOUD_TIMEOUT = _safe_int("NEXTCLOUD_TIMEOUT", 30)

# -- Gmail --
GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = _safe_int("IMAP_PORT", 993)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = _safe_int("SMTP_PORT", 465)
IMAP_TIMEOUT = _safe_int("IMAP_TIMEOUT", 30)
SMTP_TIMEOUT = _safe_int("SMTP_TIMEOUT", 30)

# -- ProtonMail --
MAIL_PROVIDER = os.getenv("MAIL_PROVIDER", "gmail")
PROTON_USER = os.getenv("PROTON_USER", "")
PROTON_PASSWORD = os.getenv("PROTON_PASSWORD", "")
PROTON_IMAP_HOST = os.getenv("PROTON_IMAP_HOST", "localhost")
PROTON_IMAP_PORT = _safe_int("PROTON_IMAP_PORT", 1143)
PROTON_SMTP_HOST = os.getenv("PROTON_SMTP_HOST", "localhost")
PROTON_SMTP_PORT = _safe_int("PROTON_SMTP_PORT", 1025)

# -- Model options per backend --
# LiteRT uses dashes, Ollama uses colons in model names.
# Tried live queries first (litert /v1/models, ollama list), then fallback to these.
LITERT_MODEL_OPTIONS = [
    {"value": "gemma4-e2b", "label": {"tr": "Gemma4 E2B (gorsel, ses, tool calling)",  "en": "Gemma4 E2B (vision, audio, tool calling)"}},
    {"value": "gemma4-e4b", "label": {"tr": "Gemma4 E4B (gorsel, ses, tool calling)",  "en": "Gemma4 E4B (vision, audio, tool calling)"}},
]
OLLAMA_MODEL_OPTIONS = [
    {"value": "gemma4:e2b",      "label": {"tr": "Gemma4 E2B (gorsel, ses, tool calling)",  "en": "Gemma4 E2B (vision, audio, tool calling)"}},
    {"value": "qwen2.5:3b",     "label": {"tr": "Qwen2.5 3B (hizli, tool calling, ~2GB)",  "en": "Qwen2.5 3B (fast, tool calling, ~2GB)"}},
    {"value": "qwen3:4b",        "label": {"tr": "Qwen3 4B (hizli, 119 dil)",              "en": "Qwen3 4B (fast, 119 languages)"}},
]


# Cache for get_llm_model_options — 30s TTL to avoid hammering the backend on every settings load.
_MODEL_OPTIONS_CACHE: dict = {"data": None, "ts": 0.0, "backend": ""}


def get_llm_model_options() -> dict:
    """Return LLM_MODEL options dict keyed by backend.

    Tries live query from the running backend server first (litert /v1/models
    or ollama list).  Falls back to static lists on failure.
    Results are cached for 30 seconds.
    """
    import time as _time
    backend = os.getenv("LLM_BACKEND", "ollama").strip().lower()
    now = _time.time()
    if _MODEL_OPTIONS_CACHE["backend"] == backend and (now - _MODEL_OPTIONS_CACHE["ts"]) < 30:
        return _MODEL_OPTIONS_CACHE["data"]

    result: list | None = None
    if backend == "litert":
        try:
            import subprocess
            r = subprocess.run(
                ["curl", "-s", "--max-time", "3", f"{LITERT_BASE_URL}/v1/models"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                import json as _json
                data = _json.loads(r.stdout)
                ids = [m["id"] for m in data.get("data", []) if "id" in m]
                if ids:
                    result = [{"value": mid, "label": {"tr": mid, "en": mid}} for mid in ids]
        except Exception:
            pass
        if result is None:
            result = LITERT_MODEL_OPTIONS

    elif backend == "ollama":
        try:
            import subprocess
            r = subprocess.run(
                ["ollama", "list"], capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                names = []
                for line in r.stdout.strip().split("\n")[1:]:
                    parts = line.split()
                    if parts:
                        names.append(parts[0])
                if names:
                    result = [{"value": n, "label": {"tr": n, "en": n}} for n in names]
        except Exception:
            pass
        if result is None:
            result = OLLAMA_MODEL_OPTIONS

    else:
        result = OLLAMA_MODEL_OPTIONS

    _MODEL_OPTIONS_CACHE["data"] = result
    _MODEL_OPTIONS_CACHE["ts"] = now
    _MODEL_OPTIONS_CACHE["backend"] = backend
    return result


# -- Settings API (for PATCH /config/settings) --
SETTINGS_SCHEMA: dict = {
    "DEFAULT_CITY":        {"type": "str",   "default": "",     "label": {"tr": "Varsayilan Sehir",          "en": "Default City"}},
    "LLM_TEMPERATURE":    {"type": "float", "default": "0.6",  "label": {"tr": "Sicaklik (Temperature)",     "en": "Temperature"},           "min": 0.0, "max": 2.0, "step": 0.05},
    "LLM_TOP_P":          {"type": "float", "default": "0.85", "label": {"tr": "Top P",                      "en": "Top P"},                  "min": 0.1, "max": 1.0, "step": 0.05},
    "LLM_TOP_K":          {"type": "int",   "default": "40",   "label": {"tr": "Top K",                      "en": "Top K"},                  "min": 1, "max": 200, "step": 1},
    "LLM_NUM_CTX":        {"type": "int",   "default": "8192", "label": {"tr": "Baglam Penceresi (Tokens)",  "en": "Context Window (Tokens)"},"min": 2048, "max": 32768, "step": 1024},
    "HISTORY_LIMIT":      {"type": "int",   "default": "12",   "label": {"tr": "Gecmis Mesaj Sayisi",        "en": "History Message Limit"},  "min": 4, "max": 50, "step": 1},
    "MEMORY_LIMIT":       {"type": "int",   "default": "10",   "label": {"tr": "Hafiza Karti Sayisi",        "en": "Memory Card Limit"},      "min": 1, "max": 30, "step": 1},
    "SUMMARY_BATCH_SIZE": {"type": "int",   "default": "5",    "label": {"tr": "Ozetleme Batch Boyutu",       "en": "Summary Batch Size"},     "min": 2, "max": 20, "step": 1},
    "LLM_MODEL":          {"type": "select", "default": "gemma4:e2b", "label": {"tr": "LLM Model",              "en": "LLM Model"}},
    "LLM_KEEP_ALIVE":     {"type": "str",   "default": "4h",   "label": {"tr": "Model Saklama Suresi",       "en": "Model Keep Alive"}},
    "ASSISTANT_USER":     {"type": "str",   "default": "",     "label": {"tr": "Kullanici Adi",              "en": "Username"}},
    "MAIL_PROVIDER":      {"type": "select", "default": "gmail", "label": {"tr": "E-posta Saglayici",        "en": "Mail Provider"}, "options": [
        {"value": "gmail", "label": {"tr": "Gmail", "en": "Gmail"}},
        {"value": "proton", "label": {"tr": "ProtonMail (ProtonBridge)", "en": "ProtonMail (ProtonBridge)"}},
        {"value": "auto", "label": {"tr": "Otomatik (Proton varsa onu kullan)", "en": "Auto (Proton if available)"}},
    ]},
    "TTS_VOICE":           {"type": "select", "default": "en_US-lessac-medium", "label": {"tr": "Ses (Piper TTS)",  "en": "Voice (Piper TTS)"}, "options": [
        {"value": "tr_TR-dfki-medium",      "label": {"tr": "Turkce — Erkek (DFKI)",       "en": "Turkish — Male (DFKI)"}},
        {"value": "en_US-lessac-medium",     "label": {"tr": "Ingilizce — Erkek (Lessac)",  "en": "English — Male (Lessac)"}},
        {"value": "en_US-amy-medium",        "label": {"tr": "Ingilizce — Kadin (Amy)",     "en": "English — Female (Amy)"}},
    ]},
    "TTS_ENGINE":          {"type": "select", "default": "piper", "label": {"tr": "Ses Motoru (TTS)", "en": "Speech Engine (TTS)"}, "options": [
        {"value": "piper",   "label": {"tr": "Piper (local, offline)",           "en": "Piper (local, offline)"}},
        {"value": "browser", "label": {"tr": "Tarayici (online, daha bircok ses)","en": "Browser (online, more voices)"}},
    ]},
    "STT_ENGINE":          {"type": "select", "default": "whisper", "label": {"tr": "Ses Motoru (STT)", "en": "Speech Engine (STT)"}, "options": [
        {"value": "gemma4",  "label": {"tr": "Gemma4 Dogrudan (duygu algilama)",  "en": "Gemma4 Native (emotion-aware)"}},
        {"value": "whisper", "label": {"tr": "Whisper (hizli, tam transkribe)",    "en": "Whisper (fast, full transcription)"}},
    ]},
    "AUTO_SEND_ON_VOICE":  {"type": "select", "default": "off", "label": {"tr": "Sesle Giri\u015fte Otomatik G\u00f6nder", "en": "Auto-Send on Voice Input"}, "options": [
        {"value": "off",  "label": {"tr": "Kapal\u0131", "en": "Off"}},
        {"value": "on",   "label": {"tr": "A\u00e7\u0131k (transkripsiyonu otomatik g\u00f6nder)", "en": "On (auto-send transcription)"}},
    ]},
    "AUTO_TTS_ON_VOICE":   {"type": "select", "default": "off", "label": {"tr": "Sesli Giri\u015fte Sesli Yan\u0131t", "en": "Auto-TTS on Voice Input"}, "options": [
        {"value": "off",  "label": {"tr": "Kapal\u0131", "en": "Off"}},
        {"value": "on",   "label": {"tr": "A\u00e7\u0131k (sesli giri\u015fse sesli yan\u0131t ver)", "en": "On (speak response if voice input)"}},
    ]},
    "INTENT_LLM_FALLBACK": {"type": "select", "default": "off", "label": {"tr": "Niyet Tespiti LLM Kullan\u0131m\u0131", "en": "Intent LLM Fallback"}, "options": [
        {"value": "off",  "label": {"tr": "Kapal\u0131 (h\u0131zl\u0131, embedding+keywords yeterli)", "en": "Off (fast, embedding+keywords)"}},
        {"value": "on",   "label": {"tr": "A\u00e7\u0131k (daha do\u011fru ama yan\u0131t +15sn gecikir)", "en": "On (more accurate, but +15s delay)"}},
    ]},
}

# Settings that require a server restart to take effect
RESTART_REQUIRED_KEYS = {"LLM_NUM_CTX", "LLM_NUM_BATCH", "INTENT_LLM_FALLBACK"}

# Settings that must NEVER be changed via the API (security-sensitive)
PROTECTED_SETTINGS = {"OLLAMA_BASE_URL", "LITERT_BASE_URL", "LLM_BACKEND", "API_KEY", "CORS_ORIGINS", "TRUSTED_HOSTS", "MEDIA_MAX_MB"}

# All integer/float config keys that should be re-synced after .env updates
_NUMERIC_KEYS = {
    "LLM_NUM_CTX": (int, 8192), "LLM_NUM_BATCH": (int, 256),
    "LLM_TEMPERATURE": (float, 0.6), "LLM_TOP_P": (float, 0.85), "LLM_TOP_K": (int, 40),
    "LLM_MAX_TOOL_ITERATIONS": (int, 5), "LLM_TIMEOUT": (int, 120),
    "HISTORY_LIMIT": (int, 12), "MEMORY_LIMIT": (int, 10),
    "SUMMARY_BATCH_SIZE": (int, 5), "SUMMARY_EARLY_TRIGGER": (int, 6),
    "WEATHER_TIMEOUT": (int, 10), "NEXTCLOUD_TIMEOUT": (int, 30),
    "IMAP_PORT": (int, 993), "SMTP_PORT": (int, 465),
    "IMAP_TIMEOUT": (int, 30), "SMTP_TIMEOUT": (int, 30),
    "PROTON_IMAP_PORT": (int, 1143), "PROTON_SMTP_PORT": (int, 1025),
    "MEMORY_SIMILARITY_THRESHOLD": (float, 0.68),
    "MEDIA_MAX_MB": (int, 100),
}


def sync_config():
    """Re-read env vars into module-level globals after a .env PATCH.

    Called by the settings API after writing new values to .env so that
    running process picks up changes without a restart.
    """
    import config as _cfg
    for key, (converter, default) in _NUMERIC_KEYS.items():
        raw = os.getenv(key)
        if raw is not None:
            try:
                setattr(_cfg, key, converter(raw))
            except (ValueError, TypeError):
                logger.warning(f"sync_config: invalid {key}={raw!r}, keeping current value")

    # Sync string settings that can change at runtime
    for key in ("LLM_BACKEND", "LLM_MODEL", "STT_ENGINE", "TTS_ENGINE", "TTS_VOICE", "AUTO_SEND_ON_VOICE", "AUTO_TTS_ON_VOICE", "INTENT_LLM_FALLBACK"):
        raw = os.getenv(key)
        if raw is not None:
            setattr(_cfg, key, raw)
