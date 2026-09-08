"""Single-source-of-truth contracts across files that cannot import each other.

install.py must stay stdlib-only (it runs before dependencies exist), so these
checks parse the files as text instead of importing them. If any assertion
fails, update the offending file — never weaken the test.
"""

import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(name: str) -> str:
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def _env_literal(content: str, key: str) -> str:
    m = re.search(rf"^{key}=(\S+)\s*$", content, re.M)
    assert m, f"{key}= literal not found"
    return m.group(1)


def test_embed_model_single_source():
    install_py = _read("install.py")
    example_env = _read("example.env")
    config_py = _read("config.py")
    embedding_py = _read("embedding.py")

    from_template = _env_literal(install_py, "EMBED_MODEL")
    from_example = _env_literal(example_env, "EMBED_MODEL")
    m = re.search(r'EMBED_MODEL = os\.getenv\("EMBED_MODEL", "([^"]+)"\)', config_py)
    assert m, "config.py EMBED_MODEL default not found"
    from_config = m.group(1)

    assert from_template == from_example == from_config, (
        f"EMBED_MODEL drift: install.py={from_template} example.env={from_example} "
        f"config.py={from_config}"
    )
    # embedding.py must not define its own default (it poisoned cosine scores).
    assert "from config import EMBED_MODEL" in embedding_py
    assert 'os.getenv(\n    "EMBED_MODEL"' not in embedding_py
