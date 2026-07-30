#!/usr/bin/env python3
"""
piSynapse Installer — offline-first personal AI assistant
Platforms: Linux, macOS, Windows (experimental)
Run with: python install.py
"""

import os, re, sys, shutil, secrets, getpass, platform, struct, subprocess
from pathlib import Path
from typing import Dict, Optional

# ── Defaults ──────────────────────────────────────────────────────────────────

VENV_DIR = ".venv"
IS_WIN = sys.platform == "win32"

# ── Terminal helpers ──────────────────────────────────────────────────────────

def _c(c: str, t: str) -> str:          return t if IS_WIN else f"{c}{t}\033[0m"
def green(t: str) -> str:                return _c("\033[0;32m", t)
def blue(t: str) -> str:                 return _c("\033[0;34m", t)
def yellow(t: str) -> str:               return _c("\033[1;33m", t)
def red(t: str) -> str:                  return _c("\033[0;31m", t)

LINE = "\u2550"
INFO_SYM = "\u2139"
OK_SYM = "\u2705"
WARN_SYM = "\u26a0"
ERR_SYM = "\u274c"

def info(m: str) -> None:               print(blue(f"  {INFO_SYM}  {m}"))
def ok(m: str) -> None:                 print(green(f"  {OK_SYM} {m}"))
def warn(m: str) -> None:               print(yellow(f"  {WARN_SYM}  {m}"))
def error(m: str) -> None:              print(red(f"  {ERR_SYM} {m}"))
def header(m: str) -> None:             print(f"\n{blue(LINE * 56)}\n  {m}\n{blue(LINE * 56)}")

def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"     {prompt}{suffix}: ").strip()
    return val or default

def ask_secret(prompt: str) -> str:
    try:
        return getpass.getpass(f"     {prompt}: ").strip()
    except Exception:
        return input(f"     {prompt} (visible): ").strip()

def ask_yesno(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    val = input(f"     {prompt} [{hint}]: ").strip().lower()
    if not val:
        return default
    return val.startswith("y")

def venv_bin(name: str) -> str:
    return os.path.join(VENV_DIR, "Scripts" if IS_WIN else "bin", f"{name}.exe" if IS_WIN else name)

def detect_shell() -> str:
    if IS_WIN:
        return "powershell" if os.environ.get("PSModulePath") else "cmd"
    n = os.path.basename(os.environ.get("SHELL", "")).lower()
    for s in ("fish", "zsh", "bash"):
        if s in n:
            return s
    return "unknown"

def activation_cmd(shell: str) -> str:
    m = {
        "fish": f"source {VENV_DIR}/bin/activate.fish",
        "bash": f"source {VENV_DIR}/bin/activate",
        "zsh":  f"source {VENV_DIR}/bin/activate",
        "unknown": f"source {VENV_DIR}/bin/activate",
        "powershell": rf"{VENV_DIR}\Scripts\Activate.ps1",
        "cmd":  rf"{VENV_DIR}\Scripts\activate.bat",
    }
    return m.get(shell, f"source {VENV_DIR}/bin/activate")


# ── Step 1: Python ────────────────────────────────────────────────────────────

def step_python() -> None:
    header("1 / 7  Python version")
    major, minor = sys.version_info[:2]
    info(f"Python {major}.{minor}")
    if (major, minor) < (3, 10):
        error("piSynapse requires Python 3.10 or newer.")
        sys.exit(1)
    ok("OK")


# ── Step 2: System dependencies ───────────────────────────────────────────────

def step_system_deps() -> None:
    header("2 / 7  System dependencies")
    missing: list[str] = []

    # ffmpeg — required for Whisper STT and audio conversion
    if shutil.which("ffmpeg"):
        ok("ffmpeg found")
    else:
        warn("ffmpeg not found (required for audio/voice)")
        if IS_WIN:
            info("Download from: https://ffmpeg.org/download.html")
        else:
            if ask_yesno("Install ffmpeg now? (sudo apt install ffmpeg)"):
                r = subprocess.run(["sudo", "apt-get", "install", "-y", "ffmpeg"])
                if r.returncode == 0:
                    ok("ffmpeg installed")
                else:
                    warn("ffmpeg install failed — install manually later")
        missing.append("ffmpeg")

    # build tools — for pip packages with native extensions
    if not IS_WIN and not shutil.which("build-essential"):
        if ask_yesno("Install build-essential (recommended for pip packages)?"):
            subprocess.run(["sudo", "apt-get", "install", "-y", "build-essential"])

    if not missing:
        ok("All system dependencies satisfied")


# ── Step 3: Virtual env + Python packages ────────────────────────────────────

def step_venv() -> None:
    header("3 / 7  Virtual environment & dependencies")

    if not os.path.exists(VENV_DIR):
        info(f"Creating {VENV_DIR}/...")
        if subprocess.run([sys.executable, "-m", "venv", VENV_DIR]).returncode != 0:
            error("Failed to create virtual environment.")
            sys.exit(1)
        ok(f"{VENV_DIR}/ created")
    else:
        ok(f"{VENV_DIR}/ already exists")

    pip = venv_bin("pip")
    info("Upgrading pip...")
    subprocess.run([pip, "install", "--quiet", "--upgrade", "pip"])

    if os.path.exists("requirements.txt"):
        info("Installing requirements.txt...")
        r = subprocess.run([pip, "install", "-r", "requirements.txt"])
        if r.returncode != 0:
            warn("pip install had issues — check output above")
        else:
            ok("Dependencies installed")
    else:
        warn("requirements.txt not found — skipping pip install")


# ── Step 4: LLM backend ──────────────────────────────────────────────────────

# HuggingFace repos for supported LiteRT-LM models
_LITERT_MODEL_REGISTRY: dict[str, tuple[str, str, str]] = {
    # model-id → (hf_repo, filename_in_repo, size_human)
    "gemma4:e2b": ("litert-community/gemma-4-E2B-it-litert-lm", "gemma-4-E2B-it.litertlm", "~2.4 GB"),
    "gemma4:e4b": ("litert-community/gemma-4-E4B-it-litert-lm", "gemma-4-E4B-it.litertlm", "~3.4 GB"),
}


def _ensure_uv() -> str | None:
    """Return path to uv binary, installing it if needed."""
    exe = shutil.which("uv")
    if exe:
        return exe
    info("uv not found — installing via pip...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--user", "uv"],
        capture_output=True, text=True,
    )
    if r.returncode == 0:
        exe = shutil.which("uv")
        if exe:
            ok("uv installed")
            return exe
    warn("uv installation failed — will try pip inside venv instead")
    return None


