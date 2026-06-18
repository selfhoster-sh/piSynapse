#!/usr/bin/env python3
"""
piSynapse Installer
Supports: Linux, macOS, Windows
Run with: python install.py
"""

import os
import sys
import subprocess
import shutil
import getpass
import re
from typing import Dict

TARGET_MODEL = "gemma4:e2b"
VENV_DIR     = ".venv"
IS_WIN       = sys.platform == "win32"


# ── Terminal helpers ──────────────────────────────────────────────────────────

def _c(code: str, text: str) -> str:
    return text if IS_WIN else f"{code}{text}\033[0m"

def green(t: str)  -> str: return _c("\033[0;32m", t)
def blue(t: str)   -> str: return _c("\033[0;34m", t)
def yellow(t: str) -> str: return _c("\033[1;33m", t)
def red(t: str)    -> str: return _c("\033[0;31m", t)

def info(msg: str)   -> None: print(blue(f"  ℹ  {msg}"))
def ok(msg: str)     -> None: print(green(f"  ✅ {msg}"))
def warn(msg: str)   -> None: print(yellow(f"  ⚠  {msg}"))
def error(msg: str)  -> None: print(red(f"  ❌ {msg}"))
def header(msg: str) -> None: print(f"\n{blue('═' * 56)}\n  {msg}\n{blue('═' * 56)}")

def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"     {prompt}{suffix}: ").strip()
    return val or default

def ask_secret(prompt: str) -> str:
    try:
        return getpass.getpass(f"     {prompt}: ").strip()
    except Exception:
        return input(f"     {prompt} (visible): ").strip()

def venv_bin(name: str) -> str:
    if IS_WIN:
        return os.path.join(VENV_DIR, "Scripts", f"{name}.exe")
    return os.path.join(VENV_DIR, "bin", name)

def detect_shell() -> str:
    if IS_WIN:
        return "powershell" if os.environ.get("PSModulePath") else "cmd"
    name = os.path.basename(os.environ.get("SHELL", "")).lower()
    for shell in ("fish", "zsh", "bash"):
        if shell in name:
            return shell
    return "unknown"

def activation_command(shell: str) -> str:
    return {
        "fish":       f"source {VENV_DIR}/bin/activate.fish",
        "bash":       f"source {VENV_DIR}/bin/activate",
        "zsh":        f"source {VENV_DIR}/bin/activate",
        "unknown":    f"source {VENV_DIR}/bin/activate",
        "powershell": rf"{VENV_DIR}\Scripts\Activate.ps1",
        "cmd":        rf"{VENV_DIR}\Scripts\activate.bat",
    }.get(shell, f"source {VENV_DIR}/bin/activate")


# ── Step 1: Python version ────────────────────────────────────────────────────

def check_python() -> None:
    header("1 / 6  Python version")
    major, minor = sys.version_info[:2]
    info(f"Python {major}.{minor} detected")
    if (major, minor) < (3, 10):
        error("piSynapse requires Python 3.10 or newer.")
        sys.exit(1)
    ok("Python version OK")


# ── Step 2: Ollama ───────────────────────────────────────────────────────────

def check_ollama() -> None:
    header("2 / 6  Ollama")
    if shutil.which("ollama"):
        ok("Ollama is already installed.")
        return

    warn("Ollama not found.")
    if IS_WIN:
        print("     Download from: https://ollama.com/download/windows")
        print("     Install it, then re-run this script.")
        sys.exit(1)

    if input("     Install Ollama now? (y/n): ").strip().lower() == "y":
        info("Installing Ollama…")
        result = subprocess.run("curl -fsSL https://ollama.com/install.sh | sh", shell=True)
        if result.returncode != 0:
            error("Ollama installation failed. Visit https://ollama.com")
            sys.exit(1)
        ok("Ollama installed.")
    else:
        error("Ollama is required. Exiting.")
        sys.exit(1)


# ── Step 3: Model ────────────────────────────────────────────────────────────

def setup_model() -> None:
    header("3 / 6  Model")

    # Warn if system RAM is below the recommended threshold
    try:
        ram_gb = (os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")) // (1024 ** 3)
        info(f"System RAM: {ram_gb} GB")
        if ram_gb < 8:
            warn(f"{TARGET_MODEL} recommends at least 8 GB of RAM. Performance may be degraded.")
    except Exception:
        info("Could not read system RAM — skipping hardware check.")

    info(f"Checking for {TARGET_MODEL}…")
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True)
        if TARGET_MODEL in result.stdout:
            ok(f"{TARGET_MODEL} is already available.")
            return
    except subprocess.CalledProcessError:
        error("Could not reach the Ollama service. Make sure it is running.")
        sys.exit(1)

    info(f"Pulling {TARGET_MODEL} (this may take a few minutes)…")
    if subprocess.run(["ollama", "pull", TARGET_MODEL]).returncode != 0:
        error(f"Failed to pull {TARGET_MODEL}.")
        sys.exit(1)
    ok(f"{TARGET_MODEL} ready.")


