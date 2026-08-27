# Changelog

All notable changes to piSynapse will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/). This project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed (hardening, 17 fixes — parallel audit, no false positives, each 1 commit + 365 passed)
- **Security:** HEAD/OPTIONS auth bypass (`main.py:383`), Body-Size `Content-Length` missing bypass (`main.py:425` → 411), stored XSS `onclick` (`static/index.html:2940,2289` → data-* delegation), API key URL leak `/debug?k=` (`main.py:389` → body `_k`).
- **Logic:** duplicate-create race `llm/chat.py:280` per-call + cap 1, hallucinated tool `allowed_names` (`llm/chat.py:280`), `title.py:147` Ollama crash + hardcoded model, `retrieval.py:17` threshold/window, prompt injection `prompt.py:184` delimiters + Rule 15.
- **Consistency:** upload 4MB→100MB (`main.py:425`), trusted host empty bypass (`main.py:366`), `/sync` session_id validator (`routers/chat.py:547`), LIKE `safe_q` escape (`db.py:798`), `UI_LANGUAGE` sync (`config.py:374`), `.env` TOCTOU lock (`routers/config.py:148`).
- **Robustness/a11y:** calendar cache lock (`calendar_ops.py:22`), payload orphan trailing `tool_calls` (`llm/payload.py:184`), theme-swatch `role=button` + search/msg `aria-label` + modal `Esc` (`static/index.html:1563`).

## [1.7.0] - 2026-08-27

This cycle ships session UX (titles, retry, search) and hardens cross-cutting concerns:

### Added
- **Hybrid session titles (RAKE instant + LLM enriched):** first user message gets a <1ms RAKE title (`title.py`), then a background `httpx` LLM call replaces it with a 2-5 word topic title (dual-backend `litert`/`ollama`, 15 tokens, temp 0.1). Toggle `LLM_TITLE_ENRICHMENT` in Settings → Chat.
- **Regenerate button (ChatGPT-style):** `DELETE /chat/messages/last/{session_id}` + `delete_last_assistant` + dedup in `save_message`; frontend reuses `sendMsg()` (no duplicate SSE loop), `.bubble` fix, SW `v23→v28`.
- **FTS5 session search:** `conversations_fts` (`unicode61 remove_diacritics 2`, external-content), `search_sessions` with `snippet` + `LIKE` fallback, `GET /chat/search?q=`; frontend debounced 150ms single-layer (was 300ms dual-layer flicker) with `X-API-Key` and `AbortController 800ms` offline fallback.
- **Hybrid search (FTS5 + semantic):** `conversations.embedding` (`BLOB`, migration 6th, 353 backfilled), `save_message` embeds on write, `search_sessions` merges FTS (`AND` first, `OR` fallback) + semantic (`cosine≥0.50`, 200 recent, top 10) — cross-language `temperature`→`sıcaklık`, paraphrase tolerant, 90ms.
- **Offline search:** `navigator.onLine` fast-path + `online`/`offline` event listeners re-run search on transition; clear restores full list (no stale filter).
- **Snippet UI:** `renderSessions` shows FTS `<b>` snippet (11px, ellipsis) via `snippetMap`.

### Fixed
- **Search API path** `API+'/search'` → `API+'/chat/search'` (404 → 200; logs `GET /search 404`).
- **Search precision:** `OR` (18 hits for `omlet`) → `AND` first (1 hit), semantic threshold `0.35→0.50`, single-word disables semantic (was `teşekkürler` 0.637 false positive).
- **Title:** `requests` (sync, 15s loop block) → `httpx.AsyncClient` + `LITERT_URL`→`LITERT_BASE_URL` fix.
- **FTS rebuild:** every startup O(N) → conditional (detect `unicode61` via `sqlite_master`, drift `COUNT(*)`).
- **Config:** missing `LLM_TITLE_ENRICHMENT` module var + `sync_config` entry (always returned default).
- **CORS:** `allow_headers=["*"]` + credentials violates Fetch spec → explicit `["X-API-Key","Content-Type","X-Request-ID","Authorization"]`.
- **`_enrich_title` race:** `get_history(limit=3)` → `COUNT(*) ==2` (true total).
- **`NEXTCLOUD_TIMEOUT` 30→10** (fast fail; widget 17s→1.7s after `docker start redis`).
- **Search UI:** `s.id`→`s.session_id`, `e.dataset.sid`, `.bubble` vs `.msg-content`, `appendChild` before `attachMsgActions`, clear restores full list.

### Changed
- Search debounce 300→150ms, single-layer (no flicker, no kopukluk).
- SW cache `v23→v32`.

### Tests
- Suite 341→365 passing (`test_retry.py` 7, `test_title.py` 17).

## [1.6.0] - 2026-08-26

