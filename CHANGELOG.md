# Changelog

All notable changes to piSynapse will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/). This project
uses [Semantic Versioning](https://semver.org/).

## [1.0.2] - 2026-08-14

### Added

- `LLM_REASONING_EFFORT` setting in the UI (Model group): pick the Gemma4
  thinking level (`none`, `minimal`, `low`, `medium`, `high`, `xhigh`) used
  when Think mode is on. Live-updates via the settings API, no restart needed.

### Changed

- STT "Gemma4" label no longer claims voice emotion awareness: emotion/tone/mood
  are inferred from the transcript content, not from vocal prosody.

## [1.0.1] - 2026-08-14

### Changed

- Gemma4 think mode now uses the native LiteRT-LM `reasoning_effort` API
  (`medium` on, `none` off) instead of a system-prompt injection.
  Reasoning runs model-side and is stripped from responses (no leaks).
- Qwen3-specific think-mode remnants (`/no_think`, "qwen3" checks) removed.
- `_THINKING_STRIP_RE` also strips Gemma 4 `<|channel>thought ... <channel|>` tags.
- `LLM_TIMEOUT` default raised to 240s to accommodate model-side reasoning.

### Added

- Unit tests for payload construction, think-mode forwarding, and tag stripping.

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
