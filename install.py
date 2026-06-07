#!/usr/bin/env python3
"""
piSynapse Installer
Supports: Linux, macOS, Windows
Shells:   bash, zsh, fish, PowerShell, CMD
Run with: python install.py
"""

import os
import sys
import subprocess
import shutil
import getpass
import re

# ── Colour helpers ────────────────────────────────────────────────────────────
IS_WIN = sys.platform == "win32"

def _c(code: str, text: str) -> str:
    if IS_WIN:
        return text
    return f"{code}{text}\033[0m"

def green(t):  return _c("\033[0;32m", t)
def blue(t):   return _c("\033[0;34m", t)
def yellow(t): return _c("\033[1;33m", t)
def red(t):    return _c("\033[0;31m", t)

def info(msg):   print(blue(f"  ℹ  {msg}"))
def ok(msg):     print(green(f"  ✅ {msg}"))
def warn(msg):   print(yellow(f"  ⚠  {msg}"))
def error(msg):  print(red(f"  ❌ {msg}"))
def header(msg): print(f"\n{blue('═' * 56)}\n  {msg}\n{blue('═' * 56)}")

def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"     {prompt}{suffix}: ").strip()
    return val or default

def ask_secret(prompt: str) -> str:
    try:
        return getpass.getpass(f"     {prompt}: ").strip()
    except Exception:
        return input(f"     {prompt} (visible): ").strip()

# ── venv paths ────────────────────────────────────────────────────────────────
VENV_DIR = ".venv"

def venv_bin(name: str) -> str:
    """Returns the path to a binary inside the venv, cross-platform."""
    if IS_WIN:
        return os.path.join(VENV_DIR, "Scripts", f"{name}.exe")
    return os.path.join(VENV_DIR, "bin", name)

# ── Shell detection ───────────────────────────────────────────────────────────
def detect_shell() -> str:
    """Returns a short shell identifier: bash, zsh, fish, powershell, cmd, unknown."""
    if IS_WIN:
        if os.environ.get("PSModulePath"):
            return "powershell"
        return "cmd"
    shell_path = os.environ.get("SHELL", "")
    name = os.path.basename(shell_path).lower()
    if "fish" in name:
        return "fish"
    if "zsh" in name:
        return "zsh"
    if "bash" in name:
        return "bash"
    return "unknown"

def activation_command(shell: str) -> str:
    """Returns the correct venv activation command for the detected shell."""
    cmds = {
        "fish":       f"source {VENV_DIR}/bin/activate.fish",
        "bash":       f"source {VENV_DIR}/bin/activate",
        "zsh":        f"source {VENV_DIR}/bin/activate",
        "unknown":    f"source {VENV_DIR}/bin/activate",
        "powershell": rf"{VENV_DIR}\Scripts\Activate.ps1",
        "cmd":        rf"{VENV_DIR}\Scripts\activate.bat",
    }
    return cmds.get(shell, f"source {VENV_DIR}/bin/activate")

# ── Step 1: Python version ────────────────────────────────────────────────────
def check_python():
    header("1 / 7  Python version")
    major, minor = sys.version_info[:2]
    info(f"Python {major}.{minor} detected")
    if (major, minor) < (3, 10):
        error("piSynapse requires Python 3.10 or newer.")
        sys.exit(1)
    ok("Python version OK")

# ── Step 2: Ollama ────────────────────────────────────────────────────────────
def check_ollama():
    header("2 / 7  Ollama")
    if shutil.which("ollama"):
        ok("Ollama is already installed.")
        return

    warn("Ollama not found.")
    if IS_WIN:
        print("     Download from: https://ollama.com/download/windows")
        print("     Install it, then re-run this script.")
        sys.exit(1)

    choice = input("     Install Ollama now? (y/n): ").strip().lower()
    if choice == "y":
        info("Installing Ollama...")
        result = subprocess.run("curl -fsSL https://ollama.com/install.sh | sh", shell=True)
        if result.returncode != 0:
            error("Ollama installation failed. Visit https://ollama.com")
            sys.exit(1)
        ok("Ollama installed.")
    else:
        error("Ollama is required. Exiting.")
        sys.exit(1)

# ── Step 3: Model selection ───────────────────────────────────────────────────
def select_model() -> str:
    header("3 / 7  Model selection")

    try:
        mem_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        ram_gb = mem_bytes // (1024 ** 3)
    except Exception:
        ram_gb = 0

    if ram_gb:
        info(f"Detected RAM: {ram_gb} GB")

    models = [
        ("gemma4:e2b",   "Best accuracy — recommended for 8 GB+"),
        ("qwen3:1.7b",   "Good balance of speed and quality"),
        ("qwen3:0.6b",   "Optimised for low RAM (< 4 GB)"),
        ("smollm2:1.7b", "Fastest inference"),
    ]

    if ram_gb and ram_gb < 4:
        default = 3
    elif ram_gb and ram_gb < 8:
        default = 2
    else:
        default = 1

    print()
    for i, (name, desc) in enumerate(models, 1):
        marker = "  ◀ recommended" if i == default else ""
        print(f"     {i}) {name:<18} {desc}{marker}")

    choice = ask("\n     Choose model number", str(default))
    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(models)):
            raise ValueError
    except ValueError:
        idx = default - 1

    selected, _ = models[idx]

    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if selected in result.stdout:
        ok(f"{selected} is already downloaded.")
    else:
        info(f"Downloading {selected} (this may take a while)...")
        dl = subprocess.run(["ollama", "pull", selected])
        if dl.returncode != 0:
            error(f"Failed to download {selected}.")
            sys.exit(1)
        ok(f"{selected} downloaded.")

    return selected

