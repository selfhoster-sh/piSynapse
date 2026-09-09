# Multi-User Plan — M1–M4 (2026-09-09)

Status: M1 and M2 implemented (see NOTES.md entries for deviations,
residuals and test evidence). M3–M4 pending.

Decisions (user): open registration with an admin toggle (standard);
existing `default` data belongs to the admin (bootstrap onto the `default`
identity — zero row moves); all phases in one plan, in order.
Iron rule (user): **one user's sessions are invisible to every other user.**

## M1 — Identity (this phase)
- M1a: `users` table (id PK incl. reserved `default`, name, key_hash UNIQUE,
  is_admin, created_at) via `CREATE TABLE IF NOT EXISTS` (no migration
  entry needed for a new table) + key utils (`generate_api_key`,
  `hash_api_key` SHA-256, `verify`) + unit tests.
- M1b: `POST /users/register` (honors `REGISTRATION_OPEN`, default true;
  first user becomes admin), `POST /users/key/rotate` (auth-bound, returns
  the new key ONCE), `GET /users/me`. Registration closed → 403.
  Admin bootstrap: if `users` empty, first registration is admin; the
  pre-existing `default` identity becomes admin on first run (idempotent
  ensure step, no data rewrite).
- M1c: auth middleware resolves keys via DB (`key_hash` lookup + small TTL
  cache) instead of only the single `.env` key; `.env` `API_KEY` keeps
  working and maps to `default` (backward compatible). Unknown keys → 401
  (no silent `default` fallback for non-empty keys).
- Tests: key lifecycle, toggle open/closed, bootstrap admin, middleware
  mapping incl. cache invalidation on rotate.

## M2 — Isolation completion
- Rate limits keyed by `user_id` (fallback IP for unauthenticated/health);
  rpm values to env (`RATE_LIMIT_RPM_*`, same defaults 30/20/120).
- `user_id` column + backfill (owner from `sessions`) on the 4 map tables;
  dispatcher + prompt read/write paths filter by it; `clear_history`
  cascade extended.
- `user_id` on `tool_audit_log` (migration + backfill via `conversation_id`);
  `_last_executed_tool_group(session_id, user_id)` + caller threading.
- litert conversation-cache key becomes `user_id:session_id` (opaque to
  litert; sent only when caching enabled).
- Session-invisibility tests: list/read/rename/delete/history/summary/search
  across two users — every direction returns empty/untouched.
- Remove vestigial `user_id` query params (auth-bound `_uid` is the source).

## M3 — Per-user settings
- `user_settings(user_id, key, value)` + `UNIQUE(user_id, key)`; taxonomy:
  personal (`UI_LANGUAGE`, `ASSISTANT_USER`, `DEFAULT_CITY`, `STT/…_ENGINE`,
  `TTS_*`, `AUTO_*`) per-user, rest global `.env`.
- `GET/PUT /config/my-settings` (auth-bound); `PATCH /config/settings`
  becomes admin-only.
- Prompt/context assembly reads per-request user settings (city/name/
  language); `DEFAULT_USER` fallback preserved for key-less paths.
- Migration: existing `.env` personal values seed the admin's rows once.

## M4 — Verification & docs
- Full suite green + new tests (registration flows, per-key limits, map
  isolation, settings precedence, migration on a legacy fixture DB).
- Capacity guide (Pi 5: 2–3 concurrent active users practical ceiling;
  bigger hardware scales with model/RAM; rpm tunables).
- `docs/remote-access.md` multi-user note (per-user keys per device).
- Out of scope (server phases): phone-app login UI (needs key-entry
  screen — separate track after the port decision).

## Security notes
- Keys stored as SHA-256 hash only; comparison via `hmac.compare_digest`;
  rotation invalidates cache; auth failures 401 without user enumeration
  (identical response for bad key vs unknown user).
- Registration rate-limited strictly (anti-enumeration/brute-force).
