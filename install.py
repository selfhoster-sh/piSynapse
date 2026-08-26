#!/usr/bin/env python3
"""piSynapse Installer — offline-first personal AI assistant.
Platforms: Linux, macOS, Windows (experimental).
Run with: python3 install.py

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
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ── Defaults ──────────────────────────────────────────────────────────────────

VENV_DIR = "venv"
LITERT_PORT = 9379
IS_WIN = sys.platform == "win32"

# Shared state passed between steps so no question is asked twice.
STATE: dict = {}

# ── CLI flags ────────────────────────────────────────────────────────────────

BATCH_MODE = False     # --yes : accept all defaults, no prompts
SKIP_LLM = False       # --skip-llm : skip LLM backend setup
SKIP_TTS = False       # --skip-tts : skip TTS voice download
SKIP_SYSTEMD = False   # --skip-systemd : skip systemd service creation


def _parse_args() -> None:
    global BATCH_MODE, SKIP_LLM, SKIP_TTS, SKIP_SYSTEMD
    args = sys.argv[1:]
    if "--yes" in args or "-y" in args:
        BATCH_MODE = True
    if "--skip-llm" in args:
        SKIP_LLM = True
    if "--skip-tts" in args:
        SKIP_TTS = True
    if "--skip-systemd" in args:
        SKIP_SYSTEMD = True
    if "--help" in args or "-h" in args:
        print("""
  piSynapse Installer

  Usage: python3 install.py [options]

  Options:
    -y, --yes         Non-interactive mode (accept all defaults)
    --skip-llm        Skip LLM backend setup (model download, server start)
    --skip-tts        Skip TTS voice download
    --skip-systemd    Skip systemd service creation
    -h, --help        Show this help