def _ensure_litertlm(uv_bin: str | None) -> str | None:
    """Install litert-lm if not present, return path to binary."""
    exe = shutil.which("litert-lm")
    if exe:
        ok(f"litert-lm found at {exe}")
        return exe

    info("Installing litert-lm via uv tool...")
    installer = [uv_bin, "tool", "install", "litert-lm"] if uv_bin else [sys.executable, "-m", "pip", "install", "litert-lm"]
    r = subprocess.run(installer, capture_output=True, text=True)
    if r.returncode == 0:
        exe = shutil.which("litert-lm")
        if exe:
            ok("litert-lm installed")
            return exe

    # Fallback: pip inside project venv
    info("Trying pip inside project venv...")
    pip = venv_bin("pip")
    r = subprocess.run([pip, "install", "litert-lm"], capture_output=True, text=True)
    if r.returncode == 0:
        exe = shutil.which("litert-lm")
        if exe:
            ok("litert-lm found after venv install")
            return exe
        # litert-lm may not get a CLI entrypoint in venv — create shim
        shim_path = os.path.abspath(os.path.join(VENV_DIR, "bin", "litert-lm"))
        venv_python = venv_bin("python3")
        with open(shim_path, "w") as f:
            f.write(f'#!{venv_python}\nfrom litert_lm.cli import main; main()\n')
        os.chmod(shim_path, 0o755)
        ok(f"Created shim at {shim_path}")
        return shim_path

    warn("litert-lm installation failed")
    return None


