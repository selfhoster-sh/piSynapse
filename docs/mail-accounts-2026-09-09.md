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
2. Now: shared mailbox is ADMIN-ONLY. `_run_mail_tool` refuses resolved
   non-admin callers and anonymous callers with
   "ERROR: Email is available to the server admin only." Unresolvable ids fall
   through (legacy single-user flows use opaque caller labels; HTTP middleware
   already guarantees production callers are real users).
3. Later (needs approval — new secrets architecture): per-user mail accounts.
   Requirements: encrypted per-user credential store (Fernet, key in .env,
   never plaintext in DB); Gmail per-user = app password (trivial); Proton
   per-user = each account added to the shared Bridge by the owner (outside
   this app) + per-user bridge password in the encrypted store.

## Changed
- tools/dispatcher.py: gate at top of `_run_mail_tool`.
- tests/test_auth_helpers.py: deny non-admin, deny anonymous, allow
  unknown-id compat (3 tests).