This cycle hardens tool-calling against small-model failure modes end-to-end:
detail-asking moved from static prompt rules to context-aware backend guards,
hallucinated/unoffered tools are rejected with guidance instead of executed,
duplicate creates became structurally impossible, and a new intent audit log
turns routing uncertainty into reviewable data. piServe enables constrained
decoding for tool-bearing turns. Test suite grows from 329 to 337 passing.

### Added
- **Intent audit log** (`intent_audit_log`): thin-margin and keyword-fallback
  classifications recorded (message/group/sim/margin/source) with 30-day
  retention, daily purge wired into the existing rollup loop; weekly review
  SQL shipped in NOTES
- **Escalation hardening**: bare-tool-name blurts join the TOOL_NEEDED marker
  as hatch triggers; group-scoped toolset selection on escalation; early
  abort of pure-chat rounds
- Hallucinated non-offered tools rejected with a guidance result instead of
  executing (observed in the field: create_task during a calendar turn wrote junk tasks)
- Creates/send_email capped at ONE identical execution per turn (duplicate
  'Yarın için görev' ×2 class)
- Chip-origin requests force clarify on create/send regardless of supplied
  params; decline replies ('yok / sadece oluştur') save title-only notes
- Deterministic instant chip clarify (LLM call skipped — model cost ~0 ms; see Perf for end-to-end wall time)

### Fixed
- **SSE relay swallowed all events after the first gen_retry** — escalated
  and retried rounds looked like empty replies to users
- **Task parser read fields from the VCALENDAR wrapper instead of the VTODO
  child** — every task displayed as 'Untitled', poisoning delete/complete
  flows
- Identical-execution counter incremented post-loop, letting two identical
  creates inside one response bypass the cap (single-shot cap landed earlier
  this cycle; this bypass was a flaw in its first implementation)
- Language mirroring recency bias: guard strings embed the user's original
  words as an anchor (TR stays TR on ollama-class backends)
- LiteRT server-side doubled-brace parse failures recovered from the error
  payload instead of failing the turn
- Boundary-safe ambiguous keywords ('kar' ⊂ 'çıkar'/'kart'; bare 'not' vs EN
  negation)
- complete_task card popped for delete requests (verb mapping pinned)

### Changed
- **UI_LANGUAGE default en** for fresh installs (existing settings untouched)
- Prompt: enumerated ask-if-missing instructions removed — dispatcher guards
  carry asking duty contextually (A/B verified identical outcomes);
  destructive tools pop confirmation cards directly, no textual 'are you
  sure'
- Verb-first notes corpus seeds (embedding sim 0.45→0.53 on mixed sentences)
- piServe passes ConstrainedDecodingConfig (LL_GUIDANCE) for tool-bearing
  conversations; tool results fed back in the template's structured
  tool_response form

### Perf
- Welcome-chip clarify wall time 15–40 s → ~2.4 s end-to-end (deterministic
  path, LLM skipped)

### Docs / Experiments
- FC Restructure Roadmap (8 items; 7 closed this cycle) + open verification
  register
- Benchmarks: constrained decoding ≈0 % overhead (ADOPTED); MiniLM vs E5-large
  intent comparison (E5 margins collapse — staying on MiniLM); operational
  rule for docker stop/start dependency restarts

## [1.5.0] - 2026-08-23

This cycle ships a backend-driven tool-call indicator, an intent-misroute
safety net for small models, and a full ambient-UI campaign. The SSE stream
schema gains two additive event types (`tool`, `gen_retry`); old clients
ignore them gracefully, so nothing breaks. Test suite grows from 302 to 329
passing tests.

### Added

- **Tool-call indicator**: the stream loop emits structured `tool`
  (start/end/refused, with attempt n/max against the identical-call cap) and
  `gen_retry` (overflow / empty / tool_leak / tools_escalated) events around
  every tool execution. The frontend renders a status pill directly above
  the typing dots — visible before streaming starts AND mid-stream for
  multi-tool chains, localized tr/en for all tools, WCAG-AA contrast in
  every theme including glass mode, dots dim while a tool runs, and the
  pill disappears the instant reasoning or reply tokens arrive.
- **Tool-escalation escape hatch**: intent routing stays fast, but pure-chat
  turns now carry a system note teaching a literal `TOOL_NEEDED` escape
  verb. When the model leaks function-call syntax or emits the marker, the
  round is cut mid-stream and redone once with the smallest sufficient
  toolset — group inferred from the leaked tool's name, else keyword
  heuristics on the user message, else the combined set. Escalated
  time-to-first-token drops from ~49s to ~13s whenever the domain is
  inferable; terminal text-only modes can never re-arm it. Verified
  identical on both the LiteRT and Ollama wire formats.
- **Ambient aurora campaign**: always-present color field with true
  freeze/resume (animations pause instead of detaching — no frame jump
  between replies), four drifting blobs, subtle playback speed-up while
  generating, faint idle washes so idle is never empty black,
  `prefers-reduced-motion` support, pure-black OLED default plus frosted
  glass-mode refinements.