""")
        sys.exit(0)


# ── Distro / package manager detection ───────────────────────────────────────

class _Distro:
    """Detected Linux distribution info."""

    id: str = ""            # ubuntu, fedora, arch, alpine, ...
    pm: str = ""            # apt, dnf, pacman, zypper, apk, brew, unknown
    pm_install: list[str] = []  # command prefix for installing packages
    pm_sudo: bool = True   # needs sudo?

    @property
    def is_debian(self) -> bool:
        return self.pm == "apt"

    @property
    def is_redhat(self) -> bool:
        return self.pm in ("dnf", "yum")

    @property
    def is_arch(self) -> bool:
        return self.pm == "pacman"


DISTRO = _Distro()


def _detect_distro() -> None:
    """Detect the Linux distribution and set DISTRO.pm (package manager)."""
    if IS_WIN or sys.platform == "darwin":
        DISTRO.pm = "brew" if sys.platform == "darwin" else "unknown"
        return

    # 1. Check /etc/os-release (standard on all modern distros)
    os_release: dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                os_release[k.strip()] = v.strip().strip('"')
    except Exception:
        pass
    DISTRO.id = os_release.get("ID", "").lower()

    # 2. Detect package manager by checking what's on PATH
    if shutil.which("apt") or shutil.which("apt-get"):
        DISTRO.pm = "apt"
    elif shutil.which("dnf"):
        DISTRO.pm = "dnf"
    elif shutil.which("pacman"):
        DISTRO.pm = "pacman"
    elif shutil.which("zypper"):
        DISTRO.pm = "zypper"
    elif shutil.which("apk"):
        DISTRO.pm = "apk"
    elif shutil.which("brew"):
        DISTRO.pm = "brew"
    else:
        DISTRO.pm = "unknown"


def _pkg_install(*packages: str, extra_args: list[str] | None = None) -> bool:
    """Install packages using the detected package manager. Returns True on success."""
    args = extra_args or []
    if DISTRO.pm == "apt":
        cmd = ["sudo", "apt-get", "install", "-y"] + args + list(packages)
    elif DISTRO.pm == "dnf":
        cmd = ["sudo", "dnf", "install", "-y"] + args + list(packages)
    elif DISTRO.pm == "yum":
        cmd = ["sudo", "yum", "install", "-y"] + args + list(packages)
    elif DISTRO.pm == "pacman":
        cmd = ["sudo", "pacman", "-S", "--noconfirm"] + args + list(packages)
    elif DISTRO.pm == "zypper":
        cmd = ["sudo", "zypper", "--non-interactive", "install"] + args + list(packages)
    elif DISTRO.pm == "apk":
        cmd = ["sudo", "apk", "add"] + args + list(packages)
    elif DISTRO.pm == "brew":
        cmd = ["brew", "install"] + list(packages)
    else:
        warn(f"Unknown package manager — install manually: {' '.join(packages)}")
        return False

    r = subprocess.run(cmd)
    return r.returncode == 0


def _pkg_build_essential() -> str | None:
    """Return the build-essential equivalent package name for this distro, or None."""
    if DISTRO.pm == "apt":
        return "build-essential"
    elif DISTRO.pm in ("dnf", "yum"):
        return "gcc"  # groupinstall "Development Tools" or just gcc
    elif DISTRO.pm == "pacman":
        return "base-devel"
    elif DISTRO.pm == "zypper":
        return "patterns-devel-base-devel_basis"
    elif DISTRO.pm == "apk":
        return "build-base"
    return None


def _pkg_python_venv() -> str | None:
    """Return the python3-venv package name for this distro, or None if not needed."""
    major, minor = sys.version_info[:2]
    ver = f"{major}.{minor}"

    if DISTRO.pm == "apt":
        return f"python{ver}-venv"
    elif DISTRO.pm in ("dnf", "yum"):
        # On Fedora/RHEL, venv module is included in the main python3 package.
        # But if ensurepip is missing, we need python3-pip or python3-virtualenv.
        # Check if ensurepip module exists first.
        try:
            r = subprocess.run(
                [sys.executable, "-c", "import ensurepip"],
                capture_output=True, timeout=5,
            )
            if r.returncode == 0:
                return None  # ensurepip works, no extra package needed
        except Exception:
            pass
        return "python3-pip"  # provides ensurepip on Fedora/RHEL
    elif DISTRO.pm == "pacman":
        return None  # Arch python includes venv by default
    elif DISTRO.pm == "zypper":
        return f"python{ver}-venv"
    elif DISTRO.pm == "apk":
        return None  # Alpine python3 includes venv
    return None


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
    if BATCH_MODE:
        return default
    suffix = f" [{default}]" if default else ""
    val = input(f"     {prompt}{suffix}: ").strip()
    return val or default


def ask_secret(prompt: str) -> str:
    if BATCH_MODE:
        return ""
    try:
        return getpass.getpass(f"     {prompt}: ").strip()
    except Exception:
        return input(f"     {prompt} (visible): ").strip()

def ask_yesno(prompt: str, default: bool = True) -> bool:
    if BATCH_MODE:
        return default
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
    if DISTRO.pm != "unknown":
        info(f"Detected: {DISTRO.id or DISTRO.pm} ({DISTRO.pm})")
    missing: list[str] = []

    # ffmpeg
    if shutil.which("ffmpeg"):
        ok("ffmpeg found")
    else:
        warn("ffmpeg not found (required for audio/voice)")
        if IS_WIN:
            info("Download from: https://ffmpeg.org/download.html")
        elif sys.platform == "darwin":
            if ask_yesno("Install ffmpeg now? (brew install ffmpeg)"):
                if _pkg_install("ffmpeg"):
                    ok("ffmpeg installed")
                else:
                    missing.append("ffmpeg")
        else:
            if ask_yesno(f"Install ffmpeg now? ({DISTRO.pm} install ffmpeg)"):
                if _pkg_install("ffmpeg"):
                    ok("ffmpeg installed")
                else:
                    warn("ffmpeg install failed — install manually later")
                    missing.append("ffmpeg")
            else:
                missing.append("ffmpeg")

    # curl
    if not shutil.which("curl"):
        warn("curl not found (needed for model downloads and health checks)")
        if not IS_WIN:
            _pkg_install("curl")
            if shutil.which("curl"):
                ok("curl installed")
            else:
                missing.append("curl")
        else:
            missing.append("curl")

    # python3-venv (needed before venv creation)
    if not IS_WIN and sys.platform != "darwin":
        venv_pkg = _pkg_python_venv()
        if venv_pkg:
            # Quick check: can we actually create a venv?
            if not _venv_works():
                warn(f"python3-venv not functional — installing {venv_pkg}")
                if _pkg_install(venv_pkg):
                    ok(f"{venv_pkg} installed")
                else:
                    warn(f"Could not install {venv_pkg} — venv creation may fail")

    # build tools
    if not IS_WIN and sys.platform != "darwin":
        if not _build_tools_installed():
            be_pkg = _pkg_build_essential()
            if be_pkg and ask_yesno(f"Install build tools ({be_pkg}, recommended for pip packages)?"):
                _pkg_install(be_pkg)

    if not missing:
        ok("All system dependencies satisfied")


def _venv_works() -> bool:
    """Check if venv creation with ensurepip actually works."""
    test_dir = Path(".venv_test")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(test_dir)],
            capture_output=True, timeout=10,
        )
        # Even --without-pip should work; if it fails, venv is broken
        if r.returncode != 0:
            return False
        # Now test ensurepip
        pip_path = test_dir / "bin" / "pip"
        if not pip_path.exists():
            # Try bootstrapping
            r2 = subprocess.run(
                [str(test_dir / "bin" / "python3"), "-m", "ensurepip", "--upgrade"],
                capture_output=True, timeout=30,
            )
            return r2.returncode == 0
        return True
    except Exception:
        return False
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def _build_tools_installed() -> bool:
    """Return True when a C toolchain is already present."""
    # Check for compilers on PATH (universal)
    if shutil.which("gcc") and shutil.which("make"):
        return True

    # Debian/Ubuntu: query build-essential via dpkg
    if shutil.which("dpkg"):
        try:
            r = subprocess.run(
                ["dpkg", "-s", "build-essential"],
                capture_output=True, timeout=15,
            )
            if r.returncode == 0:
                return True
        except Exception:
            pass

    # Fedora/RHEL: check for gcc via rpm
    if shutil.which("rpm"):
        try:
            r = subprocess.run(
                ["rpm", "-q", "gcc"],
                capture_output=True, timeout=15,
            )
            if r.returncode == 0:
                return True
        except Exception:
            pass

    # Arch: base-devel group
    if shutil.which("pacman"):
        try:
            r = subprocess.run(
                ["pacman", "-Qi", "base-devel"],
                capture_output=True, timeout=15,
            )
            if r.returncode == 0:
                return True
        except Exception:
            pass

    return False


# ── Step 3: Virtual env + Python packages ────────────────────────────────────

def step_venv() -> None:
    header("3 / 7  Virtual environment & dependencies")

    pip = venv_bin("pip")

    # Check if existing venv is functional
    if os.path.exists(VENV_DIR):
        if os.path.isfile(pip):
            ok(f"{VENV_DIR}/ already exists")
        else:
            # venv exists but pip is missing — broken venv (e.g. ensurepip was unavailable)
            warn(f"{VENV_DIR}/ exists but is broken (no pip) — recreating")
            shutil.rmtree(VENV_DIR, ignore_errors=True)

    if not os.path.exists(VENV_DIR):
        info(f"Creating {VENV_DIR}/...")
        r = subprocess.run([sys.executable, "-m", "venv", VENV_DIR])
        if r.returncode != 0:
            # ensurepip might have failed; try without-pip and bootstrap
            warn("Standard venv creation failed — trying without pip")
            r2 = subprocess.run([sys.executable, "-m", "venv", "--without-pip", VENV_DIR])
            if r2.returncode != 0:
                error("Failed to create virtual environment.")
                error("Install the venv package for your distro:")
                error(f"  Debian/Ubuntu:  sudo apt install python{sys.version_info[0]}.{sys.version_info[1]}-venv")
                error(f"  Fedora/RHEL:    sudo dnf install python{sys.version_info[0]}.{sys.version_info[1]}-devel")
                error("  Arch:           sudo pacman -S python (includes venv)")
                error(f"  openSUSE:       sudo zypper install python{sys.version_info[0]}.{sys.version_info[1]}-venv")
                sys.exit(1)

            # Bootstrap pip manually via get-pip.py
            info("Bootstrapping pip via get-pip.py...")
            bootstrap_ok = False
            for cmd in [
                [sys.executable, "-m", "ensurepip", "--upgrade"],
            ]:
                r3 = subprocess.run(cmd, cwd=VENV_DIR, capture_output=True, text=True)
                if r3.returncode == 0:
                    bootstrap_ok = True
                    break

            if not bootstrap_ok:
                # Last resort: download get-pip.py
                info("Downloading get-pip.py...")
                try:
                    get_pip = os.path.join(VENV_DIR, "get-pip.py")
                    urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", get_pip)
                    venv_python = venv_bin("python3")
                    r4 = subprocess.run([venv_python, get_pip], capture_output=True, text=True)
                    os.remove(get_pip)
                    bootstrap_ok = r4.returncode == 0
                except Exception as e:
                    warn(f"get-pip.py download failed: {e}")

            if not bootstrap_ok:
                error("Could not install pip into the virtual environment.")
                sys.exit(1)

            ok(f"{VENV_DIR}/ created (pip bootstrapped)")
        else:
            ok(f"{VENV_DIR}/ created")

    # Verify pip exists now
    if not os.path.isfile(pip):
        # Try to find pip3 as fallback
        pip3 = venv_bin("pip3")
        if os.path.isfile(pip3):
            pip = pip3
        else:
            error(f"pip not found at {pip}")
            error("The virtual environment may be broken. Delete it and re-run:")
            error(f"  rm -rf {VENV_DIR}")
            sys.exit(1)

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
    # Try pip install first (into venv)
    pip = venv_bin("pip")
    if os.path.isfile(pip):
        r = subprocess.run(
            [pip, "install", "--quiet", "uv"],
            capture_output=True, text=True,
        )
    elif shutil.which("pipx"):
        r = subprocess.run(
            ["pipx", "install", "uv"],
            capture_output=True, text=True,
        )
    else:
        # Fallback: try pip install --user
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


def _litert_model_imported(import_id: str, litert_bin: str = "litert-lm") -> bool:
    """Check whether a model is already in litert-lm's local registry.

    A hung/hissing CLI must not crash the installer — treat timeouts and any
    subprocess failure as "not imported" (the caller then offers to import).
    """
    try:
        r = subprocess.run([litert_bin, "list"], capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError):
        return False
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


def _litert_model_served(model_id: str) -> bool:
    """Check whether a specific model id appears in the running server's registry."""
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "5", f"http://localhost:{LITERT_PORT}/v1/models"],
            capture_output=True, text=True, timeout=8,
        )
        return r.returncode == 0 and model_id in r.stdout
    except Exception:
        return False


