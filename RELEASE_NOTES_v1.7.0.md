# v1.7.0 — Hybrid Titles / Search / Offline + Hardening

**Summary:** Session UX (titles, retry, search) and resilience.

## Added
- **Hybrid titles (RAKE <1ms + LLM):** instant RAKE on first message, then background `httpx` LLM (15 tokens, 0.1) 2-5 word topic. Toggle `LLM_TITLE_ENRICHMENT` (Chat).
- **Regenerate (ChatGPT-style):** `DELETE /chat/messages/last/{id}` + dedup, frontend reuses `sendMsg()` (`.bubble` fix), SW `v23→v28`.
- **FTS5 search:** `conversations_fts` (`unicode61 remove_diacritics 2`), `snippet` + `LIKE` fallback, `GET /chat/search?q=`, debounced 150ms single-layer, `AbortController 800ms` offline fallback.
- **Hybrid search (FTS5 + semantic):** `conversations.embedding` (BLOB, 353 backfilled), `save_message` embeds on write, `search_sessions` `FTS AND→OR` + `cosine≥0.50` (200 recent) — cross-language `temperature`→`sıcaklık`, 90ms.
- **Offline search:** `navigator.onLine` fast-path + `online`/`offline` listeners, clear restores full list.
- **Snippet UI:** `renderSessions` shows FTS `<b>` snippet (11px, ellipsis) via `snippetMap`.

## Fixed
- `API+'/search'` → `API+'/chat/search'` (404).
- `OR` (18 hits) → `AND` first (1 hit) + semantic `0.35→0.50`, single-word disables semantic.
- `requests` (sync) → `httpx.AsyncClient` + `LITERT_BASE_URL` fix.
- FTS every-startup `REBUILD` O(N) → conditional (`unicode61` + `COUNT` drift).
- Missing `LLM_TITLE_ENRICHMENT` var/sync.
- CORS `allow_headers="*"` → explicit `["X-API-Key","Content-Type","X-Request-ID","Authorization"]`.
- `_enrich_title` race `limit=3` → `COUNT(*)==2`.
- `NEXTCLOUD_TIMEOUT 30→10` (widget 17s→1.7s).
- `s.id`→`s.session_id`, `e.dataset.sid`, `.bubble` vs `.msg-content`, `appendChild` before `attachMsgActions`.

## Changed
- Debounce 300→150ms, single-layer (no flicker).
- SW `v23→v32`.

## Tests
- 341→365 (`test_retry.py` 7, `test_title.py` 17).

## Install
```bash
cp example.env .env && nano .env  # LLM_TITLE_ENRICHMENT=on added
python3 install.py
sudo systemctl restart pisynapse
```
