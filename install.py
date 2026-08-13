#!/usr/bin/env python3
"""piSynapse Installer — offline-first personal AI assistant.
Platforms: Linux, macOS, Windows (experimental).
Run with: python install.py

Flow:
  1. Python version check
  2. System dependencies (ffmpeg, curl)
  3. Virtual environment + pip packages
  4. LLM backend (LiteRT-LM or Ollama) + model + server start
  5. Piper TTS voices (optional)
  6. Environment configuration (.env auto-generated)
  7. systemd service (Linux only, optional)
"""

import getpass
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

# ── Defaults ──────────────────────────────────────────────────────────────────

VENV_DIR = ".venv"
LITERT_PORT = 9379
IS_WIN = sys.platform == "win32"

# Shared state passed between steps so no question is asked twice.
STATE: dict = {}


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

def menu(title: str, options: list[tuple[str, str]], default: int = 1) -> int:
    """Numbered choice menu. options = [(label, description)]. Returns 1-based index."""
    print(f"\n  {title}")
    for i, (label, desc) in enumerate(options, 1):
        line = f"    {i}) {label}"
        if desc:
            line += f"  —  {desc}"
        print(line)
    val = input(f"  Choose [1-{len(options)}] (default {default}): ").strip()
    if not val:
        return default
    try:
        idx = int(val)
    except ValueError:
        idx = 0
    if not (1 <= idx <= len(options)):
        warn(f"Invalid choice '{val}' — using option {default}.")
        return default
    return idx

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

    if shutil.which("ffmpeg"):
        ok("ffmpeg found")
    else:
        warn("ffmpeg not found (required for audio/voice)")
        if IS_WIN:
            info("Download from: https://ffmpeg.org/download.html")
        elif sys.platform == "darwin":
            info("Install with: brew install ffmpeg")
        else:
            if ask_yesno("Install ffmpeg now? (sudo apt install ffmpeg)"):
                r = subprocess.run(["sudo", "apt-get", "install", "-y", "ffmpeg"])
                if r.returncode == 0:
                    ok("ffmpeg installed")
                else:
                    warn("ffmpeg install failed — install manually later")
                    missing.append("ffmpeg")
            else:
                missing.append("ffmpeg")

    if not shutil.which("curl"):
        warn("curl not found (needed for model downloads and health checks)")
        if not IS_WIN:
            subprocess.run(["sudo", "apt-get", "install", "-y", "curl"])
            if shutil.which("curl"):
                ok("curl installed")
            else:
                missing.append("curl")
        else:
            missing.append("curl")

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

# piSynapse model name → (HuggingFace repo, filename, size hint).
# NOTE: litert-lm imports with the model ID the app will request. The app sends
# LLM_MODEL with ':' replaced by '-', so the import ID MUST use dashes.
_LITERT_MODEL_REGISTRY: dict[str, tuple[str, str, str]] = {
    "gemma4:e2b": ("litert-community/gemma-4-E2B-it-litert-lm", "gemma-4-E2B-it.litertlm", "~2.4 GB"),
    "gemma4:e4b": ("litert-community/gemma-4-E4B-it-litert-lm", "gemma-4-E4B-it.litertlm", "~3.4 GB"),
}

