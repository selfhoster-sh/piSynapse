"""Settings CRUD: GET/PATCH settings, type validation, .env persistence."""
import logging
import os

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False
    fcntl = None  # type: ignore[assignment]
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import ENV_PATH, PROTECTED_SETTINGS, RESTART_REQUIRED_KEYS, SETTINGS_SCHEMA, get, get_llm_model_options

logger = logging.getLogger("piSynapse")

router = APIRouter(prefix="/config", tags=["config"])


@router.get("")
async def get_config():
    """Returns .env configurations needed by the UI on startup."""
    return {
        # Empty when unset — the UI falls back to a localized "You" label
        # instead of ever displaying a placeholder like "User"/"default".
        "username": (get("ASSISTANT_USER") or "").strip(),
        "default_city": get("DEFAULT_CITY", ""),
        "model": get("LLM_MODEL", "gemma4-e2b"),
        "llm_backend": get("LLM_BACKEND", "litert"),
        "stt_engine": get("STT_ENGINE", "whisper"),
        "tts_engine": get("TTS_ENGINE", "piper"),
        "auto_send_on_voice": get("AUTO_SEND_ON_VOICE", "off"),
        "auto_tts_on_voice": get("AUTO_TTS_ON_VOICE", "off"),
        "llm_title_enrichment": get("LLM_TITLE_ENRICHMENT", "on"),
    }


@router.get("/settings")
async def get_settings():
    result = {}
    for key, schema in SETTINGS_SCHEMA.items():
        entry = {"value": os.getenv(key, schema["default"]), "type": schema["type"], "label": schema.get("label", {})}
        if key == "LLM_MODEL":
            entry["options"] = await get_llm_model_options()
            # Normalize value to match backend format so dropdown shows correct selection
            backend = (os.getenv("LLM_BACKEND") or "litert").strip().lower()
            current = entry["value"]
            normalized = current.replace(":", "-") if backend == "litert" else current
            if normalized != current:
                entry["value"] = normalized
        elif "options" in schema:
            entry["options"] = schema["options"]
        if "min" in schema:
            entry["min"] = schema["min"]
        if "max" in schema:
            entry["max"] = schema["max"]
        if "step" in schema:
            entry["step"] = schema["step"]
        if "desc" in schema:
            entry["desc"] = schema["desc"]
        result[key] = entry
    return result


class SettingsUpdate(BaseModel):
    values: dict[str, str]


@router.patch("/settings")
async def update_settings(body: SettingsUpdate):
    if not ENV_PATH.exists():
        raise HTTPException(status_code=500, detail=".env file not found")

    updated_keys: list[str] = []

    # Backend switch in the same request? Model validation and auto-mapping
    # must target the NEW backend's daemon, not the currently running one.
    current_backend = (os.getenv("LLM_BACKEND") or "litert").strip().lower()
    new_backend = None
    if "LLM_BACKEND" in body.values:
        candidate = body.values["LLM_BACKEND"].strip().lower()
        if candidate != current_backend:
            new_backend = candidate

    # Validate + apply each value to os.environ
    validated: dict[str, str] = {}
    for key, value in body.values.items():
        if key not in SETTINGS_SCHEMA or key in PROTECTED_SETTINGS:
            continue
        schema = SETTINGS_SCHEMA[key]
        try:
            if schema["type"] == "int":
                value = str(int(float(value)))
            elif schema["type"] == "float":
                value = str(float(value))
            elif schema["type"] == "select":
                allowed = [o["value"] for o in schema.get("options", [])]
                if key == "LLM_MODEL":
                    allowed = [o["value"] for o in await get_llm_model_options(new_backend or current_backend)]
                if allowed and value not in allowed:
                    raise HTTPException(status_code=400, detail=f"Invalid option for {key}: {value}. Allowed: {allowed}")
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail=f"Invalid value for {key}: {value}")
        if "min" in schema and schema["type"] in ("int", "float") and float(value) < schema["min"]:
            raise HTTPException(status_code=400, detail=f"{key} must be >= {schema['min']}")
        if "max" in schema and schema["type"] in ("int", "float") and float(value) > schema["max"]:
            raise HTTPException(status_code=400, detail=f"{key} must be <= {schema['max']}")
        # Never allow line breaks: a "\n" in a value could inject a new
        # key=value line into .env on the next read.
        if "\n" in value or "\r" in value:
            raise HTTPException(status_code=400, detail=f"Invalid value for {key}: newlines are not allowed")
        validated[key] = value
        updated_keys.append(key)

    # All values validated OK — only now mutate the running process.
    # Applying os.environ inside the loop would leave a partial update if a
    # later key raised HTTPException (os.environ changed, .env + module
    # attributes stale → three-way divergence).
    if new_backend and "LLM_MODEL" not in validated:
        # Auto-map the current model to the new backend's registry by
        # separator-insensitive match (litert "gemma4-e2b" ↔ ollama
        # "gemma4:e2b"). Without this, switching backends leaves the old
        # model id in place and every LLM call 404s on the new daemon.
        old_model = os.getenv("LLM_MODEL", "")
        try:
            options = await get_llm_model_options(new_backend)

            def norm(s: str) -> str:
                return s.replace(":", "-").strip().lower()

            match = next((o["value"] for o in options if norm(o["value"]) == norm(old_model)), None)
            if match:
                validated["LLM_MODEL"] = match
                updated_keys.append("LLM_MODEL")
                logger.info(f"Backend switch {current_backend}→{new_backend}: mapped LLM_MODEL {old_model!r} → {match!r}")
            else:
                logger.warning(
                    f"Backend switch {current_backend}→{new_backend}: no equivalent "
                    f"model for {old_model!r} — manual model selection required"
                )
        except Exception as e:
            logger.warning(f"Backend switch: model auto-map failed ({e}) — keeping {old_model!r}")

    for key, value in validated.items():
        os.environ[key] = value

    # Read .env, modify, then write back
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    for key, value in validated.items():
        found = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                lines[i] = f"{key}={value}"
                found = True
                break
        if not found:
            lines.append(f"{key}={value}")

    new_content = "\n".join(lines) + "\n"

    if _HAS_FCNTL:
        with open(ENV_PATH, "r+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                f.truncate()
                f.write(new_content)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    else:
        logger.warning("fcntl not available (Windows?) — .env writes are not file-locked")
        ENV_PATH.write_text(new_content, encoding="utf-8")

    # Sync numeric config values into running process (avoids restart)
    from config import sync_config
    sync_config()

    restart_keys = [k for k in updated_keys if k in RESTART_REQUIRED_KEYS]
    return {"ok": True, "updated": updated_keys, "restart_required": restart_keys}
