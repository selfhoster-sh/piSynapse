# Changelog

All notable changes to piSynapse will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/). This project
uses [Semantic Versioning](https://semver.org/).

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
- Interactive installer (`python install.py`) with systemd service support
- Unit tests (pytest)

### Fixed

- Email integration is now opt-in by default (`MAIL_PROVIDER` defaults to off)
- Settings UI can turn email integration back off
- Installer writes a consistent LiteRT model id (`gemma4-e2b`)
- Installer verifies the model import and that the server serves it
- Installer prompts to start the Ollama server when it is not running
