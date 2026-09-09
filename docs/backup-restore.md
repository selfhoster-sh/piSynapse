# Backup & restore

Automatic online backups run at startup and daily (sqlite3 online-backup
API over a dedicated read-only connection, owner-only `0600`):

- Location: `backups/piSynapse-auto-YYYYMMDD.db` next to `assistant.db`
  (or `AUDIT_EXPORT_DIR`'s sibling when `DB_PATH` is overridden).
- Retention: newest 7 generations are kept, older ones pruned automatically.
- Manual pre-upgrade backup: `sqlite3 assistant.db ".backup 'backups/manual-$(date +%F).db'"`.

## Restore

1. Stop the service: `sudo systemctl stop pisynapse`.
2. Copy the chosen generation over the live DB (keep a copy of the
   corrupt file first for forensics):
   `cp assistant.db /tmp/assistant-corrupt.db && cp backups/piSynapse-auto-YYYYMMDD.db assistant.db && chmod 600 assistant.db`.
3. Start: `sudo systemctl start pisynapse`.
4. Verify: `/health` reports `healthy` (a failed `PRAGMA quick_check`
   would otherwise keep it `degraded` with a `startup_error` field).

## Notes

- `VACUUM INTO` produces a compacted copy; it never locks writers out.
- Never restore a backup over a running server: stop it first.
- `assistant.db-shm` / `-wal` sidecars are rebuilt automatically; do not
  back them up or restore them.