def _litert_model_imported(model_id: str) -> bool:
    """Check if a model is already imported in litert-lm's local storage."""
    r = subprocess.run(
        ["litert-lm", "list"],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode == 0:
        return model_id in r.stdout
    return False


def _litert_is_running() -> bool:
    try:
        r = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "http://localhost:9379/v1/models"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() == "200"
    except Exception:
        return False


def step_llm_backend() -> None:
    header("4 / 7  LLM backend")

    backend = ask("Choose LLM backend (litert / ollama)", "litert").strip().lower()
    while backend not in ("litert", "ollama"):
        backend = ask("Please enter 'litert' or 'ollama'", "litert").strip().lower()

    # ── LiteRT path ─────────────────────────────────────────────────────
    if backend == "litert":
        ok("Selected LiteRT LM")

        # 4a. Ensure curl (used for health checks)
        if not shutil.which("curl"):
            info("Installing curl...")
            subprocess.run(["sudo", "apt-get", "install", "-y", "curl"])
        ok("curl available")

        # 4b. Install uv + litert-lm
        uv_bin = _ensure_uv()
        litert_bin = _ensure_litertlm(uv_bin)
        if litert_bin is None:
            error("Could not install litert-lm — aborting")
            sys.exit(1)

        # 4c. Pick model
        model_id = ask("Model ID", "gemma4:e2b").strip()
        if model_id not in _LITERT_MODEL_REGISTRY:
            info(f"Unknown model {model_id!r}, will try direct import")
            hf_repo = ask("HuggingFace repo (e.g. org/repo)")
            hf_file = ask("Model filename in repo (e.g. model.litertlm)")
            reg = (hf_repo, hf_file, "unknown size")
        else:
            reg = _LITERT_MODEL_REGISTRY[model_id]
        hf_repo, hf_file, size_hint = reg

        # 4d. Import model (download from HuggingFace)
        if _litert_model_imported(model_id):
            ok(f"Model {model_id} already imported")
        else:
            info(f"Importing {model_id} from HuggingFace ({size_hint})...")
            info(f"  Repo: {hf_repo}")
            info(f"  File: {hf_file}")
            print()
            if not ask_yesno("Download now? (requires ~3 GB free disk space)"):
                info("Skipping model download — you can import later with:")
                info(f"  litert-lm import --from-huggingface-repo {hf_repo} {hf_file} {model_id}")
            else:
                r = subprocess.run([
                    "litert-lm", "import",
                    "--from-huggingface-repo", hf_repo,
                    hf_file, model_id,
                ])
                if r.returncode == 0:
                    ok(f"{model_id} imported")
                else:
                    warn(f"Import failed — try manually: litert-lm import --from-huggingface-repo {hf_repo} {hf_file} {model_id}")

        # 4e. Start LiteRT server if not running
        if _litert_is_running():
            ok("LiteRT server already running on :9379")
        else:
            info("Starting LiteRT server...")
            if shutil.which("systemctl"):
                if ask_yesno("Create & start LiteRT systemd service (auto-start on boot)?"):
                    _create_litert_service()
            else:
                litert_bin = _get_litert_bin()
                subprocess.Popen(
                    [litert_bin, "serve", "--port", "9379"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                info("LiteRT started in background — will stop when you log out")

        # 4f. Wait for server to be ready
        info("Waiting for LiteRT server to accept requests...")
        import time
        for _ in range(30):
            if _litert_is_running():
                ok("LiteRT server ready")
                break
            time.sleep(2)
        else:
            warn("LiteRT server not responding after 60s — check: systemctl status litert")

    # ── Ollama path ──────────────────────────────────────────────────────
    elif backend == "ollama":
        ok("Selected Ollama")
        if not shutil.which("ollama"):
            info("Ollama not found. Installing...")
            r = subprocess.run([
                "curl", "-fsSL", "https://ollama.com/install.sh"
            ], capture_output=True, text=True)
            if r.returncode == 0:
                subprocess.run(["sh"], input=r.stdout, text=True)
                ok("Ollama installed")
            else:
                warn("Automatic install failed — install manually: https://ollama.com")
        else:
            ok("Ollama already installed")

        model = ask("Model name", "gemma4:e2b").strip()
        info(f"Pulling {model}...")
        r = subprocess.run(["ollama", "pull", model])
        if r.returncode == 0:
            ok(f"{model} ready")
        else:
            warn(f"Pull failed — try: ollama pull {model}")


def _get_litert_bin() -> str:
    """Return the litert-lm binary path, preferring system-wide install."""
    exe = shutil.which("litert-lm")
    if exe:
        return exe
    # Fallback to venv shim
    shim = os.path.abspath(os.path.join(VENV_DIR, "bin", "litert-lm"))
    if os.path.isfile(shim) and os.access(shim, os.X_OK):
        return shim
    return "litert-lm"


def _create_litert_service() -> None:
    """Create a systemd unit for litert-lm serve."""
    if not shutil.which("systemctl"):
        warn("systemctl not found — skipping LiteRT systemd service")
        return

    user = os.environ.get("SUDO_USER") or os.environ.get("USER") or "pi"
    litert_bin = _get_litert_bin()
    # litert-lm stores models in the user's home
    user_home = os.path.expanduser(f"~{user}")

    unit = f"""[Unit]
Description=LiteRT-LM API Server (piSynapse backend)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
Environment=HOME={user_home}
ExecStart={litert_bin} serve --port 9379
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    try:
        tmp = Path("/tmp/litert.service")
        tmp.write_text(unit, encoding="utf-8")
        subprocess.run(["sudo", "cp", str(tmp), "/etc/systemd/system/litert.service"], check=True)
        subprocess.run(["sudo", "systemctl", "daemon-reload"], capture_output=True)
        subprocess.run(["sudo", "systemctl", "enable", "litert"], capture_output=True)
        subprocess.run(["sudo", "systemctl", "start", "litert"])
        ok("litert.service created and started")
    except Exception as e:
        warn(f"Could not create litert systemd service: {e}")
        info(f"Start manually: {litert_bin} serve --port 9379")


# ── Step 5: Piper TTS voices ─────────────────────────────────────────────────

PIPER_VOICES = {
    "tr_TR-dfki-medium":   "rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/tr_TR-dfki-medium",
    "en_US-lessac-medium": "rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium",
    "en_US-amy-medium":    "rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium",
}

def step_tts_voices() -> None:
    header("5 / 7  Piper TTS voices")

    if not shutil.which("ffmpeg"):
        warn("ffmpeg not installed — TTS output may not play in browser")

    base_url = "https://huggingface.co"
    piper_dir = os.path.join("models", "piper")
    os.makedirs(piper_dir, exist_ok=True)

    existing = [f for f in os.listdir(piper_dir) if f.endswith(".onnx")] if os.path.isdir(piper_dir) else []
    if existing:
        ok(f"Found {len(existing)} voice(s) in models/piper/")

    for name, hf_path in PIPER_VOICES.items():
        onnx_dest = os.path.join(piper_dir, f"{name}.onnx")
        json_dest = os.path.join(piper_dir, f"{name}.onnx.json")

        if os.path.exists(onnx_dest) and os.path.exists(json_dest):
            ok(f"{name} ready")
            continue

        dl = ask_yesno(f"Download Piper voice '{name}'? (~60 MB)", default=False)
        if not dl:
            info(f"Skipping {name}")
            continue

        for ext, label in [(".onnx", "model"), (".onnx.json", "config")]:
            dest = onnx_dest if ext == ".onnx" else json_dest
            url = f"{base_url}/{hf_path}{ext}"
            info(f"  Downloading {label} ({ext})...")
            r = subprocess.run(["curl", "-fSL", "-o", dest, url], capture_output=True)
            if r.returncode == 0:
                ok(f"  {name}{ext}")
            else:
                warn(f"  Failed to download {name}{ext}")

    # Confirm at least one voice is available
    voices_found = [f for f in os.listdir(piper_dir) if f.endswith(".onnx")] if os.path.isdir(piper_dir) else []
    if voices_found:
        ok(f"TTS voices available: {', '.join(v.replace('.onnx', '') for v in voices_found)}")
    else:
        warn("No voices downloaded — TTS will not work (you can download later)")


# ── Step 6: Environment configuration ─────────────────────────────────────────

_ENV_TEMPLATE = """# ============================================================
# piSynapse — Environment Configuration
# Auto-generated by install.py
# ============================================================

# --- LLM Backend ---
# "litert"  — LiteRT-LM (OpenAI-compatible, recommended)
# "ollama"  — Ollama server
LLM_BACKEND={LLM_BACKEND}

# --- LLM URLs ---
OLLAMA_BASE_URL=http://localhost:11434
LITERT_BASE_URL=http://localhost:9379

# --- Model ---
LLM_MODEL={LLM_MODEL}
LLM_NUM_CTX=8192
LLM_NUM_BATCH=256
LLM_TEMPERATURE=0.6
LLM_TOP_P=0.85
LLM_TOP_K=40
LLM_KEEP_ALIVE=4h
LLM_TIMEOUT=120
LLM_MAX_TOOL_ITERATIONS=5

# --- Embedding ---
EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

# --- Memory ---
MEMORY_SIMILARITY_THRESHOLD=0.68
HISTORY_LIMIT=12
MEMORY_LIMIT=10
SUMMARY_BATCH_SIZE=5
SUMMARY_EARLY_TRIGGER=6

# --- Database ---
DB_PATH=assistant.db

# --- Weather ---
DEFAULT_CITY={DEFAULT_CITY}
WEATHER_TIMEOUT=10

# --- Nextcloud (optional) ---
NEXTCLOUD_URL={NEXTCLOUD_URL}
NEXTCLOUD_USER={NEXTCLOUD_USER}
NEXTCLOUD_PASSWORD={NEXTCLOUD_PASSWORD}
NEXTCLOUD_TIMEOUT=30

# --- Email Provider ---
# "gmail"   — Gmail with App Password
# "proton"  — ProtonMail via ProtonBridge (bridge must be running)
# Leave empty to disable email
MAIL_PROVIDER={MAIL_PROVIDER}

# --- Gmail (optional — only if MAIL_PROVIDER=gmail) ---
GMAIL_USER={GMAIL_USER}
GMAIL_APP_PASSWORD={GMAIL_APP_PASSWORD}
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465

# --- ProtonMail / ProtonBridge (optional — only if MAIL_PROVIDER=proton) ---
PROTON_USER={PROTON_USER}
PROTON_PASSWORD={PROTON_PASSWORD}
PROTON_IMAP_HOST=localhost
PROTON_IMAP_PORT=1143
PROTON_SMTP_HOST=localhost
PROTON_SMTP_PORT=1025

# --- Timeouts ---
IMAP_TIMEOUT=30
SMTP_TIMEOUT=30

# --- Piper TTS ---
TTS_VOICE={TTS_VOICE}
TTS_ENGINE={TTS_ENGINE}

# --- Security ---
API_KEY={API_KEY}
CORS_ORIGINS=
TRUSTED_HOSTS=*
MEDIA_MAX_MB=100

# --- STT ---
STT_ENGINE={STT_ENGINE}

# --- Voice Input Behavior ---
AUTO_SEND_ON_VOICE={AUTO_SEND_ON_VOICE}
AUTO_TTS_ON_VOICE={AUTO_TTS_ON_VOICE}

# --- Intent ---
INTENT_LLM_FALLBACK=off

# --- Personalization ---
ASSISTANT_USER={ASSISTANT_USER}
"""


def _read_current_env() -> dict[str, str]:
    """Read existing .env into a dict, preserving only 'key=value' lines."""
    env_path = Path(".env")
    if not env_path.exists():
        return {}
    result: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def step_env() -> None:
    header("6 / 7  Environment configuration")

    env_path = Path(".env")
    current = _read_current_env()

    info("You will now be asked a few questions. Press Enter to accept the default.\n")

    # Auto-generate API key
    existing_key = current.get("API_KEY", "")
    if not existing_key:
        existing_key = secrets.token_urlsafe(32)
        info(f"Generated API key: {existing_key}")

    # Backend + model
    llm_backend = ask("LLM backend (litert / ollama)", current.get("LLM_BACKEND", "litert"))
    llm_model = ask("Model name", current.get("LLM_MODEL", "gemma4:e2b"))

    # Personalization
    assistant_user = ask("Your name", current.get("ASSISTANT_USER", "default"))
    default_city = ask("Default city for weather", current.get("DEFAULT_CITY", "Istanbul"))

    # Mail provider with guided prompts
    mail_provider = ask("Mail provider (gmail / proton / none)", current.get("MAIL_PROVIDER", "none")).lower()
    if mail_provider not in ("gmail", "proton", "none"):
        mail_provider = "none"

    gmail_user = current.get("GMAIL_USER", "")
    gmail_pass = current.get("GMAIL_APP_PASSWORD", "")
    proton_user = current.get("PROTON_USER", "")
    proton_pass = current.get("PROTON_PASSWORD", "")

    if mail_provider == "gmail":
        info("Gmail requires an App Password. Generate one at:")
        info("  https://myaccount.google.com/apppasswords")
        gmail_user = ask("Gmail address", gmail_user)
        raw = ask_secret("Gmail App Password (16 chars, no spaces)")
        gmail_pass = raw.replace(" ", "").replace("-", "") if raw else gmail_pass
    elif mail_provider == "proton":
        info("ProtonMail requires ProtonBridge running locally.")
        info("Install from: https://proton.me/mail/bridge")
        proton_user = ask("ProtonMail address", proton_user)
        proton_pass = ask_secret("ProtonBridge password", proton_pass)

    # Nextcloud
    nc_url = ask("Nextcloud URL (e.g. https://cloud.example.com)", current.get("NEXTCLOUD_URL", ""))
    nc_user = ask("Nextcloud username", current.get("NEXTCLOUD_USER", ""))
    nc_pass = ask_secret("Nextcloud app password") if nc_url else current.get("NEXTCLOUD_PASSWORD", "")

    # Voice
    stt = ask("STT engine (whisper / gemma4)", current.get("STT_ENGINE", "whisper"))
    tts_engine = ask("TTS engine (piper / browser)", current.get("TTS_ENGINE", "piper"))
    tts_voice = ask("TTS voice (en_US-lessac-medium / tr_TR-dfki-medium / en_US-amy-medium)",
                    current.get("TTS_VOICE", "en_US-lessac-medium"))
    auto_send = ask("Auto-send after voice transcription? (on/off)", current.get("AUTO_SEND_ON_VOICE", "off"))
    auto_tts = ask("Auto-speak response when input was voice? (on/off)", current.get("AUTO_TTS_ON_VOICE", "off"))

    # Build values dict
    values = {
        "LLM_BACKEND":        llm_backend,
        "LLM_MODEL":          llm_model,
        "DEFAULT_CITY":       default_city or "",
        "ASSISTANT_USER":     assistant_user,
        "API_KEY":            existing_key,
        "MAIL_PROVIDER":      mail_provider if mail_provider != "none" else "",
        "GMAIL_USER":         gmail_user,
        "GMAIL_APP_PASSWORD": gmail_pass,
        "PROTON_USER":        proton_user,
        "PROTON_PASSWORD":    proton_pass,
        "NEXTCLOUD_URL":      nc_url,
        "NEXTCLOUD_USER":     nc_user,
        "NEXTCLOUD_PASSWORD": nc_pass,
        "STT_ENGINE":         stt,
        "TTS_ENGINE":         tts_engine,
        "TTS_VOICE":          tts_voice,
        "AUTO_SEND_ON_VOICE": auto_send if auto_send in ("on", "off") else "off",
        "AUTO_TTS_ON_VOICE":  auto_tts if auto_tts in ("on", "off") else "off",
    }

    # Preserve any existing values not asked above
    preserved_keys = {
        "OLLAMA_BASE_URL", "LITERT_BASE_URL", "LLM_NUM_CTX", "LLM_NUM_BATCH",
        "LLM_TEMPERATURE", "LLM_TOP_P", "LLM_TOP_K", "LLM_KEEP_ALIVE", "LLM_TIMEOUT",
        "LLM_MAX_TOOL_ITERATIONS", "EMBED_MODEL", "MEMORY_SIMILARITY_THRESHOLD",
        "HISTORY_LIMIT", "MEMORY_LIMIT", "SUMMARY_BATCH_SIZE", "SUMMARY_EARLY_TRIGGER",
        "DB_PATH", "WEATHER_TIMEOUT", "NEXTCLOUD_TIMEOUT",
        "IMAP_HOST", "IMAP_PORT", "SMTP_HOST", "SMTP_PORT",
        "PROTON_IMAP_HOST", "PROTON_IMAP_PORT", "PROTON_SMTP_HOST", "PROTON_SMTP_PORT",
        "IMAP_TIMEOUT", "SMTP_TIMEOUT", "CORS_ORIGINS", "TRUSTED_HOSTS", "MEDIA_MAX_MB",
        "INTENT_LLM_FALLBACK",
    }
    for k in preserved_keys:
        v = current.get(k)
        if v:
            values[k] = v

    # Render template, then apply preserved values
    content = _ENV_TEMPLATE.format(**values)
    for k, v in values.items():
        pattern = rf"^{re.escape(k)}=.*$"
        replacement = f"{k}={v}"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    env_path.write_text(content.strip() + "\n", encoding="utf-8")
    ok(".env created / updated")


# ── Step 7: systemd service (Linux only) ──────────────────────────────────────

def step_systemd() -> None:
    if IS_WIN or sys.platform == "darwin":
        return

    header("7 / 7  Systemd service (optional)")

    if not shutil.which("systemctl"):
        info("systemctl not found — skipping systemd setup")
        return

    if ask_yesno("Create a systemd service to start piSynapse on boot?"):
        user = os.environ.get("SUDO_USER") or os.environ.get("USER") or "pi"
        home = os.path.expanduser(f"~{user}")
        project_dir = os.path.abspath(".")
        python_path = os.path.join(project_dir, VENV_DIR, "bin", "python3")
        uvicorn_path = os.path.join(project_dir, VENV_DIR, "bin", "uvicorn")
        wants_litert = os.path.exists("/etc/systemd/system/litert.service")

        unit = f"""[Unit]
Description=piSynapse AI Assistant
After=network-online.target{" litert.service" if wants_litert else ""}
Wants=network-online.target{" litert.service" if wants_litert else ""}

[Service]
Type=simple
User={user}
WorkingDirectory={project_dir}
Environment=PATH={os.path.join(project_dir, VENV_DIR, "bin")}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart={uvicorn_path} main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        service_path = Path(f"/etc/systemd/system/pisynapse.service")
        try:
            # Write via temp file to avoid permission issues
            tmp = Path("/tmp/pisynapse.service")
            tmp.write_text(unit, encoding="utf-8")
            subprocess.run(["sudo", "cp", str(tmp), str(service_path)], check=True)
            subprocess.run(["sudo", "systemctl", "daemon-reload"], capture_output=True)
            ok("systemd service created: pisynapse.service")

            if ask_yesno("Enable and start the service now?"):
                subprocess.run(["sudo", "systemctl", "enable", "pisynapse"], capture_output=True)
                subprocess.run(["sudo", "systemctl", "start", "pisynapse"])
                ok("piSynapse started — check status: systemctl status pisynapse")
        except Exception as e:
            warn(f"Could not create service: {e}")
            info("Manual setup: see README.md for systemd instructions")
    else:
        info("Skipping systemd setup")


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary() -> None:
    shell = detect_shell()
    activate = activation_cmd(shell)
    run_cmd = f"{venv_bin('uvicorn')} main:app --host 0.0.0.0 --port 8000"

    api_key = ""
    try:
        for line in Path(".env").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("API_KEY=") and "=" in line:
                api_key = line.split("=", 1)[1].strip()
                break
    except Exception:
        pass

    print(f"\n{green(LINE * 56)}")
    print(green(f"  {OK_SYM} Installation complete!"))
    print(green(LINE * 56))
    print(f"\n  {'Shell':12s}: {shell}")
    print(f"  {'Model':12s}: {os.environ.get('LLM_MODEL', 'gemma4:e2b')}")
    litert_service = os.path.exists("/etc/systemd/system/litert.service")
    pisynapse_service = os.path.exists("/etc/systemd/system/pisynapse.service")
    if litert_service:
        print(f"  {'LiteRT':12s}: systemd (active)")
    if pisynapse_service:
        print(f"  {'piSynapse':12s}: systemd (active)")
    if api_key:
        print(f"  {'API Key':12s}: {api_key}")
    print(f"\n  Activate:")
    print(f"    {activate}")
    print(f"\n  Start piSynapse:")
    print(f"    {run_cmd}")
    print(f"\n  Open http://localhost:8000 in your browser.")
    if api_key:
        print(f"  Enter your API key when prompted.\n")
    if litert_service or pisynapse_service:
        print(f"  {'Manage':12s}: systemctl status litert pisynapse\n")


# ── Entry ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print(blue("\n  piSynapse Installer\n"))

    # Verify we're in the project root
    if not os.path.isfile("main.py"):
        error("main.py not found — run this script from the piSynapse project directory.")
        sys.exit(1)

    step_python()
    step_system_deps()
    step_venv()
    step_llm_backend()
    step_tts_voices()
    step_env()
    step_systemd()
    print_summary()


if __name__ == "__main__":
    main()
