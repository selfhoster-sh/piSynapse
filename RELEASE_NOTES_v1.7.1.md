# v1.7.1 — Hardening (17 fixes, parallel audit)

**Audit:** 2 agents + manual, very thorough, no false positives. Backend 11 + LLM 7 + frontend 2 critical XSS.

## Security
- `main.py:383` HEAD/OPTIONS bypass → only `OPTIONS + Access-Control-Request-Method` exempt.
- `main.py:425` Body-Size missing `Content-Length` bypass → `411` required.
- `static/index.html:2940,2289` stored XSS `onclick='${esc()}'` → `data-*` + delegation.
- `main.py:389` `/debug?k=` URL leak → `sendBeacon` body `_k` + header/body/query check.

## Logic
- `llm/chat.py:280` duplicate-create race per-call + `create` cap 1 (was post-loop).
- `llm/chat.py:280` hallucinated tool `allowed_names` (stream parity).
- `title.py:147` Ollama `use_tools` TypeError + hardcoded `gemma4-e2b` → dynamic.
- `retrieval.py:17` `SIM 0.20→0.35`, `RECENT 8→6`, `TOP_K 6→4`, `timestamp→id`.
- `prompt.py:184` untrusted email delimiters `--- BEGIN/END UNTRUSTED ---` + Rule 15.

## Consistency / Robustness
- `main.py:425` `_large_body_paths` add `/chat/upload` (4MB→100MB).
- `main.py:366` `if host and ...` → `if not host or ...` (empty Host).
- `routers/chat.py:547` `/sync` `session_id` validator.
- `db.py:798` LIKE `safe_q` + `ESCAPE '\'`.
- `config.py:374` `sync_config` add `UI_LANGUAGE`.
- `routers/config.py:148` `.env` TOCTOU read-before-lock → inside `LOCK_EX`.
- `calendar_ops.py:22` `_cache_lock` + `llm/payload.py:184` orphan drop.
- `static/index.html:1563` `theme-swatch` `role=button`, `aria-label`, modal `Esc`.

## Tests
- 365 passed, `py_compile` ok, `ruff` main clean, `health` `db ok, llm ok`.

## Upgrade
```bash
git pull && sudo systemctl restart pisynapse
# .env new: LLM_TITLE_ENRICHMENT=on (added to install.py/example.env)
```