# ── Step 4: Project structure ─────────────────────────────────────────────────

def setup_structure() -> None:
    header("4 / 6  Project structure")

    # Ensure the routers package directory exists with its __init__.py
    os.makedirs("routers", exist_ok=True)
    ok("routers/ directory ready")

    init_path = os.path.join("routers", "__init__.py")
    if not os.path.exists(init_path):
        open(init_path, "w").close()
        ok("Created routers/__init__.py")

    # Create .env from the example template if it doesn't exist yet
    if os.path.exists("example.env") and not os.path.exists(".env"):
        shutil.copy("example.env", ".env")
        ok("Copied example.env → .env")
    elif not os.path.exists(".env"):
        warn("No example.env found — creating an empty .env.")
        open(".env", "w").close()
    else:
        ok(".env already exists")


# ── Step 5: Virtual environment ───────────────────────────────────────────────

def create_venv() -> None:
    header("5 / 6  Virtual environment")
    if os.path.exists(VENV_DIR):
        ok(f"{VENV_DIR}/ already exists, skipping.")
        return
    info(f"Creating {VENV_DIR}/…")
    if subprocess.run([sys.executable, "-m", "venv", VENV_DIR]).returncode != 0:
        error("Failed to create virtual environment.")
        sys.exit(1)
    ok(f"{VENV_DIR}/ created.")


# ── Step 6: Dependencies + configuration ─────────────────────────────────────

def install_deps() -> None:
    header("6 / 6  Dependencies & configuration")

    if not os.path.exists("requirements.txt"):
        error("requirements.txt not found.")
        sys.exit(1)

    pip = venv_bin("pip")
    info("Upgrading pip…")
    subprocess.run([pip, "install", "--quiet", "--upgrade", "pip"])
    info("Installing requirements…")
    if subprocess.run([pip, "install", "-r", "requirements.txt"]).returncode != 0:
        error("pip install failed. Check the output above.")
        sys.exit(1)
    ok("Dependencies installed.")

    # Interactive configuration — all fields are optional
    print(f"\n{blue('  ── Optional configuration (Enter to skip) ──')}\n")
    fields: Dict[str, str] = {
        "NEXTCLOUD_URL":      ask("Nextcloud URL (e.g. https://cloud.example.com)"),
        "NEXTCLOUD_USER":     ask("Nextcloud username"),
        "NEXTCLOUD_PASSWORD": ask_secret("Nextcloud app password"),
        "GMAIL_USER":         ask("Gmail address"),
        "GMAIL_APP_PASSWORD": ask_secret("Gmail app password (xxxx-xxxx-xxxx-xxxx)").replace("-", ""),
        "ASSISTANT_USER":     ask("Your name (for personalization)", "default"),
        "DEFAULT_CITY":       ask("Default city for weather", "Istanbul"),
        "LLM_MODEL":          TARGET_MODEL,
    }

    try:
        content = open(".env", "r", encoding="utf-8").read()
    except Exception:
        content = ""

    for key, value in fields.items():
        if not value:
            continue
        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        else:
            content = content.rstrip("\n") + f"\n{replacement}\n"

    open(".env", "w", encoding="utf-8").write(content.strip() + "\n")
    ok(".env updated.")


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary() -> None:
    shell        = detect_shell()
    activate_cmd = activation_command(shell)
    run_cmd      = f"{venv_bin('uvicorn')} main:app --host 0.0.0.0 --port 8000"

    print(f"\n{green('═' * 56)}")
    print(green("  ✅ Installation complete!"))
    print(green('═' * 56))
    print(f"\n  Shell  : {shell}")
    print(f"  Model  : {TARGET_MODEL}")
    print(f"\n  Activate the virtual environment:")
    print(f"    {activate_cmd}")
    print(f"\n  Start piSynapse:")
    print(f"    {run_cmd}")
    print(f"\n  Then open http://localhost:8000 in your browser.\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(blue("\n  piSynapse Installer\n"))
    check_python()
    check_ollama()
    setup_model()
    setup_structure()
    create_venv()
    install_deps()
    print_summary()