- **Welcome chip lanes**: dual counter-scrolling marquee tracks with drag +
  fling physics (velocity inheritance, exponential decay, auto-resume),
  randomized anti-clump layout on every render, and taps that send directly
  — on desktop and mobile alike.
- Streaming caret, scroll edge-fade, silent sidebar refresh, per-message
  copy/TTS actions row.
- Permanent `Tool call:` INFO logging (params truncated) for diagnosing
  small-model tool behavior in production.

### Fixed

- **Float positions from LiteRT FC JSON** (`note_id: 1.0`) were rejected by
  the strict list-position parser, so reads/updates/deletes failed with
  "not found" even though the session listing was current. Integral floats
  and float-valued strings now resolve; fractional values are still
  rejected (regression-tested).
- **Desktop chip clicks never reached the chips**: pointer capture
  retargeted native clicks to the track element, so pressing a chip merely
  paused the marquee. Taps are now resolved manually at pointer-up;
  keyboard activation keeps working.
- Memory hygiene root cause: meta-requests ("remember to save this later")
  are no longer stored as user facts; additional leak variants (mangled
  delimiter tags, JSON tool_calls echoes) are stripped from streamed text.
- WCAG AA sweep: the pill done-state dimmed to 3.29:1 contrast (fail) and
  was restyled to 14.34:1; glass-mode pill backdrop hardened to ≥4.63:1
  worst-case; sidebar text3 contrast corrected.

### Changed

- Tool descriptions tightened −11% prompt tokens (combined set 2707→2411,
  notes group 728→671) without losing semantics: numbered-position
  protocol, confirmation warnings, enums, ranges and ISO examples intact.
- Service worker cache bumped to `pisynapse-v21`.

### Docs

- NOTES.md development journal rebuilt and tracked in git: file-purpose
  notice, verify-before-trust currency rules (strike through with a dated
  reason instead of deleting), Future Plan verified row-by-row against the
  code.

## [1.4.0] - 2026-08-22

This cycle hardens conversation integrity against small-model quirks: leaked
tool-call fragments no longer poison saved history or summaries, tool-call
repeat loops end in a real answer instead of an empty reply, and switching
between the LiteRT and Ollama backends keeps the configured model id in sync.
Test suite grows from 275 to 302 passing tests (+2 documented xfails).

### Added

- **Backend switch with model auto-mapping**: `LLM_BACKEND` is now selectable
  from the Settings UI (previously protected/edit-only). Switching engines
  validates `LLM_MODEL` against the NEW daemon's registry and, when the request
  does not pick a model explicitly, auto-maps separator variants (LiteRT
  `gemma4-e2b` ↔ Ollama `gemma4:e2b`). Previously a backend switch left the
  old id in place and every LLM call failed against the new daemon.
- `get_llm_model_options(backend=...)` override so model listings can target a
  daemon other than the currently running one.
- Loop-guard test suites for both execution paths plus an intent-pipeline
  suite covering the embedding layer, keyword heuristics and the LLM fallback
  on both backends.
- **Instance-level assistant language (`UI_LANGUAGE`)**: backend-generated
  user-facing strings (empty-reply fallback, engine error messages) are
  localized via a new `messages.py` catalog driven by a Settings option
  (`tr`/`en`, applied live without restart). History entries are therefore
  written in the instance owner's language, and the web UI adopts the same
  language by default when the visitor hasn't explicitly chosen one.
  Model-facing prompts stay English by design — small models follow English
  instructions best and users never see them; intent keyword heuristics
  remain intentionally multilingual detection data.
- **Per-message actions row**: assistant replies get copy-message and
  listen-to-TTS buttons side by side under the bubble — visible in every
  theme including the minimal chat view, where the old placement inside the
  hidden meta row made the TTS button vanish. Copy uses the async clipboard
  API with an `execCommand` fallback and shows localized copied feedback;
  service-worker cache bumped so clients pick up the new UI.

### Changed

- Minimal chat view: slightly more vertical breathing room between messages
  (24px → 34px).
- Direct Ollama calls that bypass the shared payload builder (intent LLM
  fallback, media STT transcription, model warmup) now send `think: false`
  explicitly — thinking-capable models otherwise burn their tiny
  `num_predict` budget on hidden reasoning before emitting any content.

- **Summary poisoning defense (3 layers)**: the running-summary prompt now
  instructs the summarizer to ignore tool-call artifacts, never invent details,
  prefer newer information on contradictions, and compress to ~3–5 sentences;
  the transcript fed to the summarizer is sanitized input-side (assistant
  messages stripped of leak fragments, fully-leaked lines dropped); the stored
  output passes through `strip_tool_leaks()`. Empty transcripts skip the LLM
  call entirely and keep the previous summary.