def _litert_python() -> str:
    """Return a python interpreter that can import litert_lm.

    litert-lm is installed one of two ways:
      - `uv tool install litert-lm` → dedicated tool venv
        (~/.local/share/uv/tools/litert-lm/bin/python3)
      - `pip install litert-lm` into the app venv → .venv python
    The piServe server (litert_serve/server.py) must run under the
    interpreter that has the litert_lm package — the CLI binary alone is
    not enough.
    """
    uv_python = os.path.expanduser("~/.local/share/uv/tools/litert-lm/bin/python3")
    if os.path.isfile(uv_python):
        return uv_python
    return venv_bin("python3")


def _model_dash_id() -> str:
    """Model id as the app requests it ('gemma4:e2b' → 'gemma4-e2b')."""
    return STATE.get("model", "gemma4:e2b").replace(":", "-")


def _piserve_config_path() -> Path:
    return Path(__file__).resolve().parent / "litert_serve" / "config.json"


def _write_piserve_config() -> bool:
    """Regenerate litert_serve/config.json for the installed model.

    server.py reads this file (Engine needs an exact model_path, and
    `litert-lm serve` ignores max_num_tokens — this is the whole reason
    piServe exists). Atomic write so a crash can't leave a half-written
    config behind.
    """
    model_id = _model_dash_id()
    cfg = {
        "model_id": model_id,
        "model_path": os.path.expanduser(f"~/.litert-lm/models/{model_id}/model.litertlm"),
        # Must match config.DEFAULT_LLM_NUM_CTX (single source of truth).
        "max_num_tokens": 8192,
        "speculative_decoding": True,
        "use_ringbuffers_local_attention": False,
        "enable_ynnpack": False,
        "host": "127.0.0.1",
        "port": LITERT_PORT,
    }
    cfg_path = _piserve_config_path()
    try:
        tmp = cfg_path.with_name(cfg_path.name + ".tmp")
        tmp.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, cfg_path)
        return True
    except OSError as e:
        warn(f"Could not write {cfg_path}: {e}")
        return False