# ── Step 4: Project structure ─────────────────────────────────────────────────
def setup_structure():
    header("4 / 7  Project structure")

    os.makedirs("routers", exist_ok=True)
    ok("routers/ directory ready")

    init_path = os.path.join("routers", "__init__.py")
    if not os.path.exists(init_path):
        open(init_path, "w").close()
        ok("Created routers/__init__.py")

    chat_src = "chat.py"
    chat_dst = os.path.join("routers", "chat.py")
    if os.path.exists(chat_src) and not os.path.exists(chat_dst):
        shutil.move(chat_src, chat_dst)
        ok("Moved chat.py → routers/chat.py")
    elif os.path.exists(chat_dst):
        ok("routers/chat.py already in place")
    else:
        warn("chat.py not found — make sure routers/chat.py exists before starting.")

    if os.path.exists("example.env") and not os.path.exists(".env"):
        shutil.copy("example.env", ".env")
        ok("Copied example.env → .env")
    elif not os.path.exists(".env"):
        warn("No .env found. Creating an empty one.")
        open(".env", "w").close()
    else:
        ok(".env already exists")

# ── Step 5: Virtual environment ───────────────────────────────────────────────
def create_venv():
    header("5 / 7  Virtual environment")

    if os.path.exists(VENV_DIR):
        ok(f"{VENV_DIR}/ already exists, skipping creation.")
        return

    info(f"Creating {VENV_DIR}/ ...")
    result = subprocess.run([sys.executable, "-m", "venv", VENV_DIR])
    if result.returncode != 0:
        error("Failed to create virtual environment.")
        sys.exit(1)
    ok(f"{VENV_DIR}/ created.")

# ── Step 6: Python dependencies ───────────────────────────────────────────────
def install_deps():
    header("6 / 7  Python dependencies")

    if not os.path.exists("requirements.txt"):
        error("requirements.txt not found.")
        sys.exit(1)

    pip = venv_bin("pip")
    info(f"Installing into {VENV_DIR}/ using venv pip...")

    # Upgrade pip first to avoid outdated-pip warnings
    subprocess.run([pip, "install", "--quiet", "--upgrade", "pip"])

    result = subprocess.run([pip, "install", "-r", "requirements.txt"])
    if result.returncode != 0:
        error("pip install failed. Check the error above.")
        sys.exit(1)
    ok(f"All dependencies installed into {VENV_DIR}/")

# ── Step 7: Credentials ───────────────────────────────────────────────────────
def configure_env(selected_model: str):
    header("7 / 7  Configuration")
    print("     (press Enter to skip any field)\n")

    fields = {
        "NEXTCLOUD_URL":      ask("Nextcloud URL (e.g. https://cloud.example.com)"),
        "NEXTCLOUD_USER":     ask("Nextcloud username"),
        "NEXTCLOUD_PASSWORD": ask_secret("Nextcloud app password"),
        "GMAIL_USER":         ask("Gmail address"),
        "GMAIL_APP_PASSWORD": ask_secret("Gmail app password (xxxx-xxxx-xxxx-xxxx)").replace("-", ""),
        "ASSISTANT_USER":     ask("Your name (for personalisation)", "default"),
        "LLM_MODEL":          selected_model,
    }

    with open(".env", "r") as f:
        content = f.read()

    for key, value in fields.items():
        if not value:
            continue
        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        else:
            content += f"\n{replacement}"

    with open(".env", "w") as f:
        f.write(content)

    ok(".env updated.")

# ── Summary ───────────────────────────────────────────────────────────────────
def print_summary(selected_model: str):
    shell = detect_shell()
    activate_cmd = activation_command(shell)
    uvicorn_cmd = venv_bin("uvicorn")

    # On fish/zsh/bash we can show a one-liner without activating
    run_cmd = f"{uvicorn_cmd} main:app --host 0.0.0.0 --port 8000"

    print(f"\n{green('═' * 56)}")
    print(green("  ✅ Installation complete!"))
    print(green('═' * 56))
    print(f"\n  Detected shell : {shell}")
    print(f"  Model          : {selected_model}")
    print()
    print(f"  To activate the venv ({shell}):")
    print(f"    {activate_cmd}")
    print()
    print(f"  Or run directly without activating:")
    print(f"    {run_cmd}")
    print()
    print(f"  Health check:")
    print(f"    curl http://localhost:8000/health")
    print()
    print(f"  Test chat:")
    print(f"    curl -X POST http://localhost:8000/chat \\")
    print(f'      -H "Content-Type: application/json" \\')
    print(f"      -d '{{\"message\": \"Merhaba!\", \"session_id\": \"s1\"}}'")
    print()

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(blue("\n🚀 piSynapse Installer\n"))

    check_python()
    check_ollama()
    selected_model = select_model()
    setup_structure()
    create_venv()
    install_deps()
    configure_env(selected_model)
    print_summary(selected_model)