- Anti-loop guard constants (`finalize nudge`, fallback message, identical-
  execution cap) live in `llm/utils.py` and are shared by both chat paths.

### Fixed

- **History self-poisoning**: assistant replies containing leaked tool-call
  syntax (`<|tool_call|>` tags, bare `call:name{{}}` residues) were persisted
  verbatim and re-entered later prompts, triggering repeat loops and blank
  answers. Replies are now sanitized with `strip_tool_leaks()` before
  persisting on all save paths (stream completion/fallback and non-stream);
  replies that are entirely leak are not saved at all. A one-time database
  sweep removed previously poisoned rows.
- **Tool-call repeat loops** (streaming and non-streaming): when the model
  re-emits an already-executed tool call without producing any answer text,
  the loop now forces one text-only finalize round (a system nudge is appended
  and tools are disabled) instead of yielding an empty reply; if that round
  still produces nothing, a friendly retry prompt is returned instead of
  silence.
- **Identical-execution cap**: the exact same tool signature (name + sorted
  arguments) runs at most twice per request; further repeats are refused to
  the model via its tool-result channel while distinct calls in the same batch
  still execute — protecting side-effectful tools from runaway duplicates.
- `strip_tool_leaks()` whitespace collapsing no longer mangles fenced code
  blocks (collapsing now applies only outside ``` fences).
- Leak-recovery regex handles the doubled-brace `call:name{{}}` variant seen
  in saved history.
- **Ollama think-mode streaming was invisible**: Ollama ≥0.9 streams
  reasoning as `message.thinking`, but both chat paths only read the older
  `reasoning_content` alias, so the frontend never rendered the think flow
  on the Ollama backend. Both field names are now accepted (live-verified:
  reasoning deltas stream to the UI).
- **Intent classification on Ollama returned empty and slow**: without an
  explicit `think: false` the model spent its whole 20-token budget on
  hidden thinking (~45 s on CPU) and answered `raw=''`, always falling back
  to the `question` default. Classification now answers promptly with real
  content.
- Chat-path unit tests no longer touch the real SQLite database (fresh
  checkouts lack the schema), and a session-finish safety net closes any
  leaked connection so CI runs can no longer hang at interpreter exit with
  a non-daemon aiosqlite worker thread.
- The two remaining leak-variant blind spots (previously pinned as xfail)
  now sanitize correctly: mangled `<tool|call>` delimiter tags are consumed
  entirely, and standalone JSON echoes of tool_calls objects are removed at
  save time — strictly line-exact and known-tool-names-only, so legitimate
  JSON inside prose is never touched (regression-tested).

### Tests

- Suite expanded from 275 to 308 passing tests (zero xfails — both
  previously documented leak-variant limitations are fixed): history-hygiene
  variants with real save-path integration, summary hygiene, streaming and
  non-streaming loop-guard scenarios, Ollama think-stream parsing (stream and
  non-stream), intent classification across backends, settings backend-switch
  mapping, plus over-stripping regression tests; `ruff check` clean.

## [1.3.0] - 2026-08-22

This release hardens the whole stack after two independent audits: five
critical security fixes, a position-based tool-call architecture that removes
raw IDs from the model's view, full Ollama ↔ LiteRT backend parity for token
limits / retries / truncation signals, a mobile-ready API surface, and a
large frontend polish wave (touch-friendly hover handling, a monochrome
"Siyah" theme, an OLED black switch, a stop button for streaming replies and
a minimal chat view). Test suite grows from 242 to 275 passing tests.

### Added

- **Stop button for streaming replies** (`POST /chat/abort/{session_id}` +
  UI): the send button turns into a red stop control during an active SSE
  stream; aborting keeps the partial answer, updates the sidebar session
  name and shows a localized "stopped" notice instead of an empty-reply
  warning.
- **Chat API surface expansion**: documented OpenAPI contract for the chat
  endpoints, full session CRUD (create/rename/delete), multipart file
  upload, a `/sync` endpoint and rate-limit headers.
- **Backup/export endpoint** (`GET /chat/export`) and **memory pagination**
  (`limit`/`offset` on memory listing).
- **Per-session rate limiting** in addition to the existing per-IP limiter.
- **piServe admin protection**: `/v1/admin/config` and `/v1/admin/reload`
  require an `X-Admin-Token` header when `PISERVE_ADMIN_TOKEN` is set;
  loopback-only access remains the fallback when it is unset. Admin reload
  can also be triggered via SIGHUP.
- **Monochrome "Siyah" accent theme**: near-white accent on deeper-than-
  default dark surfaces; every accent-driven gradient (including the glass
  aurora) automatically turns into a faint white wash. Send/Save buttons get
  dark ink on solid fills while keeping white icons on glass-mode's
  translucent fills.
- **OLED black background switch** in the appearance settings: pure-black
  background/surface palette that composes with any accent theme; persisted
  separately from the theme choice.
- **Minimal view mode** ("Sade Görünüm") under advanced settings: hides the
  sender name and timestamp above every message for a cleaner chat.
- **Touch feedback parity**: all `:hover` rules are gated behind
  `@media (hover:hover)` so mobile no longer suffers sticky highlights;
  the logo glow gets an `:active` counterpart on touch devices.

### Changed

- **Position-based tool access (architecture)**: notes, tasks and calendar
  listings no longer leak database IDs/UIDs to the model. Tools now accept
  positional references (`_resolve_position`), ID lines are stripped from
  listings, and prompts/tool descriptions were rewritten accordingly. This
  removes the whole class of wrong-record edits caused by stale or truncated
  IDs.
- **Backend parity fixes (Ollama ↔ LiteRT)**:
  - Ollama payloads now honor `LLM_MAX_OUTPUT_TOKENS` via `num_predict`
    (previously silently ignored in main chat).
  - Think-mode retry on leaked tool calls works identically on both backends,
    is conditional on an actual leak (legit plain answers no longer pay an
    extra call), forwards `reasoning_effort` and preserves the tool group.
  - Ollama NDJSON error lines are raised instead of being swallowed as empty
    responses.
- **piServe model validation**: requests naming an unknown model return
  HTTP 409 with `allowed_models`; an empty/missing model silently falls back
  to the loaded one. Truncation is now reported as OpenAI-style
  `finish_reason: "length"` by scanning engine reason keys.
- **Voice transcription hardening** (`/transcribe-gemma4`): WAV codec is
  backend-aware (`pcm_s16le` for Ollama), context capped at 8192 for audio
  embedding, and failed/empty Ollama transcriptions fall back to local
  Whisper automatically.
- **Single-source numeric config**: `DEFAULT_LLM_NUM_CTX` (8192) and
  `DEFAULT_LLM_MAX_OUTPUT_TOKENS` (4096) constants feed settings schema,
  payload builders, trim budgets and the piServe installer template.
- **Focus management in the web UI**: hover styles carry `:not(:focus)` so a
  clicked button does not stay lit until you click elsewhere; keyboard users
  get a visible `:focus-visible` outline. Panel toggles (memory, menu,
  search, compact) are exempt so their glow fires on every re-hover.
- **Installer robustness**: cross-distro support, recovery from broken venvs,
  non-interactive mode, absolute `ExecStart` paths, and a fixed flow when
  systemd exists but the user declines it.
- Mobile screens use a deeper background palette across all themes (the
  Siyah theme goes one step further); desktop rendering is unchanged.

### Fixed

- Security: IMAP search injection (whitelist sanitization), unauthenticated
  `/debug` endpoint when `API_KEY` is empty, removal of the unsafe
  `pickle.loads` fallback for embeddings, sanitization of external content
  injected into prompts, and elimination of credential-leaking debug logs.
- `update_note` TypeError (category/tags were accepted by the schema but not
  forwarded); task listing cache no longer mixes completed/hidden views;
  note/task/calendar list caches are invalidated on create/update/delete;
  failed email sends report "ERROR: Failed to send." instead of silent
  success.
- Search box in the sidebar: replaced the fragile animated-collapse with an
  instant open + fade; nothing clips regardless of font zoom or device, and
  the magnifier icon sits inside the field again.
- Expanding a live think box now auto-scrolls to keep the revealed reasoning
  in view (when already near the bottom).
- In black theme + glass mode the send icon stays visible (white) instead of
  dark-on-dark.
- Performance: N+1 session count query, embedding backfill moved off the
  search path, calendar date-search caching and a two-phase memory search.

## [1.2.0] - 2026-08-16

This release replaces the stock `litert-lm serve` with a purpose-built
OpenAI-compatible backend (piServe) that raises the context window from 4096
to 6144 tokens, applies UI settings live without a restart, roughly doubles
decode speed via MTP speculative decoding, and adds persistent email ID
mapping plus a large batch of email-list, frontend and i18n polish.

### Added

- **piServe backend** (`litert_serve/`): a small OpenAI-compatible HTTP server
  wrapping `litert_lm.engine.Engine` directly. It replaces `litert-lm serve`,
  which hard-caps the KV cache at 4096 tokens and ignores `max_num_tokens`.
  piServe exposes only `/v1/models` and `/v1/chat/completions` (SSE streaming),
  passes tool schemas through via `RawSchemaTool` without executing them
  (piSynapse runs its own tool loop), and maps `reasoning_effort` to a
  thinking-token budget. Context is configurable and set to 6144 tokens.
- **MTP speculative decoding**: enabled for `gemma4-e2b`, roughly doubling
  decode throughput (7.8 → 15.9 tok/s measured).
- **Live settings**: the config module now exposes `config.get()`, and all
  consumers read values dynamically, so changes made in the Settings UI apply
  immediately without a service restart.
- **`LLM_MAX_OUTPUT_TOKENS`** setting (default 2048): caps output per reply.
  litert-lm ignores `max_tokens`, so chat payloads and summaries send
  `max_completion_tokens` instead, and the media TTS path forwards it too.
- **Persistent email ID mapping**: a new `email_session_map` SQLite table maps
  display list numbers to real IMAP IDs (replacing the 1-hour in-memory cache
  that died on service restarts). `read_email` accepts either `message_id` or
  `id`.
- **Think-mode tool-call leak recovery**: leaked `<|tool_call|>` fragments are
  parsed and the underlying tool is actually executed instead of being printed
  as raw text.
- Turkish as the default UI language on Turkish browsers
  (`navigator.language`), real Turkish labels in the settings schema, and
  localized connection/context error messages (`errConnLost`,
  `errContextTooLong`).

### Changed

- Context window raised to 6144 tokens (`LLM_NUM_CTX` default/max), with
  `LLM_TIMEOUT` raised to 600 s and the SSE idle timeout to 300 s to match the
  longer prefill/output window.
- Installer: writes `litert_serve/config.json` for the installed model,
  creates and enables `piserve.service`, and retires the legacy
  `litert.service`; `.env` template and defaults aligned to 6144.
- Email listing: raw IMAP IDs are never shown to the model; each item is one
  compact line (`N. From | Subject | Date | Preview`), double numbering is
  removed, and list numbers stay in sync across blocks (`<ol start>`).
- Settings UI: "Context Window" and "Max Output" are separate, documented
  options; advanced items gain inline descriptions.
- Ambiguous follow-ups ("tell me about the Ollama email") now route to the
  email tool through a deterministic `contextual_email_followup` rule instead
  of relying on the LLM fallback alone.
- Email bodies are cleaned of invisible Unicode control/spam characters and
  truncated to 1500 chars before reaching the model.
- Intent LLM fallback sends `max_tokens: 20` so a vague message costs a tiny
  classification instead of a full generation; the fallback backend defaults
  to `litert` (was `ollama`).
- Model name is shown in the sidebar; the think button was simplified to a
  single inline toggle (the 5-level picker stays dormant behind the flag).
- Service worker is served from the site root (`/sw.js`), fixing its scope so
  PWA updates actually cover the app.

### Fixed

- Empty-list rendering regression: list items vanished after a `renderMd`
  group-index change; numbers are now real text (`.ol-num` spans) so they also
  copy correctly.
- Email lists no longer truncated at ~600 tokens: the compact one-line format
  plus `max_completion_tokens` produce every requested item.
- `read_email` with a list number resolves through the DB map even after a
  restart; out-of-range fallback preserved.
- Invisible-character flooding (thousands of zero-width/spacing characters in
  emails) no longer blows the context budget or yields blank replies; the
  client also warns when the model returns an empty response.
- Embedding deserialization bug: raw float32 buffers whose first byte is
  `0x80` were misdetected as pickles, zeroing every cosine similarity;
  detection is now magic-byte based (`.npy` / raw buffer / pickle).
- Context overflow mid-stream triggers a shrink-and-retry instead of a silent
  empty reply.
- Config `PATCH` writes are atomic; tool-group metadata flows through the
  streaming tool path; `tools/__init__.py` exports `is_tool_success`/`_as_bool`.
- Tool audit: `execute_action` calls are audited and verified, confirm-modal
  branches sanitize exceptions, and PII keys (`body`, `content`, `text`,
  `password`, `token`, `api_key`, …) are redacted from mail and audit logs.
- CodeQL findings: startup no longer logs the trusted-host IP list, and file
  paths are normalized before permission checks.

### Removed

- Dead code verified and deleted: `install_prod.py`, `web_release.py`,
  `client_script/README.md`, `templates/render_settings.html`.

### Tests

- Suite expanded from 158 to 239 tests (email ID resolution, leaked tool-call
  parsing, dispatcher branches, PII redaction, media streaming, live payload
  sampling); `ruff check` clean.

## [1.1.1] - 2026-08-16

This release bundles the tool-execution verification layer, the tool audit
log, the health + semantic retrieval work, and the hardening from a
multi-session stability audit (30 findings).

### Added

- Tool-execution verification (`tool_verification.py`): every tool call is
  checked by a `run_verification()` hook embedded in both tool-call loops
  (stream + chat). It runs after each call and can never raise or stall
  execution.
- Tool audit log: a new SQLite `tool_audit_log` table records every tool call
  (tool name, params, success, duration, error). Detail rows older than
  14 days are rolled up into per-day summary rows — once at startup and then
  automatically every 24 hours.
- `/health` endpoint: reports `healthy`/`degraded` with live checks of the
  database, LLM backend and Nextcloud. The frontend shows a status dot
  (green/yellow/red) that polls every 60 s and names the failing dependency.
- Semantic history retrieval (`retrieval.py`): mitigates
  "lost-in-the-middle" by replacing the middle of the context window with the
  top-k most relevant older messages, using FastEmbed embeddings + cosine
  similarity. Runs in parallel with history loading under a 1500 ms
  best-effort budget and falls back gracefully on any error.
- Frontend staleness scan for the calendar widget: a client-side 60 s timer
  drops events whose start time has passed, so the ticker no longer gets
  stuck on the first event of the day (no extra network requests).
- Daily retention cleanup (conversations/memories) now runs on a background
  timer, not only at startup.
- CalDAV/notes/tasks clients and Whisper/Piper models load under a lock and
  off the event loop (no request-path blocking).
- Transcribe uploads stream to a temp file in chunks and are capped by
  `MEDIA_MAX_MB` (default 100 MB; was a hard-coded 25 MB).

### Security

- Host-header allowlist (`TRUSTED_HOSTS`): the default `"*"` (host check
  disabled) is replaced with an empty allowlist that auto-accepts only this
  machine's local IPs/hostnames; any other Host header is rejected with 403.
  Add your public domain to `TRUSTED_HOSTS` when exposing the server.
- `/debug` beacon endpoint now requires the API key via `?k=` query param
  (the auth-exempt telemetry path), is rate-limited and its body is capped
  at 8 KB.
- Settings API rejects values containing newlines (`.env` injection) and
  writes `.env` under a file lock.
- Database files (`.db`, `-wal`, `-shm`, `-journal`) are created and kept
  owner-only (`0600`) via process umask, a startup re-check and systemd
  `UMask=0077`.
- Tool audit log no longer stores raw user content: sensitive param keys
  (`body`, `content`, `text`, `password`, `token`, `api_key`, …) are stored
  as `[REDACTED]` and serialized params are capped at 2048 chars.
- Tool-call leak hardening: literal `<|tool_call|>` tags and JSON
  `"name": "tool"` echoes are detected and suppressed mid-stream; tools can
  only be dispatched from real parsed `tool_calls` (regression test for a
  historical bug). A regex-based action-claim detection was tried and removed
  in favor of this loop-level hardening.

### Fixed

- Retrieval now honors `TIME_BUDGET_MS` via `asyncio.wait_for` with a graceful
  fallback instead of only logging a warning.
- Query embedding is computed once per message and shared across retrieval,
  memory search and intent classification.
- Retrieved context is merged chronologically with recent messages
  (`merge_history` now used in production).
- Tool audit rollup is atomic per day and idempotent (no duplicate summaries).
- SMTP send retries with a fresh connection per attempt; SSE reads have a
  120 s idle timeout so a stalled model cannot hang the stream.
- `build-essential` detection uses `dpkg -s` with `gcc`/`make` fallback
  instead of a check that always failed; the installer no longer drops
  `CONVERSATION_RETENTION_DAYS`/`MEMORY_RETENTION_DAYS` on re-run.
- `.env` regeneration is safe against braces/backslashes in values.
- Various: weather geo-cache LRU bound, warmup HTTP client closed,
  opportunistic VACUUM, calendar widget today-cache, clearer Nextcloud error
  messages, ambiguous calendar event matches reported instead of silently
  picked.

### Tests

- Suite expanded from 27 to 158 tests; `ruff check` clean.

## [1.1.0] - 2026-08-14

### Added

- Gemma4 think mode now uses the native LiteRT-LM `reasoning_effort` API
  (`medium` on, `none` off) instead of a system-prompt injection. Reasoning
  runs model-side and is stripped from responses (no leaks).
- Think button redesigned as a split pill: the bolt toggles thinking on/off at
  the configured effort. A caret opens a popover with a discrete 5-level
  slider (`Düşük`/`Orta`/`Yüksek`/`Maksimum` = `low`/`medium`/`high`/`xhigh`;
  effort is sent per-request via `reasoning_effort` and validated against
  `("none","minimal","low","medium","high","xhigh")`). The slider is currently
  hidden behind the `THINK_EFFORT_PICKER` flag: litert-lm 0.15 maps every
  enabled level to the same automatic token budget (litert b/514760339), so
  the picker is dormant until per-level budgets land — the flag flips it back
  on with one change, the full UI→router→payload→litert chain already works.
- Reasoning is streamed live into a dimmed, collapsible "Thinking" box under
  the response, and is saved with the message so it survives a reload.
- `LLM_REASONING_EFFORT` setting in the UI (Model group): pick the Gemma4
  thinking level (`none`, `minimal`, `low`, `medium`, `high`, `xhigh`) used
  when Think mode is on. Live-updates via the settings API, no restart needed.
- LiteRT payload now also sends `top_p`/`top_k` (previously only temperature).
- Client error beacon: `window.onerror`/`unhandledrejection` and init-stage
  events are POSTed to a new auth-exempt `/debug` endpoint and logged as
  `DBG|` lines, so future frontend failures are visible server-side instead of
  leaving a silent blank page.
- LiteRT-LM runtime patch (external to this repo): the model's `thought`
  channel is exposed as `delta.reasoning_content` (streaming) and
  `message.reasoning_content` (non-streaming).
- Unit tests for payload construction, per-request effort precedence,
  think-mode forwarding, tag stripping, and reasoning cleaning.

### Changed

- Reasoning is display-only: it is persisted and shown in `/chat/history`, but
  never included in the model context (`get_history` defaults to excluding it).
- A streaming reply that includes reasoning is only marked saved once the full
  answer arrives, so partial-interrupt fallbacks no longer drop reasoning.
- Ollama's `message.reasoning_content` is parsed like LiteRT's, so both
  backends expose thinking uniformly.
- Settings window reworked: fixed title bar, scrollable body with rounded
  scrollbar (no more corner overflow), pinned action bar, on/off options now
  render as toggle switches, and confusing options moved to a collapsible
  "Advanced Settings" section with info buttons that explain each option's
  effect, direction and default.
- Think box is collapsed by default during streaming and can be toggled live.
- STT "Gemma4" label no longer claims voice emotion awareness: emotion/tone/mood
  are inferred from the transcript content, not from vocal prosody.
- Qwen3-specific think-mode remnants (`/no_think`, "qwen3" checks) removed, and
  `_THINKING_STRIP_RE` also strips Gemma 4 `<|channel>thought ... <channel|>` tags.
- `LLM_TIMEOUT` default raised to 240s to accommodate model-side reasoning.
- Service worker cache bumped to `pisynapse-v3` so stale cached pages no longer
  outlive fixes across hard refreshes.
- Installer `.env` template now matches the running config: it includes
  `LLM_REASONING_EFFORT`, `ENV_PATH` and `TRUST_X_FORWARDED_FOR`, and raises
  `LLM_TIMEOUT` to 240s (the old hardcoded 120s could cut off model-side
  reasoning on fresh installs).
- Message input bar is responsive. Desktop: the (think)/(attach) buttons, an
  auto-growing textarea (min ~40px, max 200px, scrolling internally beyond
  that) and the (mic)/(send) buttons share one flex row, bottom-aligned so the
  buttons stay put while the textarea grows. Mobile: the textarea takes its own
  row and the buttons move below it ((think)/(attach) left, (mic)/(send)
  right-aligned), handled purely by a media query + flex wrap/order.

### Fixed

- Blank-page crash: `applyLang` set `lbl-advanced`'s text, but that element only
  exists once the settings form is rendered — at first load it was `null` and
  the unguarded `textContent` assignment aborted app init (`Cannot set
  properties of null (setting 'textContent')`). Guarded; the beacon above is
  what made the failure visible.
- Think popover overflowed past the left screen edge on narrow windows; it is
  now anchored to the button (left-aligned) with the arrow under the caret.
- A `401` while loading the session list (missing/invalid API key) now renders
  an auth-needed state with a "re-enter key" action instead of failing silently.
- Heavy `backdrop-filter` blur caused input jank on touch devices; blur is
  reduced or removed for panels/controls under `@media (hover:none)`.
- A mobile swipe starting inside the think popover could trigger the sidebar;
  swipes originating in the popover are now ignored by the sidebar handler.

### Removed

- `release.sh` (orphaned rsync release-builder; not referenced by CI or docs;
  recoverable from git history if ever needed).

## [1.0.0] - 2026-08-13

First full release — an offline-first, self-hosted personal AI assistant.

### Added

- Web UI: chat, sessions, memory panel, think mode, EN/TR languages,
  frosted-glass theme with 5 accent colors
- Long-term memory with semantic search and deduplication (local embeddings)
- Voice input (Whisper / Gemma4) and voice output (Piper / browser)
- Image upload (drag-drop, paste, attach)
- Tool calling: weather, calendar (CalDAV), email (Gmail / Proton),
  notes & tasks (Nextcloud), memory
- Intent classification (embeddings + optional LLM fallback)
- PWA (installable, offline caching)
- API-key auth, rate limiting, trusted-host enforcement
- Interactive installer (`python3 install.py`) with systemd service support
- Unit tests (pytest)

### Fixed

- Email integration is now opt-in by default (`MAIL_PROVIDER` defaults to off)
- Settings UI can turn email integration back off
- Installer writes a consistent LiteRT model id (`gemma4-e2b`)
- Installer verifies the model import and that the server serves it
- Installer prompts to start the Ollama server when it is not running
