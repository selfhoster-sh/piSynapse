# Mail accounts under multi-user (decision 2026-09-09)

## Findings
- Hydroxide (emersion/hydroxide): upstream repo ARCHIVED 2026-08-02 (read-only,
  moved to Codeberg community). IMAP support self-declared work-in-progress.
  Proton API drift risk with no maintainer. REJECTED as a dependency.
- Official ProtonMail Bridge: actively maintained (v3.25.0, 2026-06-01),
  multi-account capable, already the server's Proton path
  (PROTON_IMAP_HOST=localhost:1143). No change needed on the transport side.
- Current server state: ONE shared mailbox (single MAIL_PROVIDER credential
  pair in .env) served to every chat caller — violates the invisibility rule
  for non-admin users.

## Decision
1. Hydroxide: no. Stay on official Bridge (Proton) + direct IMAP (Gmail).
2. [SUPERSEDED — implemented below] Shared mailbox was briefly admin-only.
3. [IMPLEMENTED 2026-09-09] Per-user mail accounts: `credstore.py` (Fernet,
   `MAIL_CREDS_KEY` in .env, never plaintext in DB); Gmail per-user = app
   password; Proton per-user = Bridge-registered account + its bridge
   password. Resolution: personal creds → legacy shared mailbox (admins;
   backward compatible) → clear "not configured" error. Anonymous refused.

## Proton Bridge multi-account (verified 2026-09-09)
One Bridge instance serves unlimited PAID accounts (free plans have no Bridge
access): each added account gets its own bridge password in its own
configuration panel, and IMAP login selects the account by address — all on
the same localhost:1143/1025. So the per-user (address + bridge password)
model is correct with one operational requirement: the admin adds each
user's Proton account to the Pi's Bridge once (Bridge GUI/CLI `+`), and the
user pastes THEIR account's bridge password. Gmail users need nothing
server-side (direct IMAP + app password).

## Changed
- `credstore.py` + `user_credentials` table + own-only CRUD endpoints.
- `tools/dispatcher.py`: personal → shared(admin) → not-configured resolution.
- `tests/test_credentials.py` (6 tests incl. wrong-key unreadability).