_OLLAMA_MODELS = ["gemma4:e2b", "gemma4:e4b"]


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess with live output (for downloads/progress bars)."""
    return subprocess.run(cmd, **kwargs)


def _ensure_uv() -> str | None:
    """Return uv binary path, installing it if needed."""
    exe = shutil.which("uv")
    if exe:
        return exe
    info("uv not found — installing...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--user", "--quiet", "uv"],
        capture_output=True, text=True,
    )
    exe = shutil.which("uv")
    if r.returncode == 0 and exe:
        ok("uv installed")
        return exe
    # uv tool may not be on PATH for this session (e.g. ~/.local/bin not in PATH).
    for candidate in (
        os.path.expanduser("~/.local/bin/uv"),
        os.path.expanduser("~/Library/Python/*/bin/uv"),
    ):
        hits = sorted(Path(os.path.dirname(candidate)).glob("uv")) if "*" in candidate else [Path(candidate)]
        for hit in hits:
            if hit.is_file() and os.access(hit, os.X_OK):
                ok(f"uv found at {hit}")
                return str(hit)
    warn("uv not found — will install litert-lm with pip instead")
    return None


def _find_litert_bin() -> str | None:
    """Locate the litert-lm executable across platforms."""
    exe = shutil.which("litert-lm")
    if exe:
        return exe
    candidates = [
        os.path.expanduser("~/.local/bin/litert-lm"),
        os.path.expanduser("~/Library/Python/3.*/bin/litert-lm"),
        os.path.abspath(os.path.join(VENV_DIR, "Scripts" if IS_WIN else "bin", "litert-lm")),
    ]
    for pattern in candidates:
        hits = sorted(Path(os.path.dirname(pattern)).glob(os.path.basename(pattern))) if "*" in pattern else [Path(pattern)]
        for hit in hits:
            if hit.is_file() and os.access(hit, os.X_OK):
                return str(hit)
    return None


def _install_litertlm(uv_bin: str | None) -> str | None:
    """Install litert-lm and return its binary path, or None on failure."""
    existing = _find_litert_bin()
    if existing:
        ok(f"litert-lm found at {existing}")
        return existing

    info("Installing litert-lm (official LiteRT-LM CLI, ~64 kB)...")
    if uv_bin:
        r = subprocess.run([uv_bin, "tool", "install", "litert-lm"], capture_output=True, text=True)
        if r.returncode == 0:
            exe = _find_litert_bin()
            if exe:
                ok("litert-lm installed (uv)")
                return exe
        warn(f"uv tool install failed: {r.stderr.strip()[-300:]}")

    info("Falling back to pip install litert-lm...")
    pip = venv_bin("pip")
    r = subprocess.run([pip, "install", "--quiet", "litert-lm"], capture_output=True, text=True)
    if r.returncode == 0:
        exe = _find_litert_bin()
        if exe:
            ok("litert-lm installed (pip)")
            return exe
        # No console entrypoint found — create a shim inside the venv.
        shim_path = os.path.abspath(os.path.join(VENV_DIR, "bin", "litert-lm"))
        venv_python = venv_bin("python3")
        with open(shim_path, "w") as f:
            f.write(f'#!{venv_python}\nfrom litert_lm.cli import main; main()\n')
        os.chmod(shim_path, 0o755)
        ok(f"Created shim at {shim_path}")
        return shim_path

    error(f"Could not install litert-lm: {r.stderr.strip()[-300:]}")
    error("Install it manually with:  uv tool install litert-lm   (or: pip install litert-lm)")
    return None


def _litert_model_imported(import_id: str) -> bool:
    """Check whether a model is already in litert-lm's local registry."""
    r = subprocess.run(["litert-lm", "list"], capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        return False
    return any(line.strip().startswith(import_id) for line in r.stdout.splitlines())


def _litert_is_running() -> bool:
    try:
        r = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             f"http://localhost:{LITERT_PORT}/v1/models"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() == "200"
    except Exception:
        return False


def _start_litert_server(litert_bin: str) -> bool:
    """Start the LiteRT server and wait until it accepts requests."""
    if _litert_is_running():
        ok(f"LiteRT server already running on :{LITERT_PORT}")
        return True

    # Linux with systemd → proper service (auto-start on boot).
    if shutil.which("systemctl"):
        if ask_yesno("Create & start LiteRT systemd service (auto-start on boot)?"):
            if _create_litert_service():
                return _wait_litert_ready()
            return False
    elif ask_yesno(f"Start LiteRT server now on port {LITERT_PORT}?"):
        pass
    else:
        info("Skipping server start. Start it later with:")
        info(f"  {litert_bin} serve --host 0.0.0.0 --port {LITERT_PORT}")
        return False

    info(f"Starting LiteRT server on :{LITERT_PORT}...")
    log_path = os.path.abspath("litert-server.log")
    logf = open(log_path, "ab")
    try:
        subprocess.Popen(
            [litert_bin, "serve", "--host", "0.0.0.0", "--port", str(LITERT_PORT)],
            stdout=logf, stderr=logf, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        error(f"Could not start LiteRT server: {e}")
        return False
    ok(f"Server starting — logs: {log_path}")
    return _wait_litert_ready()


def _wait_litert_ready(timeout_s: int = 120) -> bool:
    """Poll the LiteRT health endpoint until it responds or times out."""
    import time
    info(f"Waiting for LiteRT server on :{LITERT_PORT}...")
    for _ in range(timeout_s // 2):
        if _litert_is_running():
            ok("LiteRT server is ready")
            return True
        time.sleep(2)
    warn(f"LiteRT server did not respond after {timeout_s}s.")
    warn("Check the log: cat litert-server.log")
    warn("Check the model: litert-lm list")
    return False


def _create_litert_service() -> bool:
    """Create a systemd unit for litert-lm serve."""
    if not shutil.which("systemctl"):
        warn("systemctl not found — skipping systemd service")
        return False

    user = os.environ.get("SUDO_USER") or os.environ.get("USER") or "pi"
    litert_bin = _find_litert_bin() or "litert-lm"
    user_home = os.path.expanduser(f"~{user}")

    unit = f"""[Unit]
Description=LiteRT-LM API Server (piSynapse backend)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
Environment=HOME={user_home}
ExecStart={litert_bin} serve --host 0.0.0.0 --port {LITERT_PORT}
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
        return True
    except Exception as e:
        warn(f"Could not create litert systemd service: {e}")
        return False


def step_llm_backend() -> None:
    header("4 / 7  LLM backend")

    backend_idx = menu("Choose LLM backend:", [
        ("LiteRT-LM", "Recommended — faster and uses less RAM on ARM/Apple Silicon"),
        ("Ollama", "x86 desktop favorite, needs more RAM"),
    ])
    backend = "litert" if backend_idx == 1 else "ollama"
    STATE["backend"] = backend

    # ── Model selection ───────────────────────────────────────────────────
    if backend == "litert":
        model_idx = menu("Choose model:", [
            ("gemma4:e2b  (~2.4 GB)", "Recommended — fits in 8 GB RAM"),
            ("gemma4:e4b  (~3.4 GB)", "Higher quality — needs 16 GB+ RAM"),
        ])
        model_id = "gemma4:e2b" if model_idx == 1 else "gemma4:e4b"
    else:
        model_idx = menu("Choose model:", [
            ("gemma4:e2b  (~2.4 GB)", "Recommended — fits in 8 GB RAM"),
            ("gemma4:e4b  (~3.4 GB)", "Higher quality — needs 16 GB+ RAM"),
        ])
        model_id = _OLLAMA_MODELS[model_idx - 1]
    STATE["model"] = model_id
    ok(f"Selected {backend} / {model_id}")

    # ── LiteRT path ───────────────────────────────────────────────────────
    if backend == "litert":
        # Install litert-lm CLI (system-wide via uv, independent of the venv).
        uv_bin = _ensure_uv()
        litert_bin = _install_litertlm(uv_bin)
        if litert_bin is None:
            error("Aborting — litert-lm must be installed to continue.")
            sys.exit(1)

        # Import the model into the local registry if not present.
        import_id = model_id.replace(":", "-")          # app requests gemma4-e2b
        if _litert_model_imported(import_id):
            ok(f"Model '{import_id}' already imported")
        else:
            hf_repo, hf_file, size_hint = _LITERT_MODEL_REGISTRY[model_id]
            info(f"Downloading {model_id} from HuggingFace ({size_hint})...")
            info(f"  repo: {hf_repo}")
            print()
            r = _run([
                litert_bin, "import",
                f"--from-huggingface-repo={hf_repo}",
                hf_file, import_id,
            ])
            if r.returncode != 0:
                warn("Import failed — retry later with:")
                warn(f"  {litert_bin} import --from-huggingface-repo={hf_repo} {hf_file} {import_id}")
            else:
                ok(f"Model imported as '{import_id}'")

        # Verify the registry, then start the server.
        ok("Imported models:")
        subprocess.run([litert_bin, "list"])
        _start_litert_server(litert_bin)

    # ── Ollama path ───────────────────────────────────────────────────────
    else:
        if not shutil.which("ollama"):
            info("Ollama not found. Installing...")
            if IS_WIN:
                info("Download from: https://ollama.com/download")
                info("Then run this installer again.")
                sys.exit(1)
            r = subprocess.run(["curl", "-fsSL", "https://ollama.com/install.sh"], capture_output=True, text=True)
            if r.returncode == 0:
                subprocess.run(["sh"], input=r.stdout, text=True)
                ok("Ollama installed")
            else:
                warn("Automatic install failed — install manually: https://ollama.com")
        else:
            ok("Ollama already installed")

        info(f"Pulling {model_id}...")
        r = _run(["ollama", "pull", model_id])
        if r.returncode == 0:
            ok(f"{model_id} ready")
        else:
            warn(f"Pull failed — try: ollama pull {model_id}")

        # Make sure Ollama server is running.
        if not shutil.which("systemctl"):
            if not _ollama_is_running():
                info("Starting Ollama server...")
                subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        import time
        for _ in range(15):
            if _ollama_is_running():
                ok("Ollama server is ready")
                break
            time.sleep(2)


def _ollama_is_running() -> bool:
    try:
        r = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "http://localhost:11434"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() == "200"
    except Exception:
        return False


# ── Step 5: Piper TTS voices ─────────────────────────────────────────────────

PIPER_VOICES = {
    "en_US-lessac-medium":   "rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium",
    "tr_TR-dfki-medium":     "rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/tr_TR-dfki-medium",
    "en_US-amy-medium":      "rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium",
}


def _download_piper_voice(name: str, hf_path: str) -> bool:
    """Download one Piper voice (.onnx + config). Returns True on success."""
    base_url = "https://huggingface.co"
    piper_dir = os.path.join("models", "piper")
    os.makedirs(piper_dir, exist_ok=True)
    ok_flag = True
    for ext, label in [(".onnx", "model"), (".onnx.json", "config")]:
        dest = os.path.join(piper_dir, f"{name}{ext}")
        if os.path.exists(dest):
            continue
        url = f"{base_url}/{hf_path}{ext}"
        info(f"  Downloading {name} {label}...")
        r = subprocess.run(["curl", "-fSL", "-o", dest, url], capture_output=True)
        if r.returncode != 0:
            warn(f"  Failed: {name}{ext}")
            ok_flag = False
    return ok_flag


def step_tts_voices() -> None:
    header("5 / 7  Piper TTS voices (optional)")

    if not shutil.which("ffmpeg"):
        warn("ffmpeg not installed — TTS output may not play in browser")

    names = list(PIPER_VOICES)
    voice_idx = menu("Which TTS voice do you want?", [
        ("en_US-lessac-medium  (~60 MB)", "English male"),
        ("tr_TR-dfki-medium  (~60 MB)", "Turkish male"),
        ("en_US-amy-medium  (~60 MB)", "English female"),
        ("None — skip TTS", "You can download later"),
    ])
    if voice_idx == 4:
        STATE["tts_voice"] = "en_US-lessac-medium"
        STATE["tts_enabled"] = False
        info("Skipping TTS voice download")
        return

    chosen = names[voice_idx - 1]
    STATE["tts_voice"] = chosen
    STATE["tts_enabled"] = True
    if _download_piper_voice(chosen, PIPER_VOICES[chosen]):
        ok(f"Voice ready: {chosen}")
    else:
        warn("Some voice files failed to download — TTS may not work")


# ── Step 6: Environment configuration ────────────────────────────────────────

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
LITERT_BASE_URL=http://localhost:{LITERT_PORT}

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

# --- Gmail (only if MAIL_PROVIDER=gmail) ---
GMAIL_USER={GMAIL_USER}
GMAIL_APP_PASSWORD={GMAIL_APP_PASSWORD}
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465

# --- ProtonMail / ProtonBridge (only if MAIL_PROVIDER=proton) ---
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

    # Auto-generate API key (reuse existing if present).
    api_key = current.get("API_KEY", "")
    if not api_key:
        api_key = secrets.token_urlsafe(32)
        info(f"Generated API key: {api_key}")

    # Personalization
    assistant_user = ask("Your name", current.get("ASSISTANT_USER", "default"))
    default_city = ask("Default city for weather", current.get("DEFAULT_CITY", ""))

    # ── Email ────────────────────────────────────────────────────────────
    email_idx = menu("Email integration:", [
        ("Gmail", "Read/send via Gmail App Password"),
        ("ProtonMail", "Read/send via ProtonBridge (must run locally)"),
        ("Skip — no email", "Recommended to start"),
    ])
    gmail_user = current.get("GMAIL_USER", "")
    gmail_pass = current.get("GMAIL_APP_PASSWORD", "")
    proton_user = current.get("PROTON_USER", "")
    proton_pass = current.get("PROTON_PASSWORD", "")

    if email_idx == 1:
        mail_provider = "gmail"
        info("Gmail needs an App Password. Generate one at:")
        info("  https://myaccount.google.com/apppasswords")
        gmail_user = ask("Gmail address", gmail_user)
        raw = ask_secret("Gmail App Password (16 chars, no spaces)")
        if raw:
            gmail_pass = raw.replace(" ", "").replace("-", "")
    elif email_idx == 2:
        mail_provider = "proton"
        info("ProtonMail needs ProtonBridge running locally.")
        info("Install from: https://proton.me/mail/bridge")
        proton_user = ask("ProtonMail address", proton_user)
        raw = ask_secret("ProtonBridge password")
        if raw:
            proton_pass = raw
    else:
        mail_provider = ""

    # ── Nextcloud ────────────────────────────────────────────────────────
    nc_url = current.get("NEXTCLOUD_URL", "")
    nc_user = current.get("NEXTCLOUD_USER", "")
    nc_pass = current.get("NEXTCLOUD_PASSWORD", "")
    if not nc_url and ask_yesno("Set up Nextcloud (calendar/notes/tasks)?", default=False):
        nc_url = ask("Nextcloud URL (e.g. https://cloud.example.com)")
        nc_user = ask("Nextcloud username")
        nc_pass = ask_secret("Nextcloud app password")

    # ── Voice ────────────────────────────────────────────────────────────
    stt_idx = menu("Speech-to-text engine:", [
        ("whisper", "Fast, accurate, lightweight (~75 MB)"),
        ("gemma4", "Uses the LLM directly (slower but captures tone)"),
        ("browser", "Web Speech API in the browser"),
    ])
    stt = "whisper" if stt_idx == 1 else ("gemma4" if stt_idx == 2 else "browser")

    tts_idx = menu("Text-to-speech engine:", [
        ("piper", "Local, fully offline"),
        ("browser", "Web Speech API (more voices, needs internet)"),
    ])
    tts_engine = "piper" if tts_idx == 1 else "browser"
    tts_voice = STATE.get("tts_voice", current.get("TTS_VOICE", "en_US-lessac-medium"))

    auto_send = ask("Auto-send after voice transcription? (on/off)", current.get("AUTO_SEND_ON_VOICE", "off"))
    auto_tts = ask("Auto-speak response when input was voice? (on/off)", current.get("AUTO_TTS_ON_VOICE", "off"))

    values = {
        "LLM_BACKEND":        STATE["backend"],
        "LLM_MODEL":          STATE["model"],
        "LITERT_PORT":        str(LITERT_PORT),
        "DEFAULT_CITY":       default_city,
        "ASSISTANT_USER":     assistant_user,
        "API_KEY":            api_key,
        "MAIL_PROVIDER":      mail_provider,
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

    # Preserve any existing values not re-asked above.
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

    content = _ENV_TEMPLATE.format(**values)
    for k, v in values.items():
        pattern = rf"^{re.escape(k)}=.*$"
        replacement = f"{k}={v}"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    env_path.write_text(content.strip() + "\n", encoding="utf-8")
    ok(".env created / updated")


# ── Step 7: systemd service (Linux only) ─────────────────────────────────────

def step_systemd() -> None:
    if IS_WIN or sys.platform == "darwin":
        info("systemd is Linux-only — to auto-start on boot on this OS, see README.md")
        return

    header("7 / 7  Systemd service (optional)")

    if not shutil.which("systemctl"):
        info("systemctl not found — skipping systemd setup")
        return

    if ask_yesno("Create a systemd service to start piSynapse on boot?"):
        user = os.environ.get("SUDO_USER") or os.environ.get("USER") or "pi"
        project_dir = os.path.abspath(".")
        uvicorn_path = os.path.join(project_dir, VENV_DIR, "bin", "uvicorn")
        wants_litert = STATE.get("backend") == "litert" and os.path.exists("/etc/systemd/system/litert.service")

        unit = f"""[Unit]
Description=piSynapse AI Assistant
After=network-online.target{" litert.service" if wants_litert else ""}
Wants=network-online.target{" litert.service" if wants_litert else ""}

[Service]
Type=simple
User={user}
WorkingDirectory={project_dir}
Environment=PATH={os.path.join(project_dir, VENV_DIR, "bin")}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart={uvicorn_path} main:app --host 0.0.0.0 --port 8765
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        service_path = Path("/etc/systemd/system/pisynapse.service")
        try:
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
    run_cmd = f"{venv_bin('uvicorn')} main:app --host 0.0.0.0 --port 8765"

    api_key = ""
    try:
        for line in Path(".env").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("API_KEY=") and "=" in line:
                api_key = line.split("=", 1)[1].strip()
                break
    except Exception:
        pass

    backend = STATE.get("backend", "litert")
    model = STATE.get("model", "gemma4:e2b")

    print(f"\n{green(LINE * 56)}")
    print(green(f"  {OK_SYM} Installation complete!"))
    print(green(LINE * 56))
    print(f"\n  {'Backend':12s}: {backend}")
    print(f"  {'Model':12s}: {model}")
    if backend == "litert":
        print(f"  {'LiteRT':12s}: {'systemd (active)' if os.path.exists('/etc/systemd/system/litert.service') else 'background process on :%d' % LITERT_PORT}")
    if os.path.exists("/etc/systemd/system/pisynapse.service"):
        print(f"  {'piSynapse':12s}: systemd (active)")
    if api_key:
        print(f"  {'API Key':12s}: {api_key}")

    print("\n  Start piSynapse:")
    print(f"    {activate}")
    print(f"    {run_cmd}")
    if backend == "litert" and not _litert_is_running():
        litert_bin = _find_litert_bin() or "litert-lm"
        print("\n  LiteRT is not running — start it first in another terminal:")
        print(f"    {litert_bin} serve --host 0.0.0.0 --port {LITERT_PORT}")
    if backend == "ollama" and not _ollama_is_running():
        print("\n  Ollama is not running — start it first:")
        print("    ollama serve")
    print("\n  Open http://localhost:8765 in your browser.")
    if api_key:
        print("  Enter your API key when prompted.\n")
    if os.path.exists("/etc/systemd/system/litert.service") or os.path.exists("/etc/systemd/system/pisynapse.service"):
        print(f"  {'Manage':12s}: systemctl status litert pisynapse\n")


# ── Entry ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print(blue("\n  piSynapse Installer\n"))

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