def _start_litert_server(litert_bin: str) -> bool:
    """Start the piServe backend and wait until it accepts requests.

    piServe (litert_serve/server.py) wraps the litert Engine so the
    context window is configurable (max_num_tokens); the stock
    `litert-lm serve` hard-caps at 4096 and is bound to 127.0.0.1.
    """
    if _litert_is_running():
        ok(f"LiteRT server already running on :{LITERT_PORT}")
        return True

    server_py = Path(__file__).resolve().parent / "litert_serve" / "server.py"
    if not server_py.is_file():
        error(f"Missing server file: {server_py}")
        error("Re-run install from the piSynapse checkout (litert_serve/ must sit next to install.py).")
        return False

    if not _write_piserve_config():
        return False

    # Linux with systemd → proper service (auto-start on boot). If the user
    # declines the service, still ASK before falling back to a background
    # process instead of silently starting one.
    if shutil.which("systemctl"):
        if ask_yesno("Create & start piServe systemd service (auto-start on boot)?"):
            if _create_piserve_service(server_py):
                return _wait_litert_ready()
            return False
    if not ask_yesno(f"Start piServe server now on port {LITERT_PORT}?"):
        info("Skipping server start. Start it later with:")
        info(f"  {_litert_python()} {server_py}")
        return False

    info(f"Starting piServe on 127.0.0.1:{LITERT_PORT}...")
    log_path = os.path.abspath("litert-server.log")
    logf = open(log_path, "ab")
    try:
        subprocess.Popen(
            [_litert_python(), str(server_py)],
            stdout=logf, stderr=logf, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        error(f"Could not start piServe: {e}")
        logf.close()
        return False
    ok(f"Server starting — logs: {log_path}")
    return _wait_litert_ready()


def _wait_litert_ready(timeout_s: int = 120) -> bool:
    """Poll the LiteRT health endpoint until it responds or times out."""
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


def _create_piserve_service(server_py: Path) -> bool:
    """Create a systemd unit that runs litert_serve/server.py (piServe)."""
    if not shutil.which("systemctl"):
        warn("systemctl not found — skipping systemd service")
        return False

    user = os.environ.get("SUDO_USER") or os.environ.get("USER") or "pi"
    python = os.path.abspath(_litert_python())
    user_home = os.path.expanduser(f"~{user}")

    unit = f"""[Unit]
Description=piServe (LiteRT-LM backend for piSynapse)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
Environment=HOME={user_home}
ExecStart={python} {server_py}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    try:
        tmp = Path("/tmp/piserve.service")
        tmp.write_text(unit, encoding="utf-8")
        subprocess.run(["sudo", "cp", str(tmp), "/etc/systemd/system/piserve.service"], check=True)
        subprocess.run(["sudo", "systemctl", "daemon-reload"], capture_output=True)
        subprocess.run(["sudo", "systemctl", "enable", "piserve"], capture_output=True)
        subprocess.run(["sudo", "systemctl", "start", "piserve"])
        # Retire the legacy litert.service — it binds the same port with a
        # fixed 4096-token cap, so leaving both up would fight for :9379.
        if os.path.exists("/etc/systemd/system/litert.service"):
            subprocess.run(["sudo", "systemctl", "stop", "litert"], capture_output=True)
            subprocess.run(["sudo", "systemctl", "disable", "litert"], capture_output=True)
            info("Stopped & disabled legacy litert.service (superseded by piserve.service)")
        ok("piserve.service created and started")
        return True
    except Exception as e:
        warn(f"Could not create piserve systemd service: {e}")
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
        if _litert_model_imported(import_id, litert_bin):
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
            elif not _litert_model_imported(import_id, litert_bin):
                warn(f"Import reported success but '{import_id}' not found in registry — check: {litert_bin} list")
            else:
                ok(f"Model imported as '{import_id}'")

        # Verify the registry, then start the server.
        ok("Imported models:")
        subprocess.run([litert_bin, "list"])
        _start_litert_server(litert_bin)
        if not _litert_model_served(import_id):
            warn(f"Model '{import_id}' is not served yet — start the server and check: {litert_bin} list")

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
        if not _ollama_is_running():
            if ask_yesno("Ollama server isn't running — start it now?"):
                info("Starting Ollama server...")
                subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            else:
                info("Skipping — start it later with: ollama serve")
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
# Keep these in sync with config.DEFAULT_LLM_NUM_CTX / DEFAULT_LLM_MAX_OUTPUT_TOKENS.
LLM_MODEL={LLM_MODEL}
LLM_NUM_CTX=8192
LLM_NUM_BATCH=256
LLM_TEMPERATURE=0.6
LLM_TOP_P=0.85
LLM_TOP_K=40
LLM_KEEP_ALIVE=4h
LLM_TIMEOUT=600
SSE_READ_IDLE_TIMEOUT=300.0
LLM_MAX_TOOL_ITERATIONS=5
LLM_REASONING_EFFORT=medium
LLM_MAX_OUTPUT_TOKENS=4096

# --- Embedding ---
EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

# --- Memory ---
MEMORY_SIMILARITY_THRESHOLD=0.68
HISTORY_LIMIT=12
MEMORY_LIMIT=10
SUMMARY_BATCH_SIZE=5
SUMMARY_EARLY_TRIGGER=6
# Retention (days; 0 = keep forever)
CONVERSATION_RETENTION_DAYS=0
MEMORY_RETENTION_DAYS=0

# --- Database ---
DB_PATH=assistant.db

# --- Weather ---
DEFAULT_CITY={DEFAULT_CITY}
WEATHER_TIMEOUT=10

# --- Nextcloud (optional) ---
NEXTCLOUD_URL={NEXTCLOUD_URL}
NEXTCLOUD_USER={NEXTCLOUD_USER}
NEXTCLOUD_PASSWORD={NEXTCLOUD_PASSWORD}
NEXTCLOUD_TIMEOUT=10

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
IMAP_TIMEOUT=20
SMTP_TIMEOUT=20

# --- Piper TTS ---
TTS_VOICE={TTS_VOICE}
TTS_ENGINE={TTS_ENGINE}

# --- Security ---
ENV_PATH=.env
API_KEY={API_KEY}
CORS_ORIGINS=
# Comma-separated allowed Host header values (e.g. 192.168.1.X,myhost.local).
# Empty = auto-allow this machine's local hostnames/IPs (safe default).
TRUSTED_HOSTS={TRUSTED_HOSTS}
# Trust X-Forwarded-For for client IPs when behind a reverse proxy (1/true/yes/on)
TRUST_X_FORWARDED_FOR=
MEDIA_MAX_MB=100

# --- STT ---
STT_ENGINE={STT_ENGINE}

# --- Voice Input Behavior ---
AUTO_SEND_ON_VOICE={AUTO_SEND_ON_VOICE}
AUTO_TTS_ON_VOICE={AUTO_TTS_ON_VOICE}

# --- Intent ---
INTENT_LLM_FALLBACK=off

# --- Assistant language for backend user-facing strings (tr/en) ---
UI_LANGUAGE=en

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


def _fill_template(template: str, values: dict) -> str:
    """Substitute {PLACEHOLDER} keys without re-interpreting user-supplied
    values (unlike str.format, which chokes on literal braces in values).
    """

    def _repl(m: re.Match) -> str:
        key = m.group(1)
        return values.get(key, m.group(0))

    return re.sub(r"\{([A-Z0-9_]+)\}", _repl, template)


def step_env() -> None:
    header("6 / 7  Environment configuration")

    env_path = Path(".env")
    current = _read_current_env()

    info("You will now be asked a few questions. Press Enter to accept the default.\n")

    # Auto-generate API key (reuse existing if present).
    api_key = current.get("API_KEY", "")
    if not api_key:
        api_key = secrets.token_urlsafe(32)
        info("Generated API key (saved to .env)")

    # Personalization
    assistant_user = ask("Your name (shown as the sender label; empty = 'You')", current.get("ASSISTANT_USER", ""))
    default_city = ask("Default city for weather", current.get("DEFAULT_CITY", ""))

    # Security: allowed Host header values (empty = auto-allow local names/IPs).
    trusted_hosts = ask(
        "Allowed Host headers, comma-separated (empty = auto-allow local host/IP)",
        current.get("TRUSTED_HOSTS", ""),
    )

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
        # --skip-llm ile gelindiyse STATE boş olur: makul defaults kullan.
        "LLM_BACKEND":        STATE.get("backend", "litert"),
        # LiteRT model IDs use dashes (gemma4-e2b); Ollama uses colons (gemma4:e2b).
        "LLM_MODEL":          STATE.get("model", "gemma4:e2b").replace(":", "-") if STATE.get("backend", "litert") == "litert" else STATE.get("model", "gemma4:e2b"),
        "LITERT_PORT":        str(LITERT_PORT),
        "DEFAULT_CITY":       default_city,
        "ASSISTANT_USER":     assistant_user,
        "TRUSTED_HOSTS":      trusted_hosts,
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
        "SSE_READ_IDLE_TIMEOUT",
        "LLM_MAX_TOOL_ITERATIONS", "LLM_REASONING_EFFORT", "LLM_MAX_OUTPUT_TOKENS", "ENV_PATH", "TRUST_X_FORWARDED_FOR", "EMBED_MODEL", "MEMORY_SIMILARITY_THRESHOLD",
        "HISTORY_LIMIT", "MEMORY_LIMIT", "SUMMARY_BATCH_SIZE", "SUMMARY_EARLY_TRIGGER",
        "CONVERSATION_RETENTION_DAYS", "MEMORY_RETENTION_DAYS",
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

    content = _fill_template(_ENV_TEMPLATE, values)
    for k, v in values.items():
        pattern = rf"^{re.escape(k)}=.*$"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, lambda _m: f"{k}={v}", content, flags=re.MULTILINE)

    env_path.write_text(content.strip() + "\n", encoding="utf-8")
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass
    ok(".env created / updated")

    # Lock down any pre-existing SQLite files (db / -wal / -shm / -journal).
    # The DB itself is created on first app start; db.py re-enforces this
    # on every startup, this is the install-time safety net.
    for p in sorted(Path(".").glob("*.db*")):
        try:
            if p.is_file():
                os.chmod(p, 0o600)
        except OSError:
            pass


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
        wants_litert = STATE.get("backend") == "litert" and os.path.exists("/etc/systemd/system/piserve.service")

        unit = f"""[Unit]
Description=piSynapse AI Assistant
After=network-online.target{" piserve.service" if wants_litert else ""}
Wants=network-online.target{" piserve.service" if wants_litert else ""}

[Service]
Type=simple
User={user}
WorkingDirectory={project_dir}
UMask=0077
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
        print(f"  {'LiteRT':12s}: {'systemd (active)' if os.path.exists('/etc/systemd/system/piserve.service') else f'background process on :{LITERT_PORT}'}")
    if os.path.exists("/etc/systemd/system/pisynapse.service"):
        print(f"  {'piSynapse':12s}: systemd (active)")
    if api_key:
        print(f"  {'API Key':12s}: saved to .env")
        print("    View it anytime with:  cat .env | grep API_KEY")

    print("\n  Start piSynapse:")
    print(f"    {activate}")
    print(f"    {run_cmd}")
    if backend == "litert" and not _litert_is_running():
        print("\n  piServe is not running — start it first in another terminal:")
        print(f"    {_litert_python()} {Path(__file__).resolve().parent / 'litert_serve' / 'server.py'}")
    if backend == "ollama" and not _ollama_is_running():
        print("\n  Ollama is not running — start it first:")
        print("    ollama serve")
    print("\n  Open http://localhost:8765 in your browser.")
    if api_key:
        print("  Enter your API key when prompted.\n")
    if os.path.exists("/etc/systemd/system/piserve.service") or os.path.exists("/etc/systemd/system/pisynapse.service"):
        print(f"  {'Manage':12s}: systemctl status piserve pisynapse\n")


# ── Entry ─────────────────────────────────────────────────────────────────────

def main() -> None:
    _parse_args()
    print(blue("\n  piSynapse Installer\n"))

    if BATCH_MODE:
        info("Non-interactive mode (--yes)")

    if not os.path.isfile("main.py"):
        error("main.py not found — run this script from the piSynapse project directory.")
        sys.exit(1)

    _detect_distro()
    step_python()
    step_system_deps()
    step_venv()
    if not SKIP_LLM:
        step_llm_backend()
    else:
        header("4 / 7  LLM backend — skipped")
    if not SKIP_TTS:
        step_tts_voices()
    else:
        header("5 / 7  TTS voices — skipped")
    step_env()
    if not SKIP_SYSTEMD:
        step_systemd()
    else:
        header("7 / 7  Systemd — skipped")
    print_summary()


if __name__ == "__main__":
    main()
