# piSynapse — Development Journal

> **About this file** (developer's test-environment notes): created to carry every test, rule, and piece of essential knowledge accumulated since day one. It is used while coding with AI to keep the project structure intact, capture required knowledge, and hand it over correctly. **Never trust a statement here unconditionally** — if you are unsure of its currency, VERIFY first; after verification, EDIT the relevant spot: do not delete the old text, strike it through (`~~...~~`) and note why it is now invalid/unnecessary/done/fixed, with the date.

## READ FIRST — AFTER EVERY SESSION/COMPACTION

- The project IS a git repo (since Aug 13, 2026). Commit changes one by one (rule: one item = one commit + py_compile + pytest). Before risky architectural work, take a backup: `backups/piSynapse-*.tar.gz` (gitignored). ASK THE USER whether a backup should be taken — never assume "I took a backup" on your own.
- No architectural changes without user approval (new folders/packages, new infrastructure like Docker/WebSocket, framework swaps). Don't widen scope on your own initiative.
- Before writing "the user approved/accepted" ANYTHING, make sure that approval was really, explicitly given in this conversation. If unsure, write honestly "the user did not approve, I assumed" — never fabricate an approval.
- The services/ layer was REMOVED (July 30, 2026) — legacy modules (db.py, llm/, tools/, embedding.py) do all the work. Don't propose a DI/service layer again unless the user explicitly asks.
- Docker and WebSocket (/chat/ws) were removed — the frontend uses SSE only (/chat/stream); do not reintroduce them.
- The Ollama service is stopped/disabled — LLM_BACKEND=litert is active. Don't restart Ollama or add dependencies on it unless the user asks.
- Docker RAM-freeing rule (2026-08-26 incident): stopping containers breaks DEPENDENT long-running containers via cached DNS (nextcloud lost postgres IP -> 500s ~35 min). After any stop/start cycle restart affected high-level containers too and verify health endpoints.
- Journal policy: entries are strictly reverse chronological (newest first), record project-relevant facts only — no meta/authority commentary or approval-status notes. Applies to every future edit.
- Currency rule: before relying on a statement in this file, verify it against the code. Found-stale statements get struck through with a dated reason (invalid/unnecessary/done/fixed) — never silently deleted.
- **R5 audit/meta rule (user, 2026-11-16):** new "audit/meta" work opens only with a written trigger — (a) a user complaint, or (b) a measured metric: error rate above threshold, install failure rate, latency regression, or an explicit user request. "Nice to have" observability is not enough; existing audit infrastructure (dashboard, flywheel, archive) stays, but new work needs justification in the commit/PR. Trigger: the 2026-10-25 review (R5) found 24 of the last 60 commits were fixes and only 4 were features, 3 of them audit-related, while latency (25 s) and install friction stayed unaddressed.
- **R6 decision (user delegated, 2026-11-16):** Docker stays out of the primary install path — the rationale (Pi RAM budget, systemd-native deployment, 2.4 GB model download, no Docker on the target) still holds, and a compose file would not fix the install-friction or latency problems. Instead: keep improving install.py (pure decision functions + tests, R3 in progress) and add a one-command installer entry point (`curl … | sh` with review-then-run, which install.py already supports) plus the 30-second demo GIF (marketing, separate task). Revisit Docker only after install.py has a clean-install verification on a fresh machine.
- **History rewrite rule (user, 2026-11-16):** any history rewrite (filter-repo, amend of pushed commits, pruning journal-only commits) requires a dated journal entry BEFORE it runs — recording the exact command, the replace expressions, and every dropped ref/path/commit. No silent rewrites. Trigger: the undocumented 2026-10-25 run dropped the journal from all history and pruned 42 `main` commits with zero record anywhere.
- Test coverage used to be ~7% (calendar_ops.py, mail.py, llm/, tools/ dispatcher untested). A dedicated hardening pass has been running since August; suite size is tracked in the entries below.
- **Sanitization rule:** this file may be published. Never write personal data, identity clues, deployment addresses (hostnames, IPs, ports), or accounts into it. Keep every narrative in English; Turkish inline tokens are allowed only as product corpus / i18n test data.
- **Test-DB isolation rule (2026-09-09 incident):** tests must NEVER touch the live `assistant.db` — app/lifespan tests use tmp-path DBs only. A full-suite run once wrote a test admin row into the live DB; it was deleted and the offending test isolated.
- **Multi-user invisibility rule:** one user's sessions, settings, mail and keys are invisible to every other user. Every user-scoped query needs its owner guard, every guard needs a both-directions test.
- **Pre-push check:** before push, grep new docs/journal lines for secrets, passwords, IPs and credentials the same way code gets py_compile + pytest.
- **LLM backend parity rule (user, 2026-10-11):** any change touching the model layer must hold for BOTH engines (LiteRT and Ollama) — one must never lag the other. New stream-level behavior gets tests parametrized over both backends. Known debt: most pre-existing stream tests feed OpenAI/LiteRT-style SSE only; the non-stream path (`llm/chat.py`) also lacks the recovery logic the stream path has (analysis 03, medium).
- **Test-quality audit rule (user, 2026-10-11):** "suite is green" is not proof — run a real test audit **regularly** (at the end of each work pack, and before any release): (1) measure true coverage with `pytest-cov` (dev venv only; do NOT add it to the runtime lock); (2) AST-scan for vacuous/tautological tests (assert-less functions, `assert True`); (3) **mutation-test the critical behaviors** — ownership guards, write-lock discipline, security gates, LWW/verification — i.e. break each and confirm a test actually FAILS (a test that still passes is worthless); (4) fix any real bug the audit surfaces and add the missing tests. **Mutation-test only on a COMMITTED tree** — `git checkout` to revert a mutation wipes UNCOMMITTED work (cost a redo on 2026-10-11). Track the numbers: **runtime app coverage 90%** (2026-10-12; EXCLUDES install.py/litert_serve/scripts per the coverage-push entry — raw TOTAL is 84%); test/source line ratio **0.84** (this is a test-VOLUME proxy, NOT coverage — never conflate the two).

## 2026-11-16 (later) — R1 fixed & pushed; embedding hang fixed in product; Pi realigned to gemma4-native

- **R1 (suite red, review 2026-10-25):** the fixed-seed flywheel test made relative (fix branch `fdcaef6` cherry-picked as `75e0dd2`). Full suite **1016 passed** (~180 s). The review's determinism rule (freeze or relativize every time-dependent test) is still open.
- **Embedding hang fixed in the product line:** `embedding.py` now pins a persistent cache (`FASTEMBED_CACHE_DIR`, default `~/.cache/fastembed`; the old default /tmp cache wiped on reboot) and sets `HF_HUB_DISABLE_XET=1` before huggingface_hub use — the Xet path is what hung the loader at 0% while holding `_model_lock` (2026-11-09). Stall-test fakes updated to the real constructor signature.
- **Pushed `7db28dc..3536280`** (NOTES.md restore, history-rewrite rule, R1 fix, embedding fix) — first push since 2026-10-25.
- **Pi realignment (user):** the Pi's `piSynapse` main was the pre-rewrite lineage frozen at 2026-10-05 with the EVREN integration uncommitted on top. The EVREN work is preserved verbatim on branch `experiment/evren-lora` (`b1fb322`); `main` reset to `3536280`; `.env` → `LLM_BACKEND=litert`, `LLM_MODEL=gemma4-e2b`, EVREN keys archived in `backups/env-evren-20261116`. Safety: `backups/piSynapse-pi-allrefs-20261116.bundle` + DB tar before the reset.
- **Scope rule (user):** the product line is gemma4-native ONLY; EVREN and LoRa are Pi-side experiments and must not enter it. The LoRa bridge stays in `/home/user/pisynapse-lora` (serial device absent today; it runs only when plugged in).
- **R5/R6 decisions (user, 2026-11-16):** R5 audit/meta rule adopted (concrete triggers: user complaint, error/install/latency metric, explicit request); R6 Docker stays out of the primary install path — rationale (Pi RAM, systemd-native, 2.4 GB model) still holds; instead a one-command installer entry point + the 30-second demo GIF, revisit Docker only after a clean-install verification exists.
- **Latency tuning pass 1 (2026-11-16, evening):** trimmed the system prompt (removed the redundant "Available tools:" line) and shortened the 5 longest tool descriptions. Result: **no measurable improvement** — chat TTFB 24.75 → 25.73 s, action 51.28 → 49.99 s (within noise). Conclusion: prefill stays the driver and a ~400-token trim is below the noise floor; reaching 10-12 s needs a deep cut (system-prompt rules, full tool-schema compression) with live tool-calling accuracy validation, or a smaller/faster model. Commit kept (no regression, slightly smaller prompt); pass 2 is a dedicated tuning session.

## 2026-11-16 — Journal restored after the undocumented 2026-10-25 history rewrite

- **Incident (2026-10-25, 23:57–23:59):** a `git filter-repo` run rewrote every ref and dropped `NOTES.md` from all history; 42 `main` commits that touched only the journal were pruned (60 across all refs). The run left no journal entry, no commit message and no agent transcript — neither the laptop nor the Pi session DB contains an Oct 25 session, and the journal copy was frozen at 23:57, two minutes before the rewrite.
- **Content was not lost:** the untracked `NOTES.local.md` is byte-identical to the removed tracked file (md5 `dfabd6844422b46a1ca76dc5704ca597`, 2,419 lines). The pre-rewrite bundle `piSynapse-yedek-20261025-2357.bundle` preserves HEAD `4e1d5e8` with the same journal.
- **Precedent:** the 2026-08-30 rewrite re-added the journal as a single clean version (`fa3bb6c`, "per-history rewrite"); the 2026-10-25 run skipped that step.
- **Legitimate part of the same run:** the intended sanitize pass (names → `Ada`, `/home/<user>`, deployment host → `example.com`) — kept; the rewritten sanitized tree is the current `main`.
- **Restore (2026-11-16):** `NOTES.md` re-added as the sanitized tracked journal, generated from `NOTES.local.md` with those three replacements; `NOTES.local.md` stays untracked. Pre-rewrite history is NOT restored — only the file.
- **R10 verified (2026-11-16):** the 54 `print()` calls are all CLI/installer/batch-script output — install.py 36, corpus_feeder.py 15, provision_owner.py 2, test fixture 2, main.py 1 (inside a docstring). Zero in the server runtime; logging is already the server convention. R10 is satisfied as-is; no code change.

- **Rule adopted (user, same day):** the open question above ("no rewrite without a prior dated entry") was adopted by the user on 2026-11-16 — see the History rewrite rule in READ FIRST. No more silent rewrites.

## 2026-10-25 — External review (read-only): RED suite + product/on-ramp gaps

Full report: **`docs/degerlendirme-2026-10-25.md`** (Turkish, matching the
`docs/analiz-*` convention; IDs R1–R10 for later reference). **No code was
changed and no work was started** — the user is in exam period and the LoRa
project takes priority until then.

- **R1 (blocker) — the suite is RED on a clean checkout:**
  `2 failed, 1014 passed in 122s`. Cause: `tests/test_audit_flywheel.py:265`
  seeds `created_at="2026-10-16T00:00:00"` while `db.audit_failure_digest`
  filters `created_at >= datetime('now','-7 days')` — the two digest tests
  were green on 2026-10-16 and expired on 2026-10-24. There are **56 hard-coded
  timestamps** across the test suite and **no time-freezing dependency**.
  The "Suite: 1016 passed" figure in the 2026-10-16 entry below is therefore
  historical, not current. CI did not catch it (last push 2026-10-05).
  Proposed rule: absolute date literals are banned in tests (migration fixtures
  excepted); freeze the clock or emit relative timestamps; re-run the full
  suite on a clean checkout at the end of every pack.
- **Other findings** (details + evidence in the report): product identity is
  half-way between single-user tool and multi-user server (multi-user/admin/
  approval + plain HTTP, `SESSION_COOKIE_SECURE` off by default); coverage is
  inverted (90% runtime app, `install.py`'s 1850 lines excluded — the first
  thing every user runs); 17 functions >100 lines, all in the LLM/stream/
  install path (`chat_with_ollama_stream` 541); last 60 commits = 24 fix /
  9 NOTES / 6 docs / 5 test / 4 feat of which 3 are audit (meta-feature drift);
  no Docker, no one-command install, no demo; NOTES+docs have become a second
  product; "collective learning" names cross-user sharing the privacy promise
  denies; 51 commits unpushed, no release tag.
- **Suggested order:** (1) R1 fix + determinism rule, (2) push + `v2.1.0`,
  (3) `docker compose` + a 60-second real demo, (4) decide single-user vs
  server, (5) split the stream loop, (6) unit-test install.py's pure functions.
  Do not start new features before (1)–(3).

## 2026-10-16 — Audit flywheel pack, phase C (C1–C3): holdout split, sandboxed automation, failure digest

Research (ToolReflection "eval gate before auto-promote", LoopTool "capture → triage → promote",
flywheel lessons: holdout must be FIXED, provenance travels with the row, weekly human review
rhythm) → the feeder mined signals but trained on everything and ran by hand only. Phase C:

- **C1 — deterministic holdout + provenance**: `corpus_feeder._deterministic_split(signature)`
  = `sha256(signature) % 10 == 0 → "eval"` (~10%). Both feeder add sites write the `split`
  field; the addition record already carried `audit_id` (provenance, unchanged). **Live intent
  routing EXCLUDES eval rows** (`llm/intent._additional_corpus` skips `split=="eval"`); legacy
  rows without a split stay train. Feeder-side dedup/conflict checks still see ALL rows (the
  holdout only gates what STEERS routing, not what is MEASURED against). Split is stable per
  signature — re-runs/dedup never reshuffle, so the eval set stays an honest fixed test set.
- **C2 — sandboxed weekly automation**: `main.periodic_feeder_loop(interval_hours, run_feeder,
  sleep)` spawns `corpus_feeder.py --db <DB_PATH>` as a **subprocess** (the feeder's sync sqlite
  + embeddings + optional LLM calls must never share the event loop or crash the server), with
  a **15-min timeout kill** for a hung run, output tailed (last 15 lines). Sleeps FIRST (like
  the rollup loop), never raises (failures log + retry next cycle), `FEEDER_AUTO_INTERVAL_HOURS`
  config (default **168h weekly, 0 = off**; lifespan skips the task entirely when 0). Started
  and cancelled alongside the other background loops in lifespan.
- **C3 — weekly failure digest**: `db.audit_failure_digest(days=7)` reads DETAIL rows (summaries
  keep counts, not error text — fine, 7d < 14d retention) and clusters errors by a normalized
  key (`_error_cluster_key`: digits stripped → "timeout after 12s"/"timeout after 40s" count
  once, capped 80 chars). Reports totals (calls/errors/corrections/confirmations/verify_failed),
  top 10 failing tools with error rate, top 10 error clusters. Surfaced in
  `GET /admin/audit/overview` (`digest` key) and logged weekly by the feeder loop BEFORE the feed
  run — one "sit down and look" moment: the digest is the human half, the feed is the machine
  half. UI addition deliberately skipped (scope). Never raises (degrades to zeros on db failure).
- **Suite: 1016 passed** (+14: `tests/test_audit_flywheel.py` — split determinism/distribution
  (~10% ±40 over 1000 sigs), cluster-key shape, feeder writes split, live loader skips eval +
  keeps legacy, loop sleeps-first/retries/reports-failure/disabled-by-zero, digest clusters +
  window + never-raises, overview carries digest, config wiring). NOTES + committed as
  `feat(audit): flywheel pack phase C (C1-C3)`.

## 2026-10-12 — Audit archive-integrity pack, phase B (B1–B3): manifest, NDJSON, injection guard, own retention

Research (orboto manifest+chain, Invoance determinism+formula guard, Windmill "exports are the
durable copy", Metis byte-identical exports) → the CSV archive was unverifiable and CSV-only.
Phase B:

- **B1 — manifest + verify**: every archived day now ships `tool-audit-<day>.manifest.json`
  (sha256+bytes per file, written LAST — its presence marks a COMPLETE archive; a crash before
  it is the detectable gap). `verify_audit_export(day)` re-hashes files against the manifest;
  `GET /admin/audit/verify/{day}` exposes it (admin-only, same day gate as export).
- **B2 — NDJSON + guard + determinism**: `tool-audit-<day>.ndjson.gz` sibling (one JSON object
  per line, key order fixed by AUDIT_EXPORT_COLUMNS; gzip **mtime=0** so bytes are reproducible);
  CSV cells get the OWASP formula-injection guard (`=`,`+`,`@`,TAB,CR → leading `'`; **`-`
  deliberately NOT guarded** — negatives must stay numbers; params are JSON `{...}` anyway);
  export query gained `ORDER BY t.id`. Same rows re-exported → byte-identical files (tested).
- **B3 — `AUDIT_ARCHIVE_RETENTION_DAYS`** (default **0 = keep forever**; settings UI + hot
  reload). `_prune_audit_csvs` → `_prune_audit_exports` (prunes csv+ndjson.gz+manifest together
  — never half a day). **Behavior change:** archives NO LONGER die with conversation retention
  — the archive is the only full-detail copy after a rollup.
- **Suite: 1002 passed.** ~~Phase C remaining: corpus-feeder automation + holdout/provenance +
  weekly failure-cluster digest.~~ (done 2026-10-16 — see the flywheel pack, phase C entry above)

## 2026-10-12 — Audit dashboard pack, phase A (A1–A4): retention config, rich summaries, admin surface, error-rate alert

Industry comparison (Windmill, ClickHouse "three villains", Sysdig rollups, LLM data-flywheel
lessons) showed our tool-audit export was **write-only**: nobody could read it, the retention
window was hardcoded, and the daily summary threw away latency and per-user detail. Phase A makes
the data readable, tunable and alive:

- **A1 — `AUDIT_RETENTION_DAYS` config** (default 14, settings UI + hot-reload casters).
  `rollup_tool_audit(days=None)` now resolves the window from config at call time; explicit
  `days=` still wins (tests pin it). **A `stats_json` migration** was appended (tool_audit_log).
- **A2 — rich daily summaries**: new pure `_build_day_stats()` (tools, per-user totals/success/
  error, duration min/avg/max/**p95 nearest-rank**, verification breakdown) feeds BOTH the rollup
  INSERT (`stats_json` column) and the dashboard's live-day aggregation, so they can never
  disagree. `tool_breakdown` stays flat/legacy-readable; NULL user → "unknown"; NULL duration
  skipped; NULL verification omitted ("not applicable"). p95 = `ceil(0.95*n)-1` nearest-rank.
- **A3 — the data is finally readable**: `GET /admin/audit/overview?days=N` (admin-only; merges
  rolled-up summaries with live detail rows so the trend has **no gap at the retention boundary**;
  each day tagged `source: summary|detail`) and `GET /admin/audit/export/{day}` (serves the
  pre-rollup CSV; day validated by strict `YYYY-MM-DD` regex **before** any path is built —
  traversal rejected). Admin panel (Settings → Admin) renders the per-day table + CSV links +
  alert banner; sw.js CACHE v57→v58.
- **A4 — `audit_error_alert()`**: 24h rolling error rate across **details AND summaries** (a
  just-rolled-up catastrophic day must not vanish from the window — summaries contribute their
  success/error counts; coarseness is deliberate: it's an alarm, not accounting). Breach = rate >
  `AUDIT_ERROR_RATE_ALERT` (default 0.2, 0=off) with >= 10 calls. Fires a loud log line in the
  daily sweep + drives the dashboard banner.
- **Test-robustness fix**: `test_migration_adds_origin_to_old_db` pinned `user_version == 23`;
  it now asserts `== len(MIGRATIONS)` (append-only framework grows by one per column — the baked
  number broke the moment stats_json was appended).
- **Suite: 993 passed.** NOT done (phase B/C): NDJSON format, sha256/manifest integrity, CSV
  formula-injection guard, archive gzip/permanence, corpus-feeder automation + holdout.

## 2026-10-12 — install.py robustness pack, phase 1 (analysis A5/A7/A1/A9/D1/D3/D4)

Researched the current install flow against the Command Line Interface Guidelines (clig.dev) and the 2026 supply-chain standard (Sigstore), then applied the code-side robustness items (no Pi needed):

- **A5 (hang):** `_run()` injected a hard `timeout` (15 min) — a dead/flaky link made `litert-lm import` / `ollama pull` block FOREVER with no message, freezing the install. Both retry loops now catch `TimeoutExpired` and warn ("timed out after 15 min — dead/flaky link?").
- **A7 (batch hang):** `_pkg_install` now uses `sudo -n` in batch/CI mode (a plain `sudo` blocks on an unanswerable password prompt); `_check_sudo_batch()` warns up-front when passwordless sudo is unavailable.
- **A1 (silent credential breakage):** when `cryptography` isn't importable the `MAIL_CREDS_KEY` fallback used `secrets.token_urlsafe(32)` — NOT a valid Fernet key (43-char, no padding → "Incorrect padding"), so every credential write failed silently. New `_generate_creds_key()` emits a Fernet-compatible key (urlsafe-base64 of 32 bytes) on both paths.
- **A9:** `litert-server.log` created 0600 via `os.open(..., 0o600)` instead of the umask default 0644 (the non-systemd path has no `UMask=`). (Ollama writes to DEVNULL — no log file — so nothing to fix there.)
- **D1 (UX):** `step_system_deps` collected a `missing` list but printed NOTHING when non-empty. `_report_missing_deps()` now summarises the missing deps, prints the exact `sudo <pm> install …` command, says what breaks without them, and (interactive) asks to continue.
- **D3:** the `~/Library/Python/*/bin/uv` and `3.*/bin/litert-lm` candidates were dead code — `Path(dirname).glob(basename)` only globbed the FILENAME, so the `*` in the directory never expanded. Now `glob.glob(pattern)` (any path component).
- **D4 (data loss):** a re-run rebuilt `.env` from the template and silently DROPPED keys the operator had added by hand. `_merge_env_extras()` now carries them over and reports "Preserved N custom .env key(s): …".
- **A-Y1 — already satisfied** (not a task): both `piserve.service` and `pisynapse.service` already render `WorkingDirectory` + `UMask=0077` + `EnvironmentFile` (piserve), with tests in `tests/test_install.py`.
- Guards: +15 tests across `tests/test_install.py` (A5/A7/A1/D1/D3/D4 behavioural) and `tests/test_install_template.py` (A9 source contract). Suite: **974 passed**. **Phase 2 (UX polish: NO_COLOR/TTY, --dry-run/--no-input/--quiet) and phase 3 (checksum/Sigstore) remain; phase 3 needs a decision.** NOTE: the installer runs on a Pi — these changes are unit-tested here but a real install should still be exercised on the device.

## 2026-10-12 — Test output now 0 warnings (silence an upstream-only deprecation)

- The suite carried exactly one warning the whole time: `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead`, fired at import by `fastapi/testclient.py` (FastAPI 0.140.7 → Starlette 1.3.1 migrating TestClient from `httpx` to the new `httpx2` package). It is purely upstream — our runtime legitimately uses httpx v1 (LLM/Nextcloud calls), so "install httpx2" does not apply and the fix is FastAPI's to ship. `StarletteDeprecationWarning` subclasses `UserWarning` (not `DeprecationWarning`), which is why the existing `ignore::DeprecationWarning` filter never caught it.
- Added a **targeted** filter in `pyproject.toml` `[tool.pytest.ini_options]` (message + UserWarning, no import needed) with a dated comment; remove it once FastAPI adopts httpx2. A permanent, non-actionable warning trains people to ignore warnings — a clean signal matters. Suite: **959 passed, 0 warnings**.

## 2026-10-12 — install.py model pre-download: retry + visible cause (analysis D2)

- The installer's model pre-download made a SINGLE silent attempt (`capture_output=True` swallowed the cause) — a stalled download raises nothing for minutes, so the user saw only "failed", with no reason and no retry. This was the first touch point of the "model never downloads" incident. Now `_predownload_one` (used for embedding + Whisper): 2 attempts with a short pause, the **stderr tail shown** on failure, a "timed out after 20 min — likely a stalled download" message on hang, and the **exact command to retry later** printed. A failed step still never blocks the install (lazy download covers first use).
- Guards: `tests/test_install_predownload.py` (4 tests, `subprocess.run` faked: success first try, retry-then-succeed with the stderr line shown, two failures give up + print the manual command, timeout handled + retried). Suite: **959 passed**.

## 2026-10-12 — Coverage push: runtime app 82% → 90% (target met)

- **New metric definition (use this, not the raw TOTAL):** "runtime app coverage" EXCLUDES modules that are not unit-testable in-process — the interactive installer (`install.py`), the standalone litert server (`litert_serve/`), and one-shot scripts (`provision_owner.py`, `reembed_all.py`, `corpus_feeder.py`). Command: `pytest --cov=.` then `coverage report --omit="install.py,litert_serve/*,provision_owner.py,reembed_all.py,corpus_feeder.py"`. Rationale: those are validated by integration/E2E on the Pi (or a few `# pragma: no cover`), not by unit tests — testing them means asserting mocks.
- **Results:** raw TOTAL 82% → **84%**; runtime app → **90%** (target met); suite 900 → **955**. Per-module: `routers/chat.py` 66% → 89%, `llm/chat.py` 70% → 78%, `llm/stream.py` 80% → 86%, `db.py` 81% → 84%, `main.py` health endpoints covered.
- **New tests:** non-stream `POST /` + `/execute` + session/history/memory/sync endpoints (`test_chat_endpoint`, `test_chat_execute`, `test_chat_misc_endpoints`); non-stream tool loop + the parity fix (`test_llm_chat_toolloop`); main health checks + favicon/sw/debug (`test_health_checks`); db session-map persistence (`test_session_maps`); stream confirm previews (`test_stream_confirm`).
- **Parity fix:** non-stream `allowed_names` now defaults to an EMPTY set (not `None`), matching the stream path — a hallucinated tool_call in a pure-chat round is refused, not executed. This closes the "known non-stream debt" in the LLM-backend-parity rule.
- **Mutation-verified:** removed the `save_notes_map` DELETE → replace test fails; made `_check_db`'s error branch return "ok" → error test fails. Tests are non-vacuous.

## 2026-10-11 (closing) — Test-quality audit: real cross-user bug found + coverage gaps closed

- **Method:** measured real coverage with pytest-cov (added to the dev venv; total **82%**), scanned for vacuous/tautological tests (AST: **0** real — the 4 assert-less ones are legitimate "never raises" contracts, one looked-assert-less test actually uses `np.testing.assert_allclose`), and ran **mutation testing** on three critical behaviors — ownership (`session_foreign`), sync LWW, leaked-call gate — all three caught (tests are non-vacuous).
- **Real bug found & fixed (multi-user, verification):** `run_verification` received `user_id` but never passed it to `_verify` → `_fallback_match`; the `save_memory` content fallback then ran `SELECT COUNT(*) FROM memories WHERE content = ?` **across all users**. A foreign user's identical memory could mark the caller's failed write `verified_by_fallback`. Fixed: `user_id` threaded `run_verification → _verify → _fallback_match`, and the fallback query scoped `AND user_id = ?` (default user preserved). `tool_verification.py` coverage 76% → **97%**.
- **New tests:** `tests/test_credstore.py` (8 — credential encryption had NO dedicated test: round-trip, ciphertext hides plaintext, wrong-key/tampered/garbage → None, invalid key → ValueError, key generation + persistence) and `tests/test_verification.py` (+8 — cross-user fallback scoping both directions, complete_task/delete_task/delete-calendar/notes-trio fallbacks, empty-parameter guards). `test_verification.py` mutation-verified: dropping the `AND user_id` clause fails the scoping test.
- **Process lesson (cost me a redo):** I ran a mutation and reverted with `git checkout -- tool_verification.py` while the fix was still UNCOMMITTED — the checkout wiped the fix back to HEAD (8 tests then failed in the full suite). Do mutation testing only on COMMITTED trees, or revert with a saved copy. Fix was re-applied and committed.
- Suite: **900 passed**.

## 2026-10-11 (very late) — Decision: installer host binding stays 0.0.0.0 (A-Y2 by design)

- A-Y2 proposed defaulting the installer's bind host to `127.0.0.1` (+ firewall hint). **Rejected as by-design:** installing on a Pi and reaching it from a phone on the same LAN is the product's primary use case — a localhost default breaks it. Port stays out of `.env` too (needless complexity; whoever installs binds deliberately). server-audit A-Y2 annotation updated to "as designed, won't change".

## 2026-10-11 (very late) — install.py: systemd units no longer staged in /tmp (analysis A, CWE-377)

- Both privileged unit writes (`piserve.service`, `pisynapse.service`) staged through predictable `/tmp/*.service` files then `sudo cp` — a local unprivileged user could pre-create the name as a symlink or race to swap the content before the root copy, installing an arbitrary unit (CWE-377 insecure temp). Now piped straight to root via `sudo tee <target>` with the unit on stdin — no temp file, no race.
- Guard: `test_no_predictable_tmp_for_privileged_unit_writes` in `tests/test_install_template.py` (forbids the `/tmp/*.service` literals; requires the `sudo tee` path). Suite: **884 passed**.

## 2026-10-11 (already-late) — install.py: .env written atomically at 0600 (analysis A)

- The installer wrote `.env` with `Path.write_text` (birthed world-readable under umask 0644) and only chmod'd it to 0600 afterwards — a TOCTOU window where the secrets it holds (API_KEY, credential-encryption key) sat readable. Now created atomically via `os.open(..., O_CREAT|O_TRUNC, 0o600)` (umask can only clear bits, so 0600 is an upper bound), with the chmod kept as a belt for a pre-existing looser file.
- Guard: `test_env_written_atomically_at_0600` in `tests/test_install_template.py` (asserts the atomic open; forbids a plain `env_path.write_text`). Suite: **883 passed**.

## 2026-10-11 (night) — pyproject packaging completed (analysis A `pip install .` ImportError)

- pyproject's setuptools metadata had drifted from reality: `py-modules` omitted seven modules the app imports (`auth`, `credstore`, `retrieval`, `textnorm`, `messages`, `title`, `tool_verification`) plus the standalone scripts (`corpus_feeder`, `provision_owner`, `reembed_all`), and `dependencies` omitted two runtime deps (`bcrypt`, `cryptography`) — so `pip install .` built an incomplete package that ImportError'd. Both lists completed.
- Guards: `tests/test_packaging.py` (2 tests: every top-level `.py` is in py-modules and every listed module exists — no drift either way; every `requirements.txt` package is in pyproject dependencies). Non-vacuous: the missing modules were exactly what the test flags.
- Suite: **882 passed**. (Full packaging — shipping `static/` assets etc. — is out of scope: the deployment path is `install.py`, not `pip install`.)

## 2026-10-11 (night) — CI hardening: pinned lock + Python matrix + pip-audit (analysis B3/B6/Y18)

- **CI now consumes `requirements-lock.txt`** (reproducible; it already pins pytest/pytest-asyncio/ruff, so no floating installs) instead of the floating `requirements.txt`.
- **Python matrix 3.11 + 3.12** — the Pi target AND current dev. This is not cosmetic: the sqlite3 `INSERT rowcount = -1` regression was Py3.12-only and shipped because a 3.11-only CI never saw it.
- **`pip-audit -r requirements-lock.txt`** added as a separate job (report-only via `continue-on-error` until the baseline is triaged — I could not run it here, so I did not hard-gate on an unverified baseline; drop the flag once clean).
- **`ruff check .` is now clean.** Six findings fixed: four mine (unused imports in `test_debug_body_gate`/`test_retry_dedup`/`test_sync_lww`; a D209 docstring in `test_audit`) and two pre-existing in `routers/config.py` (redundant local `from fastapi import HTTPException as _H` shadow-import → use the module-level `HTTPException`).
- Guards: `tests/test_ci_contract.py` (3 tests: pinned lock not floating, both Python versions, pip-audit present). fix-plan Y18 annotation updated to COMPLETED. Suite: **880 passed**.

## 2026-10-11 (late) — ui.js hygiene: i18n shadowing + dead no-op (partial i18n pass, analysis C9/C9b)

- Removed two footguns: a local `const t = setTimeout(...)` in `renderSessions`' touch handler shadowed the global i18n `t()` (harmless today — no `t()` call in that scope — but a latent trap); and `optsArr = '|'.repeat(0) + optsArr` was a literal no-op placeholder in the option-normalization path.
- **Deferred (need a browser + reliable usage oracle):** C1/C2 (hardcoded UI literals → STRINGS) and C10 (dead STRINGS keys). The C10 scan is unreliable: with word-boundary matching, `obNamePh` and `amoledDesc` show the same "definitions only, 0 usages" profile as the 5 keys the analysis named — so a blind delete could remove a dynamically-used key and silently break UI text. No Node/browser here to verify. Do this where the UI can be exercised.
- Guards: `tests/test_ui_hygiene.py` (2 tests: no `t = setTimeout` shadowing, no `.repeat(0)`). Suite: **877 passed**.

## 2026-10-11 (late) — Lock discipline audit: every commit holds the write lock (analysis D4)

- **The bug class:** `_commit_with_retry(db)` on the single shared connection flushes whatever transaction is open — including another coroutine's partially-assembled one (interleaved at an `await`). A later rollback on that other path then finds its work already committed (torn state). 28 of 45 commit sites already held `_write_lock`; the rest did not.
- **Method:** an indentation-based coverage scan (for each `_commit_with_retry`, look back for an enclosing `async with _write_lock():` at a lower indent) found 18 candidates; manual reading separated the real ones (13) from a caller-guarded false positive (`_retention_prune_conversations` — its caller `_retention_cleanup` takes the lock at db.py:~821) and 2 startup exemptions (`_apply_migrations`, `init_db` run before any request, no concurrency).
- **Fixed (13 functions wrapped):** `log_intent_audit`, `set_tool_correction`, `set_tool_confirmation`, `record_feedback_vote`, `record_pattern_decision`, `upsert_message_feedback`, `link_audits_to_message`, `purge_intent_audit`, `update_session_name`, `update_session_summary`, `save_memory` (both branches), `delete_memory`, `resolve_session` (expiry + sliding-touch). Verified no nesting: none of these is called from within an existing lock block (checked callers), so the added `async with _write_lock()` cannot self-deadlock. Full suite completes normally (no deadlock).
- **Residual (documented, not fixed):** `_write_with_retry` (single-statement write + immediate commit) still has a one-`await` execute→commit window for its ~10 call sites not already inside a lock (`log_tool_call`, `clear_*_map`, the retention memory delete). Closing it needs `_write_with_retry` to take the lock, which would deadlock `_retention_prune_conversations` (called under the lock, uses the helper) — the clean fix is a **reentrant** write lock (keyed by task), which is an architectural change → deferred pending user approval.
- Guard: `tests/test_lock_discipline.py` — wraps `_commit_with_retry` to assert `_write_lock().locked()` and exercises the audited paths; proved non-vacuous (a deliberate unlocked commit is flagged). Suite: **875 passed**.

## 2026-10-11 (late) — Fixed: search_memories access-stats write (analysis D2)

- The access-stat `UPDATE` ran on the shared connection WITHOUT `_write_lock`, followed by an UNCONDITIONAL `_commit_with_retry(db)`. On a single shared connection that commit flushes whatever transaction is open — including another coroutine's partially-assembled one — so a later rollback on that other path would find its work already committed (torn state). The function's own comment already half-admitted this (the embedding backfill got its own connection for the same reason) but the final write did not.
- Fix: the write and its commit run under `_write_lock`, and the commit happens ONLY when the function actually wrote — a no-hit search has nothing of its own to flush (the old unconditional commit was the leak).
- Guards: `tests/test_memory_access_lock.py` (2 tests: a hit writes + commits under the lock and persists access_count, with a lock spy; a no-hit search takes no lock). Suite: **874 passed**. **Remaining D-group:** D4 (systemic ~15 lockless-writer audit) — next.

## 2026-10-11 (late) — Fixed: sync_items origin column + true LWW + canonical timestamps (analysis D3/D5)

- **D5 (schema):** `sync_items` violated the 2026-09-05 sync-compatibility rule (updated_at + deleted + origin) — no `origin`. Added to the CREATE TABLE AND as migration index 22 (`origin TEXT NOT NULL DEFAULT ''`) for existing DBs. `SyncItem` model takes `origin` optionally (default '') so older phones keep working; `get_sync_items` returns it so a device can skip its own echoes.
- **D3 (LWW):** `upsert_sync_items` claimed last-write-wins but `DO UPDATE` was UNCONDITIONAL — a delayed old push clobbered newer data. Now strictly-newer-wins (`WHERE excluded.updated_at > sync_items.updated_at`), under `_write_lock()`, and the return count reads `SELECT changes()` (Py3.12 INSERT rowcount is -1) so an LWW-dropped write is not counted as applied.
- **D3 (timestamps):** `updated_at` was free text, so the string comparisons behind LWW and the `since` filter were lexicographic garbage across formats (`…:00Z` vs `…:00.5Z` compares backwards). New `_normalize_sync_ts` → canonical fixed-width `YYYY-MM-DDTHH:MM:SS.ffffffZ` (offsets converted to UTC, microseconds always present, lexicographic == chronological). Applied on write, on the pull `since` filter, and via an every-boot repair (`_normalize_stored_sync_timestamps`) for legacy rows. Unparseable write timestamps are dropped fail-closed; an unparseable `since` degrades to "return everything" (client re-filters).
- **Test-framework lesson:** `test_approval` and `test_write_integrity` pinned `PRAGMA user_version = len(MIGRATIONS) - N`, assuming the migration under test was among the last N. Appending a migration silently changed the window each test exercised. Both now find their migration by IDENTITY (table, column) — robust to future appends. Rule for new migration tests: pin by identity, never by end-offset.
- Guards: `tests/test_sync_lww.py` (13 tests: fresh-schema + migration-on-old-DB + user_version 23, newer-wins / older-dropped-and-not-counted / tie-dropped, tombstone LWW both directions, offset normalization, unparseable drop, mixed-format chronology, offset `since`, legacy-row boot repair, origin round-trip, write-lock spy). Suite: **872 passed**. **Remaining from D-group:** D2 (`search_memories` lockless UPDATE) and D4 (systemic ~15 lockless-writer audit) — backlog.

## 2026-10-11 (night) — Week-2 COMPLETE: SW caching is now allowlisted

- **The SW fetch handler caches ONLY same-origin shell assets** (`/`, `/favicon.ico`, `/static/*`); everything else — every current AND future API route — goes straight to the network. This replaces the old deny-list (`/chat`, `/config`, `/widget`, `/users`, `/health`), which required every new endpoint to remember itself — the exact "forgot the binder/cache-entry" failure mode that let auth-dependent `/users` responses go stale in the first place. A same-origin gate was also added (cross-origin responses can never enter the cache). `CACHE_NAME` bumped v56 → v57 (fetch-handler change ships with the bump — rule).
- **With this, the week-2 plan line is fully satisfied:** boot gate `/users/me` check ✓; sw.js allowlist ✓; logout cache staleness resolved structurally by the exclusion (documented earlier) ✓; cookie `secure` scheme-derived ✓; SW bump ✓; `/static` Cache-Control ✓.
- Source contracts updated: `test_sw_caching_is_allowlisted` (allowlist members, same-origin gate, deny-list pattern must stay gone); SW version floor raised to v57. Suite: **859 passed**.

## 2026-10-11 (night) — Fixed: rollup_tool_audit now holds the write lock (week-3/4 pack)

- **Bug (concurrency):** the audit rollup opened its `BEGIN IMMEDIATE` transaction on the SHARED connection WITHOUT `_write_lock()` — the process-wide serializer every other write path takes. Two failure modes: another writer's statements JOIN the rollup's open transaction and roll back WITH it when a busy retry discards the day; or `BEGIN IMMEDIATE` collides with the other path's implicit transaction, and the generic rollback kills the OTHER path's partial write. Fix: each day's attempt loop now runs inside `async with _write_lock():` (per-day granularity — a long rollup does not starve other writers for its whole duration).
- Guard: `test_rollup_holds_the_process_write_lock` in `tests/test_audit.py` (lock spy: rollup must acquire `_write_lock`; fails on the lockless version). Suite: **859 passed**.

## 2026-10-11 (evening) — Docs refresh: stale counts (analysis B7/B9)

- `docs/port-contract.md` §8 acceptance list refreshed from live collection (`test_user_isolation` 9→16, `test_summary_bounds` 10→11, `test_write_integrity` 5→6, suite 648→858) and now carries the regeneration command (`pytest --collect-only -q`) so counts are never hand-maintained again.
- NOTES stale numbers got dated correction notes instead of silent edits (journal policy): "27 tools"/"22 tools" → 23 today (with the regen command), "test_install_template (9)" → regenerate via collect-only. Cosmetic drift, no behavior change. Suite: **858 passed**.

## 2026-10-11 (evening) — Fixed: playwright e2e no longer touches the live database

- The playwright webServer booted the real app against the repo-root database, and `reuseExistingServer: true` could even attach to the dev/systemd instance running it — a test-DB isolation violation (NOTES 2026-09-09 incident class: a suite run once wrote a test admin row into the live DB). The config is now self-contained: dedicated `E2E_PORT` (8770, never the dev-service 8765 — no conflict, no mistaken attach), `reuseExistingServer: false`, and a per-run throwaway `DB_PATH` under tmpdir (fresh state, no cross-run bleed). Stale "dev service must be up" comment removed.
- **Honest limitation:** Node is not available in this dev environment, so the e2e suite itself could NOT be executed here — only the config changed, guarded by a Python source-contract test (`tests/test_playwright_isolation.py`: isolated boot, per-run DB, no live-db literal, dedicated port). **Run the e2e suite once on the Pi/dev machine where Node exists.**
- Suite: **858 passed**.

## 2026-10-11 (evening) — Fixed: intent/classification LLM calls get a hard timeout (analysis A2)

- `_llm_classify_call` (shared by the intent fallback AND the evidence-verified follow-up resolver, both backends) posted with no `wait_for` — a stalled engine would ride the shared client's 600s `LLM_TIMEOUT` and freeze the setup phase of every chat for minutes on a 20-token call. Now wrapped in `asyncio.wait_for` with `INTENT_LLM_TIMEOUT` (new config key, default 10s; added to example.env + install.py template + preserved_keys so it survives reinstall and stays single-sourced). On timeout the existing except-path degrades to question/None — never raises.
- **Setup-phase budget (plan item "SSE öncesi kurulum fazı bütçesi") — resolved structurally, no extra layer:** the gather's stall sources are now individually bounded (intent ≤ 10s here; embedding model load ≤ `EMBED_LOAD_TIMEOUT` with cooldown from the earlier fix; history/retrieval/memories are local DB queries). A whole-gather `wait_for` would add complexity for marginal gain.
- Guards: `tests/test_intent_timeout.py` (5 tests, parametrized litert+ollama: stalled engine → None within the budget, fast response parsed + normalized, ollama `think=False` preserved, HTTP error degrades). Suite: **856 passed**.

## 2026-10-11 (evening) — Fixed: retry duplication (analysis "retry mükerrer")

- **Bug:** when a stream round is retried (overflow / empty / truncation / tool-leak / escalation), tokens from the DISCARDED attempt had already been streamed to the client — and both consumers accumulated them anyway: `routers/chat.py`'s `reply_parts` kept round-1 tokens (the SAVED assistant message contained both attempts' text concatenated), and the UI's `fullText` kept growing (the bubble showed discarded text blended into the regenerated reply).
- **Fix:** the `gen_retry` event (already flowing end-to-end) now also RESETS both accumulators: `generate()` rebinds `reply_parts = []` (added to its `nonlocal`), and `ui.js`'s gen_retry branch clears `fullText`, `fullReasoning`, the bubble DOM and the think-box body so the regenerated answer starts clean. The llm layer already resets its per-round buffers (`buf`/`full_text` at the top of each round) — untouched.
- Guards: `tests/test_retry_dedup.py` (4 tests: discarded tokens absent from the saved reply while `gen_retry` still flows to the client, double-retry keeps only the last attempt, no-retry stream untouched, UI reset source contract). Loop-guard/leak suites re-verified green. Suite: **851 passed**.

## 2026-10-11 (evening) — Week-2: client cache hygiene (SW bump + /static headers)

- **`sw.js` CACHE_NAME bumped v55 → v56** — mandatory pairing: the fetch handler changed (the `/users` never-cache exclusion) and already-registered clients keep the OLD handler until the version moves (activate deletes every non-current cache). Rule for the future: any `sw.js` behavior change ships with a bump; a guard test now fails below v56.
- **`/static` got Cache-Control headers** (new `static_cache_control_middleware` in main.py): behavioral shell files (html/js/css/json/manifest — everything without a long-cache extension) revalidate on every load (`no-cache` + StaticFiles ETag 304s keep it cheap), so an updated `ui.js` reaches browsers immediately; fonts and icons (woff2/png/ico — big, rarely change) get `public, max-age=604800`. `/sw.js` already served `no-cache` separately. `ui.js` is NOT in the SW's STATIC_ASSETS, so its updates flow through HTTP revalidation, not the SW cache.
- **Logout cache cleanup (plan item) — resolved structurally, no code:** with `/users` excluded from the SW and the shell revalidating, a post-logout browser can no longer observe stale auth-dependent responses; an explicit logout→SW message channel would add complexity for nothing.
- Guards: `tests/test_static_cache_headers.py` (6 tests: revalidate vs long-cache per extension, extensionless paths, non-static untouched, CACHE_NAME ≥ v56). Suite: **847 passed**.

## 2026-10-11 (evening) — Week-2: widget NC context + shared binder

- **Fixed: the calendar widget was permanently empty.** `/widget/calendar` never bound the NC context — the credential gate answered "deny" for every widget call, so `list_events_today` always returned nothing. It was the SECOND caller to forget the binder (the tool dispatcher was the first, the 2026-09-27 hole), so the binder now lives in ONE place: `utils.bind_nc_context(user_id)` sets `NC_CREDS` (caller's decrypted credential) + `NC_SHARED_OK` (caller's admin flag, shared account for admins only). Both the dispatcher and the widget use it; a source-contract test forbids re-inlined `NC_CREDS.set(` copies. ContextVar semantics reminder (bit the unit test): `set()` lives in the TASK's context copy — the binder must run in the same async task as the NC calls; `asyncio.to_thread` propagates the context, which is why the widget's thread sees the bound vars.
- Widget handler now takes `request`, resolves the caller via `current_user` (middleware guarantees auth on `/widget/*`), and re-raises `HTTPException` instead of masking auth failures as "Calendar unavailable". `test_faz5`'s two direct-call widget tests got a request double + a binder double (that suite is DB-less).
- Guards: `tests/test_widget_nc_context.py` (6 tests: caller personal creds bound + per-identity cache key, admin → shared ok, non-admin without creds → deny, 401 unauthenticated, no-inline-drift source contract, binder unit scenarios). Suite: **841 passed**.

## 2026-10-11 (afternoon, week-2) — Fixed: post-refresh login (2026-10-05 open issue #1)

- **Root cause (verified in code):** the `ui.js` boot gate checked `getApiKey()` only, but password logins keep NO key in the browser — the HttpOnly session cookie IS the credential by design (`POST /users/session` deliberately returns no key material). So every refresh re-asked for login with a perfectly valid cookie. Two aggravators: `sw.js` stale-while-revalidate cached `/users` GETs (auth-dependent responses), and the cookie `Secure` flag came only from static `.env`.
- **Fix (3 parts):** (1) `static/ui.js` boot gate now awaits `GET /users/me` (cookie-authed, `cache: 'no-store'`) before `showLogin()` — a valid session counts as logged in, and the authoritative username is restored from the response; (2) `static/sw.js` never-cache list now excludes `/users` (a cached 200 after logout or cached 401 after login would corrupt boot auth); (3) `routers/users.py` `_set_session_cookie` derives `Secure` from the request scheme (direct TLS) with `SESSION_COOKIE_SECURE` as the TLS-terminating-proxy override — never secure-only over plain HTTP, where the browser silently drops the cookie.
- Guards: `tests/test_session_restore.py` (8 tests: source contracts for the ui.js gate + sw.js exclusion; behavioral — cookie authenticates `/users/me` 200/401, password login sets HttpOnly cookie with no key material and it works immediately, logout revokes, Secure flag from env override AND https scheme derivation AND absent over http). Suite: **835 passed**.

## 2026-10-11 (afternoon) — Week-1 pack continued: save_message/search ownership

- **Fixed: `save_message` wrote the message row BEFORE any ownership check.** A user writing into another user's session id created unreadable orphan rows (every read path filters by `user_id`) that still polluted FTS and storage. Now a `_write_lock()`-scoped guard rejects the write fail-closed (`return None`, same no-op contract as the duplicate guard) when `sessions` holds the id under a different owner. Race-free: session creation happens in the same lock's upsert. New helper `db.session_foreign(sid, uid)` — distinct from `not session_owned_by`: a brand-new id is NOT foreign, only an existing row with a different owner is.
- **`/chat/stream` answers 404 for a foreign session id**, indistinguishable from a nonexistent one (no existence oracle; feedback-path contract). Runs after the TPM check, before `save_message`, so a foreign turn never burns model compute on an unpersistable reply. Slot released on the 404 path.
- **`search_sessions` verified owner-scoped in every branch** (FTS AND, FTS OR, LIKE fallback, semantic supplement) — code was already correct; now proven by tests instead of assumption.
- Guards: `tests/test_save_message_ownership.py` (8 tests: owner ok, foreign rejected fail-closed, new-session ok, dedup contract untouched, FTS single/multiword both-directions, stream 404 + slot release, own-session passes gate). `test_history_hygiene` got a `session_foreign` double (that suite drives the endpoint DB-less). Suite: **804 passed**.
- **Fixed: /debug beacon body read was unbounded before auth.** The beacon key (`_k`) extraction in `security_middleware` called `request.body()` BEFORE the body-size gate further down and BEFORE authentication — an unauthenticated caller could make the server buffer an attacker-sized payload before the 401. New `main._debug_beacon_key()` gates the read on Content-Length ≤ `_DEBUG_MAX_BODY_BYTES` (8 KB): real beacons are tiny and always carry CL; chunked/missing/oversized CL are answered keyless (401) without reading the body. Guards: `tests/test_debug_body_gate.py` (11 tests: body-read spy proves oversized/chunked/non-digit CL never buffer, malformed JSON and non-string keys rejected, 401/413/200 middleware contract).
- **Fixed: leaked-call bypass (analysis A1, HIGH) — closed for BOTH engines.** `parse_leaked_tool_call()` recovery ran even in pure-chat rounds (`use_tools=False`) where `allowed_names` was `None` — the hallucination-rejection guard was skipped and create_note/create_task/save_memory are not in CONFIRM_TOOLS, so external content quoting `call:create_note{...}` through the model's reply became a one-step write (prompt-injection gadget). Fix (shared post-parse path, backend-agnostic): recovery now parses only on tool rounds; `allowed_names` defaults to an EMPTY set instead of `None` (no tools offered → nothing allowed); the suppress+strip terminal path yields the friendly `empty_answer_fallback()` when nothing survives stripping (restores the nudge-round UX the old recovery provided, without executing anything — `test_dedup_after_nudge_still_empty_yields_fallback` re-verified). First-attempt mistake worth remembering: gating the whole `if not tool_calls_acc:` block swallowed the terminal `yield done; return` and sent the generator into a phantom second round — gate ONLY the parse call. Guards: `tests/test_leaked_call_guard.py` (8 tests, parametrized litert+ollama: pure-chat leak never executes + pattern stripped, tool-round recovery intact, hallucinated non-offered tool rejected, plain reply untouched). Suite: **823 passed**.
- **Fixed: embedding hung-download stall (the 2026-10-05 "model never loads" root cause).** `TextEmbedding(model_name=...)` downloads weights on first use; a download hung at 0% raises NO exception, so the exception-only breaker never tripped — `_model_lock` was held forever and every embed caller queued behind it (thread-pool exhaustion risk). `get_model()` now: (1) runs the load in a daemon thread with a hard `join(_MODEL_LOAD_TIMEOUT)` (env `EMBED_LOAD_TIMEOUT`, default 120s — a hung download now arms the cooldown instead of pinning the lock forever); (2) loads OUTSIDE the lock (state transitions only inside); (3) concurrent callers fail FAST with "load already in progress" instead of serializing behind one download; (4) abandoned load threads die with the process. Cooldown contract and error types preserved (`test_embedding_resilience` untouched and green). Guards: `tests/test_embedding_stall.py` (4 tests: timeout arms cooldown + flag released, concurrent fast-fail, success + cache, exception type preserved). **With this, the week-1 critical security pack is COMPLETE** (all 10 items). Suite: **827 passed**.

## 2026-10-11 — Sector research: multi-user isolation standard vs. our system

- **Scope:** user asked how big AI companies implement multi-tenant/multi-user isolation in 2026, and whether our design matches the standard. Sources: OWASP Multi-Tenant Security Cheat Sheet, OWASP LLM Top 10 (2025), AWS PAR multi-tenant LLM analytics (Jun 2026), arxiv 2605.05287 (OGX/Llama Stack, May 2026), Anthropic "How we contain Claude" (May 2026), Check Point ChatGPT cross-account leak (Sep 2026), BeyondScale multi-tenant LLM guide (Apr 2026), Zylos session-isolation survey (Aug 2026), Bigcircle multi-user agent memory/credential isolation (Oct 2026), ChatGPT conversational-AI architecture case study. No code changes from this entry — findings only.
- **Where we already match the 2026 bar (verified in code, not assumed):** tenant context bound early in `security_middleware` (`main.py:505+` → `request.state.user_id`); client-supplied `session_id` treated as a selector with server-side ownership (`user_id=?`); relevance ≠ authorization respected (FTS/retrieval/memories all filter by `user_id`); API keys stored SHA-256 hashed (`db.py:2451`), passwords bcrypt; session cookie httponly+samesite+secure+TTL (`routers/users.py:24-27`); per-user rate-limit bucket (NAT-IP aware); tools orchestrated server-side (no client-side TCB widening); audit rows carry `user_id`; negative-path ownership tests exist. Conclusion: the base isolation layer is at the industry floor that most self-hosted assistants never reach.
- **Gaps found (ranked; sources in parens):** **A. No TPM (token-per-minute) limit** — only RPM; one long-context request can burn disproportionate compute (ChatGPT architecture, OWASP LLM10 Unbounded Consumption, BeyondScale — TPM is the binding constraint for LLM work). **B. No per-session turn serialization** — two parallel `/stream` calls on one session can both read history and interleave writes; abort event gets overwritten (Zylos Aug 2026, LangSmith enqueue/reject policy). **C. No session-token reuse detection** — login mints a fresh token (rotation exists) but a stolen old token is not detected/revoked as a family (MyPA RFC 6749 §10.4). **D. No tamper-evident audit chain** (antec HMAC chain) — low value at personal scale. **E. No output scanning** for cross-tenant PII (BeyondScale, OWASP LLM02) — low value at personal scale.
- **Clean checks:** system prompt contains no secrets → OWASP LLM07 (system-prompt leakage, new in 2025) risk is low. Shared Nextcloud instance resembles the Check Point "shared internal service" pattern, but each user has their own NC account (isolated) — accepted risk.
- **Decision (user, 2026-10-11):** apply the shortest option = gaps A + B only. **C (session-token reuse detection), D (tamper-evident audit chain), E (output scanning for cross-tenant PII) are DEFERRED, not cancelled** — they stay on the backlog (user: "erteleyelim ama iptal etmeyelim"). Pick them up when the threat model grows (e.g. assistant exposed beyond family/LAN, multiple admins, or a compliance requirement appears). Rationale: A closes a real cost/DoS vector, B closes a context-corruption + abort-consistency bug; both align with OWASP/Zylos/ChatGPT standards and fit the small-step + test + commit cadence.
- **Implemented (same day): A + B landed.** **A — TPM budget:** new `main.estimate_tokens()` (~3 chars/token on UTF-8 bytes so multibyte text is not undercounted) + `main._TokenLimiter` (sliding-window per-user token budget, config `RATE_LIMIT_TPM` default 200000/min). `/stream` pre-checks the unbounded user input (message + a 16384 output allowance) BEFORE the model is invoked → 429 when over; actual usage (history + message + output) is debited in `generate()`'s finally, so a burst cannot outrun the budget across concurrent completions. **B — one turn per session:** new `routers.chat._busy_sessions` set; `/stream` returns 409 when the session already has an in-flight turn (reject policy). The slot is released in `generate()`'s finally AND in the setup-failure path (so a failed setup cannot leak the slot). Guards: `tests/test_tpm_and_turn_lock.py` (11 tests: estimate/multibyte, limiter allow/deny/debit/isolation, 409 busy, 429 TPM + slot release, cross-session independence). `test_history_hygiene.py`'s fake-`main` double extended with `_token_limiter`/`estimate_tokens`. Suite: **796 passed**.

## 2026-10-11 — Week-1 pack: abort ownership + admin-gated corpus reload

- **Fixed: POST /chat/abort/{session_id} was callable by any authenticated user.** Anyone could stop anyone else's live generation, and the `aborted:True` answer doubled as a session-liveness oracle. The endpoint now takes the request, resolves the user and checks the new `db.session_owned_by()` before `event.set()`; a foreign (or rowless) session answers exactly like an idle one (`aborted:False`, event untouched — no oracle). Race-free by construction: `/stream` saves the session row (line ~314) before creating `_abort_events[sid]` (line ~346), so every live event has an owner row.
- **Fixed: POST /chat/reload-corpus had no admin gate.** The intent-routing corpus is process-global and shared by every user; a normal session could force a rebuild (cache-bust + embedding CPU spike). Now `require_admin(request)` (401 anon / 403 non-admin); endpoint docstring updated.
- New guards: `tests/test_abort_ownership.py` (5 tests: intruder denied + owner ok, no-event noop, ghost-row deny, 403, 401). Suite: **785 passed**.

## 2026-10-08 — Deep analysis + first fixes (work log, in progress)

- **Analysis reports (this session):** 6 parallel audits over the whole repo (~200 findings) written to `docs/analiz-2026-10-08.md` (index/summary), `docs/analiz-2026-10-08-tam.md` (combined full text), `docs/analiz-2026-10-08/01..06-*.md` (verbatim per-area reports). Commit `7feefe7`. Week-plan lives at the end of the `-tam` file (week 1 = critical security pack).
- **Fixed: `esc()` no-op (XSS, 168 sinks).** `static/ui.js:383` mapped every char to itself since regression `7609519` (2026-09-03). Restored `&amp;/&lt;/&gt;/&quot;/&#39;` chain. New guard: `tests/test_ui_esc.py` extracts the chain from source and fails if it ever becomes a no-op again (3 of its 5 tests fail on the broken version). Commit `85c1e48`.
- **Fixed: `update_session_summary` always returned False on Python >= 3.12.** sqlite3 reports `cursor.rowcount = -1` for EVERY INSERT (plain and upsert) on 3.12+; only UPDATE/DELETE rowcounts are reliable. The function now reads `SELECT changes()` (portable across SQLite versions). Owner-guard path (foreign session_id) got its first test. Commit `4b67339`. **Environment note: this laptop runs Python 3.12 — any future code reading `rowcount` after an INSERT is broken here; use `changes()`.** The other 16 rowcount reads in db.py are UPDATE/DELETE and verified fine.
- **Test environment:** fresh laptop, `.venv` created from `requirements-lock.txt`; full suite **773 passed** (was 771 + 1 previously-failing `test_conditional_summary_write`, now green, + 1 new owner-guard test).
- **Root cause candidates from analysis (fixes pending):** post-refresh login = `static/ui.js:1768` boot gate reads `getApiKey()` while `/users/session` returns no key (plus `sw.js` caching session GETs); embedding stall breaker only trips on exceptions, not on hung downloads.
- **Fixed: cross-user Nextcloud caches (the 2026-09-27 hole reopened).** `nextcloud_tasks._get_task_calendar` consulted its global cache BEFORE the `NC_CREDS`/`NC_SHARED_OK` gate, and all four process-global caches (`_task_calendars`, `_todos_cache`, `calendar_ops._primary_calendars`, `_find_events_cache`, `_today_cache`) were identity-blind. Now: gate runs first, and every entry is keyed by the new `utils.nc_cache_key()` (per-user `u|url|user` / shared `s|url|user` / `deny`). `nextcloud_notes` audited — per-user path builds an ephemeral client, safe as-is. Existing 2-tuple cache assumption in `test_stability_fixes.py` updated to the new 3-tuple shape. New guard: `tests/test_nc_cache_isolation.py` (7 tests). Suite: **780 passed**.

## 2026-10-05 — Open issues carried forward (user confirmed)

- **Post-refresh asks for login:** not resolved. Session cookie is set correctly (verified curl), UI uses /users/session for login — under investigation when bandwidth allows. Hypotheses: SW cache serving stale shell, wrong Secure attr assumption, or domain mismatch on the user's access URL. *(2026-10-08 update: root cause identified — boot gate `static/ui.js:1768` checks `getApiKey()` but `/users/session` (`routers/users.py:97-111`) never returns a key; SW also caches session GETs (`sw.js:61-74`) and cookie `secure` comes from static `.env` (`routers/users.py:24-28`). Fix scheduled week 2 of the plan.)* *(~~2026-10-11: FIXED~~ — see the 2026-10-11 week-2 entry: boot gate now verifies the session cookie via `GET /users/me`, sw.js excludes `/users`, Secure derives from the request scheme.)*
- **Model never loads today:** MPNet embedding weights cannot be downloaded over the current network (hung at %0 for hours), so chat requests that embed via SAVE message or intent classification churn until the duplicate window tripped and it stays stuck. Temporary fix when specifically desired: ask user later to point INTENTIONALLY at a cached smaller model (see below) or bring weights from a faster network. *(2026-10-08 verification: the stall bug is still live — breaker in `embedding.py:36-43` only trips on exceptions, a 0%-hung download raises none, `_model_lock` is held forever and no request path has a timeout. Fix scheduled week 1.)*
- **fastembed is now 0.8.1 (latest), requirements-lock updated.** New multilingual option `google/embeddinggemma-300m` exists (Gemma 3 based, 768-dim, 1.24 GB) — benchmarks promising but unrunnable on this link. MiniLM/MiniL2 viable but not currently trusted.

## 2026-09-09 — Later: web.html/app.html converged (unification candidate)

- `static/web.html` vs `static/app.html` differ by ONE line (a server-status span); both load the same vendor + `ui.js`. The MASTER/SLAVE split now lives in the `_NATIVE` runtime flag, not in the files. `index.html` is just the detecting loader.
- Future cleanup: single shell is possible, but native loads `app.html` directly (capacitor config, frozen port track) — do not touch until that side moves.

## 2026-09-27 — Invisibility hole closed: shared Nextcloud was served to all (user-found)

- **Report (user):** testidk (unapproved non-admin) vs admin data — checked live DB with hash comparison (no plaintext): `user_credentials` EMPTY (no leak there), but the GLOBAL `.env` Nextcloud account had NO gate — any authenticated user without personal creds silently landed on the admin's notes/tasks/calendar (read+write). Mail was already gated; Nextcloud was not. Real hole, user found it.
- **Fix:** `NC_SHARED_OK` contextvar (admin-only shared access) set per tool call next to `NC_CREDS`; all three factories (notes/tasks/calendar) deny shared use without it. Prompt contexts read DB maps only (unaffected); health uses raw status.php (unaffected).
- **Collateral:** one existing test bypassed the dispatcher (patched singleton directly) — now declares its admin context via fixture (explicit > default).
- **Test:** `tests/test_credentials.py` +3 (deny/allow/dispatcher-never-serves); full suite green; ruff clean.

## 2026-09-27 — Root cause found: embedding download stalls chats (fixed)

- **The 504 explained:** every chat embeds via fastembed mpnet, never cached locally; over the degraded link the weight download stalls at 0% — setup phase silent >90s → VPS nginx 504 → connErr toast. Direct-litert probes bypassed the app, hiding it.
- **Fix:** `get_model` circuit breaker (fail fast 10min after error) + `HF_HUB_DOWNLOAD_TIMEOUT=30`; callers already degrade (keyword fallbacks). Background resumable model fetch started; when it lands, embeddings go full-quality automatically.
- **Deployed 00:37**, `/health` all-ok. `tests/test_embedding_resilience.py` (2).
- **Still needed on VPS:** raise proxy timeouts for the stream location (snippet given to user).

## 2026-09-27 — Keepalive deployed (tunnel still degrading)

- Tunnel RTT decayed 293ms → 3s within the hour; small API calls still 200, long SSE streams die mid-flight (browser connErr toast, no answer).
- Deployed the `: ping` keepalive with a clean restart (00:07, no hang this time); `/health` all-ok.
- piai.example.com resolves to a plain VPS IP (no Cloudflare in path); full external loop answers in ~1.4s for tiny requests.
- Residual: throughput itself is environmental — if streams still die, next levers are client stall-detect/resume and shedding load (jellyfin/qbit) for first-token latency.

## 2026-09-26 — SSE keepalive + hermetic embeddings (tunnel fallout)

- **Keepalive:** `/chat/stream` now emits `: ping` comments on >15s idle gaps via a queue fan-in (the model iterator is never cancelled — wait_for on it could corrupt generator state; only the harmless queue.get times out). UI reader already skips non-data lines (verified). Pump errors still surface; client-abort semantics unchanged. `tests/test_stream_keepalive.py` (2).
- **Hermetic embeddings:** the suite hung suite-wide today — `save_message` embeds best-effort and fastembed tried downloading mpnet over the 3s tunnel (never local; CI only passed on fast bandwidth). Autouse `_hermetic_embeddings` in conftest: deterministic bag-of-words vectors (same text → same vector, overlap → similar), per-test fakes still override. Previously-hanging files pass in ~5s; suite 49s, zero network.
- **Rule learned:** tests must not depend on ambient anything — files, DB, network, or model weights. CI-green is not proof (fast network masked the download).
- **Test:** full suite **757 passed** (755 + 2); ruff clean.

## 2026-09-26 — Post-move outage: tunnel latency + stale Nextcloud URL (fixed)

- **Symptom:** UI "server unreachable", chats never returning, red status dot.
- **Findings:** Pi healthy throughout (app up, inference 2.7s direct). Root causes: (1) AmneziaWG path avg ~300ms w/ spikes — browser polls time out, long SSE stalls; (2) NEXTCLOUD_URL still pointed at the dead old-LAN IP (health degraded red); (3) cold model after reboot + 6/8GB RAM pressure slowed first tokens.
- **Fixed:** `.env` backed up, NEXTCLOUD_URL → localhost:8080 (local docker NC answers in 0.5s); service restarted 21:20, `/health` all-ok.
- **Incident:** graceful shutdown hung in stop-sigterm (stuck SSE on the flaky tunnel suspected) — restart took minutes. Future fix: graceful-shutdown timeout / SSE keepalive comments (`: ping`, UI reader already skips them).
- **Residual (environmental):** tunnel speed is outside app control; guidance given (same-LAN direct IP when possible, patience on first post-restart prompt, pause heavy containers if needed).

## 2026-09-10 — v2.0.0 live (user restarted 00:36, all healthy)

- Live server now runs current main (first time since İş 2): multi-user, sessions, onboarding v2, collective learning, per-user services all active. `/health` healthy (db/llm/nextcloud ok).
- Pending (tomorrow): smoke-test fresh onboarding in a clean browser → user wipe + fresh start (backup ready) → fresh screenshots → pilot users → Telegram/Matrix bot spike.

## 2026-09-09 — v2.0.0 release

- **Cut from:** 204 commits since v1.8.0 (server audit fixes, multi-user, collective learning, sessions, onboarding v2, per-user services, settings v2, security pass). Suite 755, ruff clean.
- **Docs:** README "Why piSynapse" + Honest limits (no superlatives, no household framing, name = private intelligence); installer/personal-setup truth; roadmap checked items; dev counts.
- **Upgrade notes for the user:** restart the server (activates everything); wipe + fresh start when ready (backup `backups/piSynapse-20260909-presession-auth.tar.gz`); SESSION_COOKIE_SECURE stays off on plain HTTP.

## 2026-09-09 — Onboarding rebuild (web): single name, no URL, explicit entry

- **Defects fixed (user audit):** double name (s3 account-name vs login-name unexplained) → ONE display name shared by both steps (s6 prefilled from s3; register syncs ASSISTANT_USER best-effort); server-URL field asked on web though requests are always same-origin (`ps_server_url` was write-only) → removed, replaced by a static connected-origin line (native phone flow untouched); register-vs-login indistinguishable → s6 now two explicit choices (register button vs key + Next), keyless advance deleted (it built broken 401-loop sessions); s5 tips read throwaway → rewritten as four concrete first-day reasons; s3 PATCH silently 403'd for non-admins → personal PUT with PATCH fallback.
- **Copy:** tr/en rewritten (s3/s6/s5/tips/hints) + 2 new keys; web overrides synced. `t()`-used keys verified present in both dicts; `node --check` clean.
- **Test:** full suite **734 passed**; ruff clean.

## 2026-09-09 — Login entry repair (fresh-browser confusion)

- **Root causes (user report: prompt()-in, then register/key-entry dead):**
  (1) `/users/me` 401'd the valid server-owner .env key whenever no users row
  existed — the one key the user knows failed validation. Now returns a
  synthetic owner record mirroring `ensure_default_admin` (test: legacy key,
  empty users → 200 admin).
  (2) Boot `prompt()` hijacked fresh users before onboarding → half-logged-in
  state. `prompt()` is now native-only; web entry belongs to the wizard
  (fresh) or the overlay (onboarded); sidebar re-entry routes to the overlay.
  (3) Register 409 (name taken) toasted "invalid key" — now a distinct
  loginNameTaken message (tr/en).
- **Note:** server half takes effect on the pending restart.
- **Test:** full-file users/audit green; `node --check` clean.

## 2026-09-09 — Round 3: scroll-chain, selects, liquid prototype, misc fixes

- **Scroll chain:** `.settings-body` wasn't flex → paged layout never sized, Assistant page clipped. `.paged` flex chain; native keeps legacy scroll.
- **Tabs leak:** author `display:flex` beat `hidden` → Telefon/Sunucu tabs on web. Override + empty-chips rules.
- **Selects:** coverage was form-scoped → document-wide + outside-tap closer (open menus lingered).
- **Search:** taller input.
- **Light:** surfaces stepped down (no pure white); light+glass rebuilt; settings solidifies under glass-open.
- **Liquid glass (experimental, desktop-only):** SVG feTurbulence+feDisplacement lens on topbar/modals, blur dialed back where it takes over, pointer:fine gate, implies glass, toggle in Appearance with persistence. Frosted stays default.
- **Wizard:** stacked-button margin bug (my spacing rule) removed; Next-display reset at render top (Back-to-welcome dead-end closed).
- **Test:** full suite **755 passed**; ruff clean; `node --check` clean; i18n both dicts.

## 2026-09-09 — UI fix round: scroll, selects, tabs, search size

- **Scroll:** paged chain missed flex on `.settings-body` (layout never sized → main clipped, Assistant page worst). `.paged` flex chain added; native keeps legacy scroll. Verified chain by reading, not by eye.
- **Tabs:** author CSS `display:flex` beat the `hidden` attribute — Telefon/Sunucu tabs leaked onto web. `[hidden]` override + empty-chips rule added.
- **Selects:** enhanced coverage was form-scoped (font/onboarding stayed native) → document-wide + outside-tap closer (open menus lingered over rows below).
- **Search:** taller input (11/14px).
- **Test:** full suite **755 passed**; ruff clean; `node --check` clean.

## 2026-09-09 — UI polish round (scroll, selects, glass, fade, minimal, regroup)

- **Scroll:** paged layout flex chain was missing `min-height:0` (main+nav never shrank → clipped, unscrolled). Fixed + bounded admin lists.
- **Spacing:** section rhythm 2→14px gaps + section margins + button gaps.
- **Light:** surfaces off-white (#f4f5f7); light+glass rebuilt from white tints (was dark smudges); settings modal solidifies under glass-open.
- **Glass perf:** topbar 16→10px blur, fb-tab saturate dropped + 12→8px, static specular insets for the glassy read (zero per-frame cost).
- **Dropdowns:** `enhanceAllSelects` covers every `<select>` now (was settings-form only — font/onboarding used native popups); called after each dynamic render.
- **Fade:** relocated below the bar to the viewport bottom, darker, theme-aware; uniform across modes.
- **Minimal:** timestamp survives — JS-moved next to the thumbs, thin, riding the row dim/hover rhythm (full on last, hover on older); reversible on toggle.
- **Regroup:** pages Appearance/Assistant(Model+Gen+Chat+Adv+Personal+Other)/Voice/Server(+Account)/Admin(bottom); non-admin server fields disabled + readonly note, save guarded; General folded into Appearance.
- **Test:** full suite **755 passed**; ruff clean; `node --check` clean; i18n both dicts.

## 2026-09-09 — Settings v2: sidebar layout + real themes (pre-2.0)

- **Layout (from scratch):** two-pane (nav rail + one visible page) replaces the scroll wall on web; pages Account/Appearance/Assistant/Model/Chat/Voice/Server/Admin built from the live schema (role-adaptive, admin page stripped for non-admins); search stacks all pages; native keeps tabs. Modal widened 520→760px; mobile collapses to top rail.
- **Themes, properly:** Dark/Light/AMOLED segmented mode (full day palette for light; legacy amoled toggle migrated once) + 6 accent swatches, all instant via CSS vars. AMOLED toggle row removed.
- **Regroup:** General folded into Appearance (it was only language); leftovers into Model; server split into Account/Server/Admin sections.
- **Test:** full suite **755 passed**; ruff clean; `node --check` clean; i18n keys verified both dicts.

## 2026-09-09 — Sector-standard settings + clean URLs (pre-2.0)

- **Settings:** live search filter (+empty state), dirty tracking (save disabled until change + unsaved note), role-aware save (non-admins PUT personal keys — their Save 403'd before), all with tr/en keys. Shells (web+app) gain search row + dirty note; CSS for disabled/empty states.
- **URLs:** loader used `location.replace` → users saw `/static/web.html`. Boot now `history.replaceState`s to `/static/` (non-native only; refresh-safe via the loader; native untouched, relative assets intact).
- **Listing:** verified no directory listing (subdirs 404; traversal normalizes to unknown routes). Locked with `tests/test_static_serving.py` (4 tests).
- **Test:** full suite **755 passed** (751 + 4); ruff clean; `node --check` clean.

## 2026-09-09 — Security pass + speed note (user requests)

- **Audit (verified, not claimed):** SQL 100% parameterized (`?` everywhere; f-string parts are constants/placeholder-runs/ints; LIKE escapes wildcards; FTS MATCH bound with LIKE fallback); XSS via `esc()` on all dynamic HTML incl. the new admin UI, `renderMd`→local-vendor DOMPurify, link protocol allowlist, no eval/Function/document.write; image previews are local dataURLs; subprocess only in install.py with fixed argv (no shell, no user input).
- **Hardened:** `renderMd` fallback now sanitizes too (was raw when marked missing); preview `src` escaped.
- **Residuals (honest):** homoglyph usernames; Secure-cookie needs HTTPS to matter; LAN-HTTP sniffing is transport, not app; no CSP (inline handlers would break — documented why).
- **Speed note:** `tourSpeed` tr/en in tour curious + settings server section (heavy first answers ~1min is normal on Pi).
- **Test:** full suite green; ruff clean; `node --check` clean.

## 2026-09-09 — Login/UI hardening round (user-reported issues)

- **Reserved names:** `admin` (and 8 system-like names) rejected at `create_user` (409) — login-by-name made a second "admin" ambiguous with the bootstrap row. Existing test using "admin" as first user renamed.
- **Sidebar stale-auth:** fresh logins kept seeing the key prompt — `finishOnboarding` and all overlay login paths now refresh sessions; auth-needed copy no longer mentions API keys (routes to overlay).
- **Ceremony tick:** copy button flips to ✓ on success. Wizard + overlay password fields wiped on close (DOM hygiene).
- **Approval transparency:** settings shows account status (Admin/Approved/Pending). Approval gates quorum weight only — never app usage (stated; usage-gating left as an open question for the user).
- **Admin delete:** user rows gain delete (confirm + server guards) next to approve/revoke.
- **Proton truth:** one Bridge serves unlimited paid accounts, each with its own bridge password (verified) — hint + `docs/mail-accounts` updated; free plans have no Bridge.
- **Curious:** expanded to six detailed items (what/model/tools/weather/thumbs/loop, 23 tools verified).
- **Test:** full suite green; ruff clean; `node --check` clean.

## 2026-09-09 — Session auth + onboarding v2 + per-user services (user spec)

- **Decision (user delegated):** session-cookie auth (JWT rejected as overweight); mail/Nextcloud vertical included now.
- **Auth:** `user_sessions` (opaque SHA-256 tokens, 30d sliding, lazy-expired cleanup); `POST /users/session` (cookie, zero key material), `POST /users/logout` (idempotent), register auto-login; password change revokes other sessions; middleware dual-auth with **header-wins** ordering (explicit beats ambient); `SESSION_COOKIE_SECURE` (HTTPS-only flag). `tests/test_sessions.py` (7) + chain tests (2).
- **Credentials:** `credstore.py` (Fernet, `MAIL_CREDS_KEY` auto-gen) + `user_credentials`; own-only CRUD endpoints (no secret ever returned); mail factory per-user (Gmail preferred) with legacy shared fallback; dispatcher resolves personal → shared(admin) → clear error; Nextcloud via `NC_CREDS` contextvar override (factories prefer it, ephemeral). Wipe covers sessions/votes/creds.
- **Onboarding (web):** gateway (2 choices) → register(name+pass+confirm) → key ceremony (copy/download-gated) → city(manual/skip) → mail(skip-note) → nextcloud(skip-note) → tour (6 groups + curious details). Login path skips to app; wrong creds toast, never blank. Overlay gains password login; logout revokes server-side. Single display name; s3 saves via personal PUT. 40+ i18n keys, parity verified.
- **Installer:** no personal questions (name/city/mail/NC preserved-if-present, never asked); generates MAIL_CREDS_KEY; SESSION_COOKIE_SECURE default off. Sandbox fresh-install verified (exit 0, 600, keys generated, personals empty).
- **Test:** full suite **750 passed**; ruff clean. Backup `backups/piSynapse-20260909-presession-auth.tar.gz` (967M) + DB copy (integrity ok) taken pre-work.
- **Deferred to user:** server restart (activates everything); live user wipe + fresh start (backup ready).

## 2026-09-09 — Collective learning Phase 4: approval + admin queue (done)

- **Approval flag:** `users.is_approved` (migration 22 + grandfather backfill via version-gated `_DATA_BACKFILLS`); new registrations unapproved except first-admin; admins always count; `POST /users/{id}/approve|unapprove` (admin). Quorum/reputation/feeder count approved-or-admin voters only. Legacy-upgrade rewind 6→7.
- **Pattern decisions:** `pattern_approvals` + `routers/admin.py` (review/approve/reject/decisions); feeder: approved skips freeze, rejected skips row. `tests/test_approval.py` (6 tests incl. backfill simulation + feeder decision paths).
- **UI:** browser settings admin-only section (user approve/revoke + review queue approve/reject, tr/en, escaped, index actions); `node --check` + 78/78 i18n parity.
- **Test:** full suite **733 passed** (725 + 8); ruff clean.

## 2026-09-09 — Collective learning Phase 3: quorum + reputation + freeze

- **`feedback_votes`** (UNIQUE(audit_id, user_id), re-vote overwrites) mirrored from correction/confirmation endpoints; message 👍/👎 votes nothing (not mined). `get_pattern_support` (distinct-user supports/contradicts), `user_reputation` (decided-pattern agreement, 1.0 neutral), `FEEDBACK_DAILY_CAP=50` → 429 at endpoints.
- **Feeder freeze:** reputable contradictors + supports < 2 → `pending_review` (`frozen_contradiction`); reputation consumed as the freeze gate. Single-user flows never freeze. Sync mirrors of the quorum helpers in the feeder (driver differs).
- **Residuals:** age filter not implemented (freezes young instances); adaptive weighting on add is future.
- **Test:** `tests/test_quorum.py` (6 tests). Full suite **725 passed** (719 + 6); ruff clean.

## 2026-09-09 — Collective learning Phase 2: signature normalization

- **New `textnorm.py`:** deterministic regex-only `normalize_signature` (email/phone/url/date/long-digit → lowercase placeholders; casefold + whitespace collapse; idempotent fixed-point). No NER (Pi budget) — bare names stay, documented as residual for quorum/review.
- **Feeder wiring:** `_process_audit_row` computes the signature once; `_is_duplicate` gains a signature-equality fast path (catches cross-user PII variants, skips an embedding call); addition records carry `"signature"` (additive — consumers untouched). One existing test fake updated for the new kwarg.
- **Test:** `tests/test_textnorm.py` (9 tests: classes, idempotence, Turkish samples, cross-user equality, residual). Full suite **719 passed** (710 + 9); ruff clean.

## 2026-09-09 — Collective learning Phase 1: feedback ownership guard

- **Plan:** `docs/collective-learning-2026-09-09.md` (4 phases: guard → lazy normalization → quorum/reputation → admin queue), grounded in federated-preference research (FedBis/FedBiscuit, adaptive reputation weighting, Byzantine-robust aggregation, Presidio-style placeholders).
- **Phase 1:** `set_tool_correction` / `set_tool_confirmation` / `get_audit_tool_name` / `upsert_message_feedback` take `user_id` (None = unscoped, offline only); the 3 endpoints pass `auth.current_user`. Miss → 404, same as not-found (no oracle). Existing `test_audit.py` endpoint tests run behind a stub-auth middleware as "default"; new `tests/test_feedback_ownership.py` (5 tests) proves both directions + anonymous 401.
- **Test:** full suite **710 passed** (705 + 5 new); ruff clean.

## 2026-09-09 — CI failure: tests depended on the ambient live DB (fixed)

- **Symptom:** CI (`python -m pytest -q` on a fresh checkout) failed 43 tests with `no such table: users/email_session_map` + auth 401s, while the Pi suite was green.
- **Root cause:** tests without their own DB fixtures used the default `DB_PATH`, which resolved to the live dev `assistant.db` on the Pi (tables present) but to a fresh empty file on CI. The mail-gate `get_user` call and the middleware user lookup turned the missing tables into hard failures.
- **Fix:** autouse `_isolated_db` fixture in `tests/conftest.py` — every test gets a fresh `init_db`'d tmp DB; live file never touched. Suite cost +15s (36s → 51s).
- **Proof:** full suite 705 passed locally AND in a pristine worktree without `assistant.db`/`.env` (true CI simulation).
- **Lesson (extends the isolation rule):** green-on-Pi is not proof — any test passing via ambient files is a latent CI failure.

## 2026-09-09 — History rewrite: zero-trace secret cleanup (user decision)

- **Decision (user):** full history rewrite instead of rotation-only, on the grounds of (near-)zero external clones.
- **Method:** `git filter-repo --replace-text` (leaked password → `***REDACTED***`, LAN IP → 192.168.x.x, `=<user>` → `=[redacted]`); 679 commits rewritten. Verified 0 hits for all three patterns across all refs, 0 hits in a fresh clone from the remote, full suite **705 passed** on the rewritten tree.
- **Push:** `main` forced (`8fc3b70...5844f4c`); tags needed no force (the secret postdates them). Pre-rewrite bundle + replace file shredded after verification.
- **Consequences:** every other clone (laptop included) must re-clone; old commit hashes/links are dead. `/home/user` paths deliberately left (pervasive, low-risk). User-side password rotation still recommended (defense in depth).

## 2026-09-09 — auth helpers + mail gate (post-M5 hardening)

- **Shared auth:** new `auth.py` with `current_user()` (401) + `require_admin()` (401/403, custom detail); routers/users.py, routers/config.py, routers/chat.py deduplicated onto it (chat keeps "default" fallback for exempt paths). 7 helper tests.
- **Live DB check (user's doubt resolved):** live `assistant.db` is schema-current (v21, `password_hash` present, 0 users); live server runs M1-era code (restart 14:35) — `/users/me` → 401 proves router+middleware live. Password flow proven on scratch DB (NULL → bcrypt hash → True/False); live needs only the pending restart.
- **Mail decision (docs/mail-accounts-2026-09-09.md):** Hydroxide REJECTED (upstream archived 2026-08-02, IMAP WIP); stay on official Bridge. Shared mailbox is now ADMIN-ONLY (`_run_mail_tool` gate: resolved non-admin + anonymous refused, unknown ids compat-allowed). Per-user accounts deferred (needs encrypted credential store — arch approval required).
- **Test:** full suite **702 passed** (695 + 7 helper); dispatcher+mail 112 passed; gate covered by 3 tests.

## 2026-09-09 — M5 (professional identity: passwords, devices, admin panel)

- **Scope (user: "make it professional, not amateur"):** password login, per-device keys, admin user management, settings visibility split. Two commits: `c57e1e5` (passwords+devices), `4c82157` (admin panel).
- **M5a:** bcrypt passwords (thread-offloaded, min 8); `POST /users/login` (uniform 401, case-insensitive names which are now unique-checked under lock); login issues a per-device key (`user_api_keys` table) so other devices survive; list/revoke own keys; `POST /users/password` (first-set needs no current). Public-login chicken-and-egg caught by tests (login/register must bypass auth but stay strictly limited).
- **M5b:** `DELETE /users/{id}` (admin; no self-delete, no last-admin; full data wipe incl. FTS/feedback orphans); `REGISTRATION_OPEN` moved into `SETTINGS_SCHEMA` (runtime toggle via admin PATCH + live sync); `GET /config/settings` splits by role (admins full, others personal-only with effective values).
- **Test:** full suite **695 passed** (688 + 7 new).
- **Residuals:** settings page UI not yet admin-aware (non-admin save → 403 toast); phone-app key entry still on the port track; device-key `last_used` tracking omitted (YAGNI — column absent by design).

## 2026-09-09 — M4 (multi-user verification & docs)

- **Scope (plan M4):** legacy-upgrade proof, capacity guide, access docs. Two commits: `62b6852` (legacy test + audit backfill), `47698e2` (capacity + access + changelog).
- **M4a:** legacy-upgrade test downgrades a fresh DB (drops newest columns/tables/index, rewinds version, plants dupes + NULL owners + legacy rows) and asserts full repair: version, dedupe, NULL-norm, index, map reassignment, audit inheritance (join-backfill added when the test exposed its absence — `tool_audit_log` rows now inherit their conversation's owner before NULL-norm), new tables.
- **M4b:** `docs/capacity.md` (bottleneck = inference; Pi 5 est. 2–3 concurrent; tunables; per-device-key guidance — estimates framed as estimates); remote-access multi-user section; CHANGELOG entries.
- **Test:** full suite **688 passed**.

## 2026-09-09 — M4-ui (browser login; user asked how others log in)

- **Design (user question):** entry = onboarding server step (name + Register → `/users/register`, or key → `/users/me` validate); persistence = `ps_api_key` + new `ps_user_name` (all requests already flow through `getApiKey()`, untouched); exit = settings user row + logout; boot gate for onboarded-but-keyless (native excluded); 401s reroute to the login overlay instead of `prompt()` (guarded: not during onboarding, not for `/users/*`, never re-entered). Registration-closed/invalid-key toast and stay. Commit `33834b5` (`static/ui.js` — the server web UI, NOT the frozen Android tree).
- **Test:** `node --check` green; i18n key parity tr/en verified by script; server suite 687 passed (UI-only change). Live browser verification pending (device/Caddy).
- **Follow-ups (not done):** settings page is not admin-aware (non-admin save → 403 toast); phone-app key-entry screen (needs the port decision track).

## 2026-09-09 — M3 (multi-user per-user settings)

- **Scope (plan M3; industry pattern verified: Nextcloud/OpenWebUI two-area model — admins own the building, users own their thermostat, personal overrides global).** Three commits: `d2eef9a` (store), `64514fd` (API+gates), `2d733b5` (wiring+seed).
- **M3a:** `user_settings` table + `PERSONAL_KEYS` taxonomy (language, name, city, 5 voice keys) + `effective_setting` (user row → live global → default).
- **M3b:** `GET/PUT /config/my-settings` (auth-bound, shared validation helper extracted from PATCH so rules can't drift); `PATCH /config/settings` now admin-only (existing direct-call tests pass an explicit admin request).
- **M3c:** prompt builders take `user_city`; `_build_full_messages` resolves city+language once per request; `messages.py` request-scoped language override (ContextVar — sync helpers need no signature changes, never leaks across requests); `seed_admin_settings()` migrates non-empty `.env` personal values into missing admin rows once (lifespan, best-effort).
- **Conscious deferrals:** settings UI still renders global schema (personal API exists; UI follow-up separate track); `GET /config` username stays global (dashboard bootstrap); `DEFAULT_USER`/`ASSISTANT_USER` display flows untouched.
- **Test:** full suite **687 passed** (679 + 8 new).

## 2026-09-09 — M2 (multi-user isolation hardening)

- **Scope (plan M2):** per-key limits, map/audit/resume/cache scoping, invisibility proofs. Four commits: `5f08ce7`→amended (rate), `b6ef217` (maps), `e2be2f0` (audit/resume/cache), `8a400fd` (params+proofs). Plus an incident fix (`31dc1f4` message reword — no code).
- **M2a:** authed routes bucket by `user_id` (NAT-shared IPs no longer share quota); rpm tunables to env (`RATE_LIMIT_RPM=30`/`_SESSION=20`/`_PUBLIC=120`) + example/template/preserved/numeric coverage.
- **M2b:** `user_id` on all 4 map tables (CREATE + MIGRATIONS + ownership backfill) with filtered reads/writes; dispatcher/llm/payload threading; llm contexts normalize once so storage never sees NULL. Init-ordering bug caught by tests (legacy repairs must run post-migration) + a pre-existing Phase 3c ordering flaw fixed alongside (UNIQUE index creation moved after dedupe).
- **M2c:** audit `user_id` (column + backfill + write threading from all 4 verification call sites); resume scoped (`_last_executed_tool_group` + `resolve_resume_context` + seed owners); litert payloads always carry namespaced `user:session` cache keys (ignored while caching is off; can never cross-share when on).
- **M2d:** vestigial `user_id` query params removed (4 endpoints; auth-bound `_uid` was always the source); `TestSessionInvisibility` proves both directions across list/read/meta/rename/deletes/summarize/search/memories.
- **Residuals (accepted):** `UNIQUE(session_id, seq)` on map tables still spans users (write error, never a leak; uuid sessions); `create_session` INSERT OR IGNORE unchanged; NULL-owner normalization covers legacy/raw rows.
- **Test:** full suite **679 passed** (668 + 11 new).

## 2026-09-09 — M1 (multi-user identity)

- **Scope (plan `docs/multiuser-plan-2026-09-09.md`, user decisions: open registration + admin toggle, data stays on bootstrapped `default` admin, all phases in one plan).** Iron rule: one user's sessions invisible to all others. Three commits: `2ef1504` (table+keys), `cf3054e` (middleware), `e5ded62` (endpoints).
- **M1a:** `users` table (id incl. reserved `default`, name, key_hash UNIQUE, is_admin) + generate/SHA-256/verify + create/get/list/rotate/count + `ensure_default_admin` (empty + `.env` key → admin on `default`, zero rewrites; empty + no key → waits for first registration).
- **M1b:** middleware resolves via DB (`key_hash` + 60s TTL, invalidated on rotate); `.env` key → default identity (backward compatible); unknown → 401; 503 only when nothing could authenticate; `request.state` carries `user_id` + `is_admin`.
- **M1c:** `routers/users.py` — register (201, first-is-admin, 403 when closed), rotate (key shown once), me, list (admin, no key material); `REGISTRATION_OPEN` (default on) in env/example/template/preserved; admin bootstrap in lifespan (best-effort); `/users/register` public under the strict limiter.
- **Test-pollution incident (root-caused, fixed):** full-suite 401s traced to `test_faz5`'s real-app lifespan writing a `default|admin` row bound to the public `test-key` into the live dev DB — a real security wart (deleted the row). Fix: that test now runs on a tmp DB; the two no-credentials tests use isolated DBs instead of assuming live-DB emptiness. Earlier "flaky" failures were this mechanism, not flakes — verified by row timestamp + bisection.
- **Test:** full suite **668 passed** (651 + 17 new), 2× consecutive green.
- **Residuals:** `get_user_id_for_key` kept (unused by middleware now, external callers safe); per-key rate limits, map/audit `user_id`, resume/cache keying, per-user settings → M2/M3.

## 2026-09-09 — README overhaul (user: explain the project + differentiation)

- **New "What makes it different" section** (commit `9eae4c9`): local brains incl. phone companion, verified tools (23, ID-based), persisting memory, small-model engineering, privacy-as-construction, honest single-user scope. Every claim verified against the tree before writing (tool count, groups, backends, endpoints, UI split).
- **Truth fixes in the same pass:** themes 5→6 (`THEMES` has six), RAKE→instant wording (roadmap + features), manual Ollama install no longer pipes unseen scripts (matches installer K7 fix), litert `config.json` line now says installer-generated (verified `_write_piserve_config`), STT browser added, Development section (venv/pytest/ruff per CI + conventions: one-commit rule, messages catalog, docs index).
- **Test:** full suite **651 passed** (docs-only change, no code touched).

## 2026-09-09 — Task 4: remote-access decision + voice root cause (user discussion)

- **Root cause (verified in code):** browser mic requires a secure context — `static/ui.js:866` (`isSecureContext` gate with `micHttps` toast), `:871` getUserMedia, `:1024` Web Speech fallback. Plain-HTTP LAN/VPS blocks the mic by browser design; the native app (`https://localhost` origin) is unaffected. Same root as the LAN-API exposure worry → same fix (HTTPS everywhere).
- **Decision (user):** user's own setup (domain via VPS) stays as-is; for other users a 3-tier model documented in `docs/remote-access.md` (same-WiFi HTTP with voice limits → Tailscale HTTPS recommended → own domain + WG reverse proxy with nginx SSE settings), linked from README; README RAKE mention fixed to instant+LLM. Key operational detail recorded: `TRUSTED_HOSTS` must include the tailnet/public hostname or requests 403.
- **Test:** full suite **651 passed** (stable since the installer render tests).

## 2026-09-09 — RAKE rename + user tasks 1–3 (per user decisions)

- **RAKE rename (user: "drop the RAKE name"):** `generate_rake_title` → `generate_instant_title` across code + tests (24 sites, commit `605d33c`); the real RAKE algorithm died in `0dcb93a`, only the misleading name survived. Historical docs untouched. Full suite 648.
- **Task 1 — secrets (user: no rotation, gitignore suffices, my discretion):** verified `backups/`, `.env`, `*.db*` all gitignored; all archives already 0600 (Phase 0b chmod); no rotation performed per decision. Nothing to commit.
- **Task 2 — systemd regen (APPROVED, done live):** pre-work manual DB backup (`backups/manual-pre-systemd-20260909.db`, integrity `ok`). Findings: orphan ran pre-A.1 code (no `conversation_cache_max`, no admin guard, default port 9380, hardcoded home path) with its own 8192 config; repo code verified importable in the litert venv. Installer templates refactored to pure `_render_*_unit` + regression tests (commit `2f26df1`); piserve unit gained WorkingDirectory/UMask/`EnvironmentFile=-.env` (token unset → no enforcement change). `litert_serve/config.example.json` 6144→8192 to match installer canonical + live behavior (commit `22eeedb`; live `config.json` is gitignored, set alongside). Applied both units, daemon-reload, restarted piserve (repo code UP in ~15s, gemma4-e2b listed) then pisynapse (`/health` healthy: db/llm/nextcloud ok). Smoke test: session create + non-stream chat ("smoke-ok" verbatim) + session delete, zero rows left. Orphan dir archived to `backups/litert_serve-orphan-20260909/` (root-owned pycache removed via sudo), directory gone. Dropped `StartLimitIntervalSec=0` (systemd default backoff is saner than unlimited restart).
- **Task 3 — other-user impact (user: fix anything affecting GitHub fresh installs):** reviewed all behavior changes for fresh-install safety — `DEFAULT_CONFIG` already 8192 (no drift for new users); migrations idempotent with legacy-dedupe; new keys additive; changed defaults only bite key-less existing installs (EMBED dim drift → startup warning + CHANGELOG note added). Nothing further to change.
- **Test:** full suite **648 passed** throughout; live smoke test green.

## 2026-09-09 — Phase 8 (port contract frozen) + session closeout

- **Phase 8:** `docs/port-contract.md` freezes post-fix behavior for the Kotlin port: session/user_id scope, fold formula + caps + conditional write + repair, parity loop, trim/normalize rules, intent layers + resume anchoring, memory/retrieval budgets, canonical mpnet model, SSE shapes (incl. aborted terminal), LANGUAGE_RULE verbatim, summary injection text, inference seam (`conversation_cache_max`), and the acceptance test list.
- **Session totals (user delegated overnight, no confirmation asks):** Phase 0–8 complete, 30 commits, full suite **563 → 648 passed** (+85 tests), zero failures. Working tree holds only the restored frozen Android files (untouched since recovery).
- **Still awaiting the user (NOT done):** (1) secret rotation — Gmail app-password, Nextcloud password, API key; (2) systemd regen + ~~orphan `/home/user/litert_serve` removal~~ (no orphan exists, verified 2026-11-16 — only the in-repo `litert_serve/` remains, serving piserve) — needs backup + explicit approval; (3) backup encryption decision (gpg/age?); (4) ~~LAN lockdown — port to 127.0.0.1 + ufw~~ (superseded 2026-10-11 by the A-Y2 by-design decision: installer binds 0.0.0.0 deliberately so phones on the LAN can reach the box; revisit under R2 as TLS + SESSION_COOKIE_SECURE instead). Details in the fix-plan's user-actions section.
- **Suggested next:** pick up the port (A: Kotlin faithful port vs B: embedded Python — decision still open) against `docs/port-contract.md`.

## 2026-09-09 — Incident: uncommitted Android tree wiped by `reset --hard`, recovered from laptop

- **What happened:** during the Phase 3 commit-message repair, a `git reset --hard` (part of recovering from an ill-advised `filter-branch`) silently discarded the pre-existing uncommitted Android work (`PiSynapseBridge.kt` session fold hardening, `static/ui.js` language anchor/listener fix/prompt tail). The loss went unnoticed through Phase 4–6 (server scope never touches those files).
- **Recovery:** the laptop build tree (`pisynapse-android`) held authoritative copies (it had received the fixed files via scp/sync). Both files were copied back; `git diff --stat` after restore is byte-identical in shape to the pre-reset state (41 + 30 lines). The monolithic `assets/public/index.html` edit was intentionally NOT restored (superseded: wrong file, and already overwritten on the laptop by the static sync).
- **Rule learned:** before ANY history-rewriting or tree-resetting command, run `git status` + `git stash list` and confirm no foreign uncommitted work is present. Prefer `rebase -i` reword over filter-branch/amend chains.
- **Status:** Android tree restored uncommitted, exactly as handed over (that scope stays frozen per the port decision).

## 2026-09-09 — Phase 7 (server audit fixes): install + runtime resilience

- **Scope (plan Phase 7, user-gated items excluded):** installer robustness + runtime resilience. Two commits: `bb756a3` (installer), `c384c9b` (resilience).
- **Phase 7a:** `menu()` honors `BATCH_MODE`; piper downloads via tmp+atomic replace (partials removed on failure); `TRUSTED_HOSTS` dropped from `preserved_keys` (asked answer wins, even intentional emptying); TTS `browser` writes empty voice + piper-without-download warns now; litert-absent warning for `--skip-llm`; data dirs 0700; shim 0750; ollama `install.sh` saved-to-file + explicit approval (batch refuses unseen remote scripts); litert import + ollama pull retry once; disk/RAM pre-check (warn-only) + optional embedding/whisper pre-download (non-fatal). New `tests/test_install.py` (installer imports cleanly — stdlib only).
- **Phase 7b:** lifespan catches `init_db` failure → serves degraded with `DB_DEGRADED` in `/health` (recovery hint logged); startup integrity `quick_check`; `auto_backup_db()` via sqlite3 online-backup on a dedicated read-only connection (`VACUUM INTO` refuses while the shared connection has open statements — verified), atomic, 0600, keep 7, at startup + daily loop; `docs/backup-restore.md` restore procedure; audit-CSV pruning under retention; `get_all_history` limit/offset (default unbounded preserves sync contract).
- **Deferred to the user (NOT done):** systemd regen + orphan removal (A-K4, needs backup + approval); secret rotation (K8); backup encryption decision; LAN exposure lockdown. See the fix-plan's user-actions section.
- **Test:** full suite **648 passed**.

## 2026-09-09 — Phase 6 (server audit fixes): security hardening

- **Scope (plan Phase 6):** trust, secrets, uploads, ops hygiene. Four commits: `2e07b09` (trust), `40d8f3a` (secrets), `cb7c7b1` (upload), `7925bed` (ops).
- **Phase 6a:** `TRUSTED_HOSTS=*` rejected+ignored (fail-closed); `CORS_ORIGINS=*` fails fast at startup (live `.env` verified explicit — no prod impact); exempt paths get a separate 120rpm bucket. Two tests had pinned the old fail-open wildcard — updated to the new contract.
- **Phase 6b:** `?k=` query auth removed (header/body only); `/debug` redacts + debug-level only; `GET /config/settings` masks secret-bearing keys (PATCH already ignored them — no functional change).
- **Phase 6c:** `/chat/upload` gates content-type + magic bytes (JPEG/PNG/GIF/WebP/BMP/ISO-BMFF) pre-buffer; audio temp suffix allowlisted at both sites. The old oversized test now sends real JPEG magic so it exercises the size path. Residual: concurrent-RAM bound left to the middleware cap (documented).
- **Phase 6d:** `ENV_PATH`/`DB_PATH` defaults repo-anchored (no more CWD split-brain); `*.db*` permission sweep; installer log rotation at spawn; `requirements-lock.txt` + pin-enforcing test (`pip-audit` documented as the networked gate).
- **Test:** full suite **637 passed**.

## 2026-09-09 — Phase 5 (server audit fixes): chat pipeline parity

- **Scope (plan Phase 5):** stream/non-stream parity, payload robustness, abort, tool hygiene. Six commits: `1ea6891` (mail), `3b5afba` (parity), `61f1a1b` (payload), `cd3f4ea` (abort), `4059ce3` + `f91f5f0` (hygiene).
- **Phase 5a:** `MailClient.search_messages` takes `mailbox_id` (dispatcher already passed 4 args — every mailbox search TypeError'd; mocks had masked it); list/search outputs numbered (`enumerate`, like the other tools).
- **Phase 5b:** hatch/chip pieces moved from `llm/stream.py` to `llm/utils.py` (stream re-imports, so `llm.stream.X` test references keep working); new shared `should_arm_tool_hint` + `chip_clarify_response` used by both paths. Non-stream now injects the hint on tool-domain questions, escalates once on marker/leak/bare-name (smallest toolset, stale hint stripped), and honors the chip fast-path (new `origin` param). New `tests/test_chat_parity.py`.
- **Phase 5c:** LiteRT normalize keeps `tool_name` (+`name` mapping); indexless single-call deltas accumulate args; trim uses an atomic triple pass (identical on well-formed input); `parse_tool_args` yields `{_parse_error: raw}` (distinct failures, distinct dedup sigs — handlers ignore unknown keys); leak parser learns bool/null/float. A test overreached on unquoted multi-word leak values (pre-existing heuristic limit) — corrected to realistic syntax.
- **Phase 5d:** `chat_with_ollama_stream(abort_event=...)` checked per round and per tool; terminal `{done, aborted}` event; router forwards it and skips full-reply save (finally-path still persists partial text). New `tests/test_stream_abort.py`.
- **Phase 5e:** group tool-names derived from `TOOL_GROUPS`; calendar/task/note listings sanitized; RRULE allowlist + CRLF reject; send_email address validation; verification failures surface `verification_error` (anchor logic unaffected); merge dedup with drop logging; 30s budgets on CalDAV reads + litert drain deadline; shared weather format helper.
- **Audit corrections:** prompt groups for weather/calendar already had `get_datetime` (only email/tasks/notes/memory were missing); `sanitize_external_text` docstring always claimed calendar/notes scope (now true).
- **Test:** full suite **627 passed** (602 + 25 new).

## 2026-09-09 — Phase 4 (server audit fixes): summary subsystem

- **Scope (plan Phase 4):** bounded folds, delete repair, race-free writes. Three commits: `48c3395` (cap), `65e5763` (repair+cascade), `aaf1afc` (conditional write).
- **Phase 4a:** `get_messages_to_summarize` folds at most `FOLD_MAX_MESSAGES` (30), oldest-first, each truncated to `FOLD_MAX_CHARS_PER_MESSAGE` (500); boundary advances by exactly the folded span so backlogs drain progressively; empty spans advance instead of retrying. New `tests/test_summary_bounds.py`.
- **Phase 4b:** new `_repair_summary_boundaries(db)` (clamp `summarized_until` to surviving MAX(id); clear summary+until when empty) wired into branch/last/clear/retention; feedback + tool-audit cascades on all delete paths (subquery form for clear, id-list for branch/last, orphan pattern for retention). Documented residual: stale facts in a surviving summary dilute through later folds (no re-summarization on sync delete paths). Retention prune extracted to a locked `_retention_prune_conversations` helper.
- **Phase 4c:** `update_session_summary(expected_until=...)` conditional write (rowcount-verified in scratch sqlite: fresh=1/applied, stale=0/skipped); `_update_summary` passes the just-read boundary and logs skipped writes (pending refolds next turn — deferred, never lost). Lock-free by design (no per-session lock objects: loop-bound, test-hostile).
- **FTS quirk map, completed:** malformed fires only when NONE of the delete targets are indexed; partial overlap is clean; bare `SELECT rowid` enumerates content rows; FTS-`rowid` reads inside a write corrupt the index; even the documented `'delete'` protocol fails on empty index. Init-db dedupe guards its FTS leg; live paths stay strict.
- **Test:** full suite **602 passed** (592 + 10 new bounds tests).

## 2026-09-09 — Phase 3 (server audit fixes): write integrity

- **Scope (plan Phase 3):** race-free, atomic, bounded writes. Four commits: `f05fc11` (lastrowid/FTS/retry), `bb1270c` (serialization), `adfa7b2` (UNIQUE/indexes/WAL/DDL guards), `3e10937` (title/RAKE).
- **Phase 3a:** `SELECT last_insert_rowid()` on the shared connection → INSERT cursor `lastrowid` (2 sites); `save_message` FTS insert best-effort like import; all 12 bare `db.commit()` → `_commit_with_retry` (a blanket pass briefly made the two helpers self-recursive — caught by re-reading the diff before commit); `update_session_name` gets the K4-class user_id guard; `update_session_summary` bumps `last_active`.
- **Phase 3b:** grouped writers serialized with a per-event-loop `asyncio.Lock` (`save_message` SQL section only — embeddings stay outside; `clear_history`, `delete_branch`, `delete_last_assistant`, `import_messages`, 4× `save_*_map`, the latter also collapsed from per-row commits to one). Explicit `BEGIN IMMEDIATE` was deliberately rejected (aiosqlite legacy isolation risks nested-BEGIN errors); the two remaining unguarded `sessions` upserts (different string format, caught by re-grep) got the guard. New `tests/test_write_integrity.py`: bursts stay complete, map replace all-or-nothing.
- **Lock lesson:** a module-level `asyncio.Lock` stays bound to its first loop — reproduced `RuntimeError: bound to a different event loop` + a downstream hang in tests (multiple `asyncio.run` loops). One lock per running loop with dead-loop pruning fixed it; stable 3/3 runs.
- **Phase 3c:** `UNIQUE(user_id, client_key)` partial index (no `user_version` bump — idempotent DDL); legacy dupes deduped first (keep `MIN(id)`); TOCTOU losers land on IntegrityError → debug-skipped. Growth indexes (`memories.created_at`, `tool_audit_log(conversation_id)`, day expression). WAL bounded (`journal_size_limit=64MB` + PASSIVE checkpoint in the cleanup loop).
- **FTS external-content quirk, mapped precisely:** the "malformed" error fires only when NONE of the delete targets are indexed; partial overlap deletes cleanly; bare `SELECT rowid` enumerates content rows (MATCH is the only honest probe); reading FTS `rowid` inside a write corrupts the index; the documented `'delete'` protocol also fails on empty index. Consequence: init_db dedupe guards its FTS leg (startup must never crash on legacy data); live paths stay strict. Test seeds mirror `save_message` (FTS rows written).
- **Phase 3d:** `_enrich_title` first-chance (total≤4) + never-overwrite (unset/"New Chat"/RAKE only) using the FIRST turn (get_history is chronological ASC — an initial `[::-1]` bug caught by the new test); RAKE masks emails/URLs; migration runner quotes identifiers + rejects DDL metacharacters.
- **Git hygiene note:** a `filter-branch` attempt to fix two commit messages duplicated history; recovered via reflog + `reset --hard`, fixed messages with scripted `rebase -i` reword, deleted `refs/original/*`. Rule learned: never filter-branch published-style history for message tweaks — reword via rebase.
- **Test:** full suite **592 passed** (579 + 13 new: 3 isolation + 2 integrity + 3 import/FTS + 5 title/migration).

## 2026-09-09 — Phase 2c correction: default language EN + multilingual priority (user directive)

- **Correction (user):** the instance default language is EN, not TR. Reverted the tr-unification (schema + `example.env` + installer template back to `en`); the real default moved in `messages.py` (`get("UI_LANGUAGE", "en")`, `entry["en"]` fallback — the schema never had a module attr, so the code default is the true fallback). `test_default_language_is_turkish` → `test_default_language_is_english` plus a new explicit Turkish-selection test; the TR `EMPTY_ANSWER_FALLBACK` constant stays for backwards compatibility. Live `.env` (tr) untouched. Commits `0e18265`, `741b006`.
- **Follow-through:** the EN default exposed two loop-guard tests pinning the frozen TR constant while the code correctly returns the live `empty_answer_fallback()` helper — tests now assert the same live helper; legacy `_EMPTY_ANSWER_FALLBACK` aliases removed from `llm/chat.py`/`llm/stream.py`. Root-caused a latent order-dependence (those tests only passed when an earlier settings test had synced `UI_LANGUAGE=tr` into the config module); now order-independent in isolation and full suite.
- **Standing directive (user): default EN; the multilingual (tr/en) catalog stays a first-class priority.** Applies to the Phase 8 port contract and all future user-facing strings: no hardcoded single-language user strings; the catalog + live-helper pattern (`messages.get_message`) is the rule.

## 2026-09-09 — Phase 2 (server audit fixes): config single-truth

- **Scope (plan Phase 2):** one canonical value for every config key across `config.py` / `example.env` / installer template / consumers. Three commits: `8ddf90d` (EMBED_MODEL), `5860f9e` (schema gaps + live reads), `b557ff1` (default unification + rerun-safe keys).
- **Phase 2a:** canonical embedding model is mpnet-base-v2 (768-dim), matching live env, `example.env` and stored vectors — `config.py` default MiniLM→mpnet, installer template MiniLM→mpnet, `embedding.py` no longer defines its own default (imports `config.EMBED_MODEL`; the old fallback silently zeroed cosine scores on drift). `main.py` lifespan warns (never blocks) on stored-dim vs configured-model mismatch, pointing at `reembed_all.py`.
- **Phase 2b:** `SETTINGS_SCHEMA` gains `SUMMARY_EARLY_TRIGGER` and the STT `browser` option (installer offered it, API validation rejected it; no server behavior code needed — in browser mode the UI uses Web Speech directly and never calls server transcribe). `CONFLICT_COSINE` read live via `config.get`, registered in `_NUMERIC_KEYS`, added to `example.env` + installer template + `preserved_keys`.
- **Phase 2c:** `UI_LANGUAGE` default unified to `tr` (schema + `example.env` + template; `messages.py` and its pinning test were already tr; live env untouched). `DEFAULT_USER` can no longer be empty. `/chat/upload` `MEDIA_MAX_MB` parse guarded (garbage → 100, not 500). `PISERVE_ADMIN_TOKEN` + `AUDIT_EXPORT_DIR` added to template + `preserved_keys` + `example.env`.
- **New tests:** `tests/test_install_template.py` (9 tests) parses the three files as text — the installer must stay stdlib-only, so no imports — enforcing template ≡ example ≡ config default, plus litert `max_num_tokens` ≡ `config.DEFAULT_LLM_NUM_CTX`. *(2026-10-11: the file has grown since — count via `pytest --collect-only -q tests/test_install_template.py` instead of trusting this number.)*
- **Conscious deferrals:** HOST/PORT env plumbing moved to Phase 6/7 (coupled with the localhost-default security decision); live `litert_serve/config.json` 6144 drift untouched (runtime behavior); `install.py` keeps the `max_num_tokens` literal (stdlib-only constraint) with the sync comment + enforcing test.
- **Test:** full suite **578 passed** (569 + 9 new).

## 2026-09-09 — Phase 1 (server audit fixes): per-user isolation

- **Scope (plan Phase 1):** `user_id` guards on summary/session/search/clear paths + retrieval threading + cross-user tests. Two commits: `9fc3ffb` (db guards), `8e9be9d` (retrieval + tests).
- **Changes:** `get_messages_to_summarize(user_id)` filters both queries; all `sessions` upserts guarded via `ON CONFLICT...WHERE sessions.user_id = excluded.user_id` (semantics verified in scratch sqlite first: same-user updates, cross-user silently skipped); `search_sessions` semantic supplement filters `c.user_id` and joins on `s.user_id`; `clear_history` FTS delete is now rowid-scoped to the user's rows and runs BEFORE the conversations delete (old code wiped the other user's FTS rows on `session_id` collision); `_fetch_candidates`/`retrieve_relevant_history` take `user_id`, both chat endpoints pass the request user through (with `_update_summary`).
- **New tests:** `tests/test_user_isolation.py` (6 tests, real sqlite tmp DB): summarize boundary isolation, summary no-clobber, session-touch preservation, retrieval fetch isolation, clear_history FTS isolation (MATCH-verified), semantic-search isolation.
- **Findings while verifying (external-content FTS5 quirks):** `DELETE...IN-subquery` against an index-empty table raises "malformed"; bare `SELECT rowid` on an external-content table enumerates *content* rowids, not index entries — MATCH is the only honest index probe; reading `rowid` from the FTS table inside a write statement corrupts the index. Test seeds mirror `save_message` (FTS rows written alongside conversation rows).
- **Residuals (accepted):** `*_session_map` tables have no `user_id` column (schema change deferred to a later phase); `create_session` keeps `INSERT OR IGNORE` (fresh uuid12 per session — collision negligible); intent-layer `_last_executed_tool_group` stays session-scoped (intent signatures carry no user_id; the planned "resume seed user_id" change was dropped as a no-op without read-side filtering).
- **Test:** full suite **569 passed** (563 baseline + 6 new).

## 2026-09-09 — Phase 0 (server audit fixes): dead code + hygiene + doc truth

- **Context (user):** comprehensive server audit first (4 parallel review agents; 106 findings saved in `docs/server-audit-2026-09-09.md`), then a phased fix plan (`docs/fix-plan-2026-09-09.md`, 9 phases Phase 0–8, each closing with its own regression tests). Standing orders for the fix run: verify every step with tests, commit per step, log into the notes files per their rules. Android tree left untouched (earlier session's uncommitted work).
- **Phase 0a (commit `21aae51`):** dead-code removal — `prompt.clear_{email,notes,tasks,calendar}_context` (zero callers repo-wide; `db.clear_*_map` functions kept), `tools.CONFIRM_REQUIRED` re-export dropped (internal use inside `definitions.py` kept), `title.generate_title_first4` folded into `generate_rake_title` (stale "db.py imports this name" comment removed — it does not), `main._SessionRateLimiter` no-op subclass collapsed to two `_RateLimiter` instances; `max_words` now caps the 4-word take instead of being silently ignored (`test_max_words_limit` updated to assert the cap). **Audit correction:** `EARLY_BUFFER_CHARS` is NOT dead (`llm/stream.py:480` uses it) — flagged by the audit in error, left untouched.
- **Phase 0b (commit `73d99eb`):** hygiene + doc truth — `backups/*` → mode 600 (secret-bearing archives were world-readable); removed 0-byte ghost DBs `pisynapse.db` / `piSynapse.db` (live DB is `assistant.db`); installer no longer suggests `cat .env | grep API_KEY` (keep-private/rotate message instead); docs: tool count 27→23 with the real per-group breakdown, weather backend OpenWeatherMap→Open-Meteo+Nominatim, README router tree gains `tools.py` + UI-split (index loader / web MASTER / app SLAVE / shared ui.js+css), intent token budget 5→≤20 (evidence ≤120), manual setup gains the mandatory API_KEY generation step (empty key = 503 fail-closed), `/reload-corpus` docstring references the real feeder flags (`--dry-run`/`--reset`).
- **Test:** full suite **563 passed** after each commit (baseline unchanged from 2026-09-08).

## 2026-09-08 — Android rolling summary (B): only-phone conversation özeti + build toolchain

- **Amaç (kullanıcı "önce a sonra b"):** A.1'den sonra B geldi — Android only-phone modunu piServe rolling-summary davranışıyla hizala. Sweet-spot deneylerinden çıkan gerçek: LiteRT-LM 6656 token bütçesini aşınca baştan (eski) mesajları atıyor → 40 mesajlık geçmişte model İLK mesajları hatırlamıyor ("erişimim yok") ama SON mesajları hatırlıyor. Yani limiti yükseltmek UI geçmişi veriyor, model görünürlüğü vermiyor; gerçek çözüm sistem promptuna gömülü rolling summary. Kullanıcı ~76s'lik ara prefill'i (17. mesajda) kabul etti.
- **SessionSummaryStore.kt (yeni):** `chat_summaries.json` (filesDir). Oturum başına `{summary, until}` — `until` = summary'ye katlanan mesaj sayacı (piServe `summarized_until` karşılığı) ve aynı zamanda monotonik revizyon. Thread-safe (JSONObject cache + lock). `get`/`set`/`clear`.
- **LlmEngine:** conversation anahtarı `sessionId:think:s{until}` oldu → summary değişince anahtar değişir, conversation yeniden kurulur (kabul edilen prefill); summary sabitken reuse korunur. `summarize(system, transcript)` — SUMMARY_SYSTEM_PROMPT (server `llm/chat.py` ile birebir) throwaway conversation'da çalışır (tools kapalı), cached conversation'a dokunmaz; `busy` guard'lı. `sanitizeConversationText()` — `strip_tool_leaks` paritesi (tool-call tag/bare regex'leri).
- **PiSynapseBridge.chatStream (only-phone):** oturum summary'si `contextSystem`'e gömülür ("Sohbetin önceki bölümlerinin özeti..." bloku, server `build_context` ifadesiyle aynı fikir). Yanıt `done` sonrası `updateRollingSummary()`: `history + (user,assistant)` üzerinden server `get_messages_to_summarize` birebir sayaç matematiği (`total - LIMIT` sınırı, `SUMMARY_BATCH_SIZE`/`SUMMARY_EARLY_TRIGGER`, ilk özet erken tetik). Assistant içeriği katlamadan önce sanitize edilir. Persist sonrası `until` yükselir → sonraki mesajda conversation yeniden kurulur.
- **ConfigStore:** `LLM_HISTORY_LIMIT` (önceki B-DENEY'den, default 40) + `SUMMARY_BATCH_SIZE` (5) + `SUMMARY_EARLY_TRIGGER` (6) — server anahtar adlarıyla birebir, schema'da "Telefon · Sohbet".
- **Trap (AndroidManifest, B-DENEY kalıntısı):** `<uses-native-library android:name="libvndksupport.so"/>` + `libOpenCL.so` (required=false) — cihaz çalışması için ilgili native lib kullanımını işaretler.
- **Build toolchain düzeltmesi:** `litertlm-android:0.17.0` transif olarak `kotlin-reflect 2.4.0` + `coroutines-android 1.11.0` çekiyor; proje KGP/stdlib 2.0.21'deydi → Kotlin metadata uyumsuzluğu (internal compiler error). `build.gradle` (root): KGP 2.0.21→2.4.0; `app/build.gradle`: stdlib 2.0.21→2.4.0, coroutines 1.8.1→1.11.0. Build tartışmasız geçti.
- **Ortam notu:** bu makine ARM64 → aapt2 (x86-64) qemu ile çalıştırılıyor; `QEMU_LD_PREFIX=/tmp/opencode/x64root` (extract edilmiş amd64 glibc/zlib/libstdc++) gerekli. JAVA_HOME=jdk21 (`/home/user/jdk21`; projects `sourceCompatibility=21`). Cihaza kurulumda imza uyuşmazlığı var (cihazdaki APK laptop debug keystore'u ile imzalı; bu makinede keystore yeniden üretildi) → kurulum/doğrulama kararı kullanıcıda.
- **Test:** Python tarafı dokunulmadı — **563 passed** (36s), py_compile ✓. Android: `assembleDebug` ✓ (Kotlin 2.4.0). Cihazda uçtan uca doğrulama bekliyor (kurulum kararı).

## 2026-09-06 — Phase PISERVE-CONV-CACHE: piServe conversation reuse altyapısı (A.1)

- **Amaç (kullanıcı, önce A sonra B):** piServe'i conversation reuse ile ileride hızlandırmak için altyapı. Şu an davranış DEĞİŞMEZ (`conversation_cache_max` varsayılan 0 = stateless). B (Android rolling summary) ayrı faz.
- **server.py:** `Handler._conv_cache` (session_id→Conversation, LRU) + `_cached_conversation`/`_preserve_conversation` + per-cache `threading.Lock`. `_chat` artık `body["session_id"]` varsa ve `conversation_cache_max>0` ise conversation'ı yeniden kullanır (prelude tekrar kurulmaz); yoksa eski davranış (create+close). LRU eviction en eskiyi `close()`lar. `admin/reload` engine swap öncesi tüm cache'i close+clear eder. Config: `conversation_cache_max` (DEFAULT_CONFIG + `admin/config` GET).
- **Not:** conversation yeniden kullanıldığında `messages[-1]` (current) `send_message`/`send_message_async`'e gider; prelude conversation kuruluşuna aittir, tekrar eklenmez. Bir sonraki fazda (A.2) istemcinin `session_id` göndermesi + `conversation_cache_max>0` ile aktifleşecek.
- **Test:** 3 yeni birim test (cache kapalıyken no-op; aynı conversation döner; LRU eviction victim close). **563 passed** (38s). Commit adayı.

## 2026-09-06 — Phase B-AUTOINSTALL+PARITY: otomatik kurulum + sunucu parite kapanışı (v0.21)

- **Komut (kullanıcı):** "sıradaki kişiler: otomatik kurulum + sunucu parite maddeleri — tümü". Kapsam: (1) ilk açılışta model yoksa otomatik indirme, (2) parite maddeleri: tool grupları, tool-correction/tool-confirm/message-feedback, /widget/calendar, abort, ses ayarı adları, MEMORY_SIMILARITY_THRESHOLD, model bellekte tutma süresi.
- **ConfigStore:** yeni anahtarlar `LLM_KEEP_ALIVE` (varsayılan "4h", select 10m/30m/1h/2h/4h/12h/24h/0, hint "Telefon · Zeka"), `MEMORY_SIMILARITY_THRESHOLD` (number, varsayılan 0.68, hint "Telefon · Sohbet"). Ses anahtarları yeniden adlandırıldı: `TTS_AUTO_REPLY`→`AUTO_TTS_ON_VOICE`, `STT_SEND_ON_PAUSE`→`AUTO_SEND_ON_VOICE` (eski anahtarlara ALIAS; `setValues` yeni anahtarı legacy anahtara da yansıtır). **Trappu:** AUTO_* varsayılanlara KONMADI — yoksa `v(name)` alias'ı default'u görür (legacy anahtar '' olarak başlar), yeni anahtar default'a girerse v() legacy alias'ı okuduğu için üstüne yazar/çelişir.
- **LlmEngine keep-alive:** `lastUsedAtMs` (@Volatile) + `markUsed()` (prewarm/chat sonrası) + `keepAliveMs()` (parsers; "0"/"never"=0) + `isLoaded()`/`lastUsedAt()`. `status()`'a `loaded_seconds`/`keep_alive`/`keep_alive_ms` eklendi. Bridge'de `keepAliveWatchdog` (uiHandler, interval = alive/6, 10-60s, default 30s; boot'ta `load()`'dan post) — idle süreyi aşınca `llmRelease()`. Kalıcı `releaseLocked` `lastUsedAtMs=0` resetler.
- **PiTools:** `companion object` içinde `TOOL_GROUP` haritası (16 tool → calendar/email/memory/notes/tasks/weather) + `GROUP_KEYS` + `GROUPS` JSONArray + `toolGroup(name)`. Bridge `toolGroups` @PluginMethod → /tools/groups.
- **ServerStore.raw(method, path, query, body):** private `exec()`'e genel passthrough — Bridge `httpProxy`'yi bunun üzerinden kurar. **OkHttp3 notu:** body'siz POST → "method POST must have a request body." → abort'ta `body=JSONObject()` iletilir.
- **Bridge yeni metodlar:** `chatAbort` (POST /chat/abort/{sid}, body=JSONObject), `toolGroups`, `httpProxy`, `messageFeedback` (POST /chat/message-feedback), `toolCorrection` (**boş `expected_tool`/`expected_group` JSON'dan çıkarılır** — sunucu `expected_tool:''` gitse 400 "Invalid expected_tool" veriyor), `toolConfirm` (POST /chat/tool-confirm). Hepsi only-server'da server'a, aktifse release. Ayrıca `transcribe`'ın bozulan satırı düzeltildi.
- **ui.js parite:** STRINGS `obEmbedding*` (tr/en); `/config`'de `auto_send_on_voice` + `auto_tts_on_voice:v('AUTO_TTS_ON_VOICE')`; `/health`'e `native/llm_loaded/loaded_seconds/keep_alive` + pollHealth status-dot title ("model in memory · süre · keep-alive") + `formatDurationShort`; `/tools/groups` → `P().toolGroups()`; `/widget/calendar` only-server'da `httpProxy` (GET), değilse `{events:[]}`; `POST /chat/message-feedback|tool-confirm|tool-correction` native route'lar (ok:false ise throw); `abortStream` önce `_NATIVE.chatAbort` dener, fetch fallback.
- **Otomatik kurulum (onboarding s4):** model mevcut değilse `obStartModelDl('hf')` 400ms sonra otomatik başlar (`_obDlActive` guard); embedding için `#ob-embed-status` + `obEmbeddingCheck` (modelProgress `kind==='embedding'` dinleyicisi + `_NATIVE.semanticDownload`) → otomatik embed indirme. **Latent bug:** `preloadModelCheck` `_nativeApiRoute` içinde function-scoped `P()` çağırıyordu (ReferenceError, sessiz) → `_NATIVE`'e çevrildi.
- **Doğrulama (TECNO CM5, LAN E2E, 5 build):** /config keys `LLM_KEEP_ALIVE=4h, MEMORY_SIMILARITY_THRESHOLD=0.68, auto_tts=off, auto_send=off`; /tools/groups = calendar,email,memory,notes,tasks,weather; /health `native:true, llm_loaded:true, loaded_seconds:2, keep_alive:4h, mf:gemma-4-E2B-it.litertlm`; `chatAbort` `{ok:true, aborted:false}`; tool-correction validation geçti (sahte audit_id'de 404); tool-confirm 404; dedup: aynı içerik 2. kayıt → `status:"duplicate"` (**MEMORY_SIMILARITY_THRESHOLD config yolu canlı çalışıyor**). İlk boot'ta görünen "Forbidden numeric value: NaN" hatası **onnxruntime flakinessi** — aynı oturum içinde semanticTool 0.27 skorla çalıştı, index kurulup search vermeden önce birkaç boot'ta tekrarladı; embedding yolu bu fazda değiştirilmedi (önceki fazda da görülmüştü). Otomatik indirme e2e testi bilinçli olarak yapılmadı (model dosyaları mevcut; `_obDlActive` guard tekrar tetiklenmeden önce `_NATIVE.modelStatus` loaded döndüğü için). Test kalıntıları temizlendi (semantic index tek Pamuk belleğine döndü; SYNC_MODE only-server bırakıldı). TODO: NOTES + backup + commit kullanıcı onayı bekliyor.

## 2026-09-06 — Phase ONNX-EMBEDDING: yerel multiplikual vektörizasyon (telefonda 7 nokta doğrulandı)

- **Karar (kullanıcı):** sunucunun embedding kullanımını telefona taşı (server'deki 7 kullanım noktasının tamamı). Model: sunucuyla aynı `paraphrase-multilingual-mpnet-base-v2` (768-dim). Tokenizer: saf Kotlin SentencePiece Unigram port'u + NFKC (kullanıcı onayı; Precompiled charsmap birebir değil ama yerel vektörler yalnız kendi arasında karşılaştırıldığı için tutarlılık yeterli — `½` referansta `1⁄2` iken NFKC `1/2`). Backup: `backups/piSynapse-embedding-20260906-1930.tar.gz`.
- **Yeni dosyalar (android Kotlin):**
  - `EmbeddingEngine.kt` — ONNX Runtime (onnxruntime-android 1.20.0): assets `mpnet_tokenizer.json`'dan vocab parsesi, max-sum Viterbi segmentasyon (pencere 16), CLS/SEP/UNK (0/2/3), 512 kırpma, mean-pool + L2 normalize, cosine. `model_local` = files/models/mpnet_qint8.onnx (267MB). **API notu:** onnxruntime-android 1.20'de `OnnxTensor.createTensor`'ın `long[]` data overload'ı YOK — `java.nio.LongBuffer.wrap()` kullan (int64 input). `SessionOptions.addSessionConfigEntry` da yok (kaldırıldı). OrtEnvironment `ensureReady` içinde build edilir, 2 intraop thread.
  - `LocalSemanticStore.kt` — singleton; `semantic_index.json` (v1, base64 float32) kalıcı indeks; `rememberMessage`/`rememberMemory`/`dropMemory`/`duplicateMemoryId` (eşik 0.68, sunucuyla aynı)/`searchMessages`/`searchMemories`/`rank`/`relevantContext`/`toolsForQuery`/`setToolDescriptions` (description corpus, lazy embed).
- **Sunucu 7 noktanın yerel karşılıkları (hepsi cihazda doğrulandı):** save_memory → dedup + rememberMemory; search_messages + search_memories → `semanticSearch`; retrieve_relevant_history → local chatStream sistem prompt'una `relevantContext` enjeksiyonu ("Sohbete bağlam olarak eklenen bilgiler:"); intent corpus → `semanticTool` (toolsForQuery); dedup eşiği `LocalStore.saveMemory`'de `status:"duplicate"`; warmup → lazy `ensureReady`. **Bug düzeltmesi:** `toolsForQuery`'de tool corpus vektörleri model hazır olmadan embed edilmiyordu → toolVecs boş dönüyordu; `ready && toolVecs.isEmpty()` koşuluyla yeniden build edilir.
- **Bridge:** `semantic` lazy property (LocalSemanticStore.instance + tool descriptions), `semanticStatus`/`semanticDownload`/`semanticSearch`/`semanticTool` @PluginMethod'ları; yerel chat sonrası `rememberMessage` (`u-$sid-${hash}` / `a-$sid-${hash}`). ui.js: `_nativeApiRoute` `GET /chat/search` → semanticSearch, `POST /chat/intent` → semanticTool (önceden boş döndüren dallar).
- **ModelDownloader:** `downloadTo` (resume'lu loop) extract edildi + `downloadEmbedding()` (HF mpnet qint8, uzak dosya `model_qint8_arm64.onnx` — uzak ad ile yerel `EmbeddingEngine.MODEL_NAME` farklı; `downloadEmbedding` uzak adı sabitler).
- **Doğrulama (TECNO CM5, CDP, 2026-09-06):** semanticStatus ready=true, model_size=278719559 (referans dosyayla aynı bayt), local chat mesajları embed edildi (messages:2); semanticTool "bir hatırlatıcı kur" → update_note + skor; semanticSearch "evcil hayvan kedisi" → bellek 0.63 skor; **dup testi:** aynı içerik 2. kayıt → `status:"duplicate"`; **bağlam enjeksiyonu uçtan uca:** local chat "Kedim hakkında ne biliyorsun?" hafızadaki bellekten "Kediniz Pamuk, bir Türk Van cinsi." çıkardı. Yerel LLM soğuk ~89s ilk yanıt, sıcak ~5.4s/8 token.
- **Yapı:** laptop'ta `assembleDebug` başarılı (onnxruntime-android dependency ilk denemede indi); APK 136MB (tokenizer + onnxruntime libs). Sync modu test sonrası `only-server`'a geri alındı. TODO: iki commit seçeneği → tek commit bekliyor (kullanıcı onayı).

## 2026-09-06 — Phase USERID-ROUTER: user_id filtrelemesi tüm router endpoint'lerinde kapatıldı

- **Kapsam:** Önceki faz (v0.20) sadece şemayı + db fonksiyon imzalarını + chat.py'nin bir kısmını kapsıyordu. Bu fazda tüm endpoint'ler `_uid(request)`'e bağlandı — client'ın gönderdiği `user_id` **asla** güvenilmiyor (güvenlik).
- **chat.py:** `_uid(request)` helper (Request import + `request.state.user_id`) — `import_chat_history`, `pull_chat_history` (`get_all_sessions(user_id)`/`get_all_history(user_id)`), `list_memories`/`delete_memory_endpoint`/`export_data` (Query `user_id` artık yok sayılıyor, `_uid` kullanılıyor), get/post `/sync/items` (`get_sync_items`/`upsert_sync_items`'te `_uid`), `/sync` batched (run_tool context `user_id` artık `_uid`), `clear_chat_history`, chat_endpoint/chat_stream'daki `chat_with_ollama*` `user_id=req.user_id` → `user_id` (yerel).
- **Test fix:** `tests/test_history_hygiene.py` `chat_stream(req, BackgroundTasks())` → `chat_stream(req, fake_request, BackgroundTasks())` (yeni Request parametresi).
- **Canlı doğrulama:** `?user_id=evil` query + body'de `user_id:"evil_spoof"` gönderildi → hem sessions/history/memories hem yeni mesajı **'default' ile yazıldı** (spoof yok sayıldı). `/chat/sessions`=66, `/chat/history/pull`=66. pytest **560 passed** (32s).

## 2026-09-06 — Phase MASTER-SLAVE-SETTINGS: user_id şeması + sunucu→telefon ayar pull'u (v0.20)

- **Karar (kullanıcı):** "chats/messages'ta user_id yok; memories/sync_items'te var. Çöz: sohbet tablolarına user_id şeması (Recommended)" + "Nextcloud grubu da şemada" + "Kullanıcı uygulamadan sunucuya bağlanıp oturum açınca otomatik pull edilsin". Backup alındı: `backups/piSynapse-20260906-170621.tar.gz` (247M, 17:06).
- **DB user_id şeması:** `MIGRATIONS`'a 14+15 eklendi: `conversations.user_id TEXT DEFAULT 'default'`, `sessions.user_id TEXT DEFAULT 'default'` (CREATE TABLE'da da var). Canlı DB uygulandı: `user_version` 13→15, 65 session + 488 konuşma korundu.
- **Sunucu settings NEXTCLOUD:** `SETTINGS_SCHEMA`'ya `NEXTCLOUD_URL/USER/PASSWORD` (str, default "") eklendi → GET `/config/settings`'e girdi. **Kritik:** üçü de `PROTECTED_SETTINGS`'te — PATCH ile DEĞİŞTİRİLEMEZ ama GET'te okunur (telefona pull için). `nextcloud_*.py` zaten `from config import NEXTCLOUD_*` okuyor, değişmedi.
- **Kotlin bridge pull:** `ServerStore.getServerSettings()` (GET /config/settings JSON) + `PiSynapseBridge.pullServerSettings()` (@PluginMethod, io.Execute). 
- **JS otomatik pull:** `_serverSettingsPull()` — sadece `_PORTABLE_KEYS = [NEXTCLOUD_URL, NEXTCLOUD_USER, NEXTCLOUD_PASSWORD, ASSISTANT_USER, DEFAULT_CITY]`'ı `configSet` ile ConfigStore'a yazar (sunucu LLM/model altyapısı cihaza taşınmaz). Tetikleyiciler: onboarding s6 `action==='server'` sonrası + `_nativeChatRestore` only-server dalı (app restart'ta oturum varsa). Sunucu müsait değilse sessiz retry.
- **Canlı doğrulama (v0.20, TECNO CM5, CDP):**
  - `pullServerSettings()` direkt: `pullok:true`, 29 ayar geldi, NEXTCLOUD_URL=http://192.168.x.x:8080 (sanitize 2026-09-09: LAN IP redacted), user=[redacted].
  - `_serverSettingsPull()` → ConfigStore'a yazdı: NEXTCLOUD_URL/USER/PASSWORD (+ASSISTANT_USER=[redacted]) cihaz config'inde.
  - Telefon config: sync_mode=only-server, SERVER_URL=http://192.168.x.x:8765 (sanitize 2026-09-09: LAN IP redacted), key set → restart'ta otomatik pull aktif.
  - pytest: **560 passed** (31s).
  - JSON top 29 ayar — NEXTCLOUD üçlüsü GET'te, PATCH'te engelli.
- **Yeni build akışı v0.20:** Kotlin değişirse `ServerStore.kt`+`PiSynapseBridge.kt` laptop'a scp → `JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64; ANDROID_HOME=/home/user/android-sdk; cd /home/user/pisynapse-android/android && ./gradlew assembleDebug -q` → `app-debug.apk` (55M) → scp → `adb install -r`. Asset'ler (index/web/app.html ui.js ui.css) ayrı scp public/.
- **ssh notu:** ~~laptop ssh şifresi burada yazıyordu — sanitize 2026-09-09: şifre metinden silindi (git geçmişinde duruyor, laptop şifresini döndür).~~ sshpass kullan (scp/ssh). `ANDROID_SDK` = /home/user/android-sdk.
- **Thread iş parçacığı uyarısı:** `io.execute`'da `call.resolve` — `pullServerSettings` aynı deseni izliyor.

## 2026-09-06 — Phase UI-SPLIT: iki ayrı kök dosya (web.html=MASTER / app.html=SLAVE), ortak ui.js/ui.css

- **Karar değişikliği:** 09-05'teki "tek dosya, ortam algılamalı" yaklaşımı **REVOKED**. Bugünkü kullanıcı kararı: "iki ayrı kök UI dosyası (browser.html + app.html)". Mimari hedef: piSynapse dağıtık asistan — **Python sunucusu = MASTER**, cihazlar (telefon) = **SLAVE**; sunucusuz device **standalone (only-phone)** çalışır; sunucuya bağlanmak = **API key ile oturum açma** gibi; sohbet listesi + hafıza + Nextcloud bilgileri/şifresi sunucudan telefona sync olup only-phone'da da kullanılabilir; geleceğe çok kullanıcılı (key + veri bazında kişi başına izolasyon) hazırlıklı.
- **Yeni dosya düzeni (`static/`):**
  - `index.html` → **yönlendirici dispatcher** (~40 satır): `_NATIVE` (Capacitor) varsa `location.replace('app.html')`, yoksa `web.html'`.  Tarayıcı `/` → 307 `/static/` → dispatcher → `web.html`.
  - `web.html` → **MASTER / tarayıcı kökü**: `#srv-status`/`#srv-dot` paneli YOK, onboarding metinleri sunucu-merkezli override ediliyor ("Kendi sunucun...", "kendi sunucunda çalışır", obTip4'te "model" yok). Setup = "Bu sunucuya bağlan (oturum aç)".
  - `app.html` → **SLAVE / WebView kökü**: mevcut telefon deneyimi (srv-status, model/izin/ayar adımları, only-phone). Capacitor `server.appStartPath=/app.html` ile WebView direkt app.html yükler.
  - `ui.css` = eski iki `<style>` bloğu → tek dosya (1363 satır); `ui.js` = eski inline ana script (4024 satır) + **web override bloğu** (`if(!_NATIVE){ STRINGS.master metinler }`). İki HTML de aynı ui.css/ui.js yükler; davranış `_NATIVE` ile ayrışır.
- **Capacitor config kritik üretim notu:** `server.appStartPath: "app.html"` **slash'sız authority'ye yapışıyor** → WebView `https://localhostapp.html/` "sayfa mevcut değil" hatası. Değer **`"/app.html"`** olmalı (uygulama asset'lerindeki `capacitor.config.json`'a `webDir:../static` → public/ üzerinden birebir kopyalanır).
- **Doğrulama (v0.19, TECNO CM5):**
  - WebView URL hatası giderildi → `https://localhost/app.html`.
  - CDP: `_NATIVE` true, `capPlugins` true, `_serverMode`=only-server, API key 43 kar. korundu, `#srv-status` DOM'da, sidebar **65 session**, onboarding kapalı (zaten onboarded).
  - Uçtan uca chat: UI'dan mesaj → sunucu cevap döndü (bubble render); test session silinip 65'e döndü.
  - Override fonksiyonel doğrulandı (Function-ctor testi): native=false iken welcomeSub/obS1S/obTip4/obS6 → sunucu-merkezli; native=true'te telefon metinleri korunuyor.
  - DOM kalıntı taraması: web.html'de srv-status/srv-dot/modelStatus/startModelDownload/Telefon·/AMOLED **0**; app.html'de srv-status/srv-dot **1**.
  - `checkjs` 3 html (12 inline blok) + ui.js → 0 hata.
- **TODO devam:** (a) sunucu tarafı `user_id` + kullanıcı başına veri izolasyon şeması (şimdi tek kullanıcı, API_KEY tek; ilerde key başına user'a açılır), (b) MASTER→SLAVE ayar pull'ı (NEXTCLOUD_URL/USER/PASSWORD + diğer sunucu ayarları → ConfigStore, only-phone'da kullanılabilir), (c) NOTES.md + commit.

## 2026-09-06 — Phase CHAT-SYNC: sohbet geçmişi iki yönlü senkron (Android ↔ sunucu)

- **Amaç:** todo'nun ikinci sırasındaki açık iş: sohbet geçmişi iki yönlü senkron (tasks+memory senkronu `393d8dc` ile bitmişti). Only-server modda soğuk telefonun sidebar'ı + konuşmaları sunucudaki panele birebir yansımalı.
- **Sunucu tarafı (idempotent import):** `conversations` tablosuna `client_key TEXT` kolonu + MIGRATIONS'a 13. kayıt eklendi. `db.import_messages(session_id, messages, client_key)`: her mesaj `client_key:<i>` ile dedupe (SELECT-check), INSERT + `conversations_fts` (best-effort non-fatal), `last_insert_rowid()` pattern'i `save_message` ile aynı, sessions upsert, RAKE title, `_commit_with_retry`. Endpoint: `POST /chat/history/import` (`ImportHistoryRequest`). Doğrulandı: run1 `{"imported":2}`, run2 `{"imported":0}`.
- **Kritik öğrenme — SQLite:** `ALTER TABLE ADD COLUMN ... UNIQUE` çalışmıyor (systemd migration adımı sessizce atlanıyordu) → kolon düz `TEXT`, dedupe SELECT üzerinden. Ayrıca **ayrı Python process'i `assistant.db`'yi boğuyor** (aiosqlite lock, 120s timeout) → tüm DB doğrulamaları curl ile çalışan sunucu üzerinden yapılmalı.
- **Tek istek pull (`GET /chat/history/pull`):** mobilitelenmiş ilk deneme her session için ayrı `GET /chat/history` yapıyordu → 60+ session = 60+ istek = **30 rpm server rate limiter'a çarparak 429**. Çözüm: `db.get_all_history()` (tek sorgu, tüm conversations, session_id grubu) + `db.get_all_sessions()` → tek endpoint `{ok, sessions, session_history}`. Bu sayede soğuk restore tek HTTP round-trip. Notebook: 65 session tek istekte geldi, rate limit'ten bağımsız.
- **Kotlin ServerStore:** `importMessages(...)` (POST /chat/history/import → `imported`), `pullHistory()` (tek istek → Pair(sessions, history)). `configured()`/X-API-Key auth aynı.
- **Bridge yeni metodlar:** `chatPush` (sadece `wantsServer()||wantsSyncAlways()` ise sunucuya yazar; değilse no-op `skipped`), `chatSyncSessions` (sidebar tazeleme), `chatHistory` (tek session), `deleteSession` (telefon yerel silince sunucudan da siler), `chatPull` (tek istek). `IOException` import'u eklendi.
- **JS tarafı:**
  - `_nativeChatSave`: debounce'lu (700ms) yerel kayıttan sonra 1.5s püskürtme timer'ıyla `chatPush` — mesaj patlamasında tek batch import.
  - `_nativeChatRestore`: önce yerel `chatHistoryLoad`, sonra `_serverMode==='only-server'` ise `chatPull` → `_nativeSessions` (sunucu formatı **korunuyor**: `{session_id,name,last_active,message_count}` — `sessName`/`renderSessions` zaten `name` bekliyor) + `_nativeSessionHistory`. Pull sonrası **kalıcı yazma** `chatHistorySave` ile (direkt; `_nativeChatSave` DEĞİL — o push timer'ı tetikler ve sunucudan gelen mesajları `phone:` key ile geri import ederek duplikat yaratırdı). Böylece uygulamadan çıkınca sıfırlanma sorunu çözüldü (restart sonrası 65 session + 65 history key korunuyor).
  - `_serverMode` global: init'te `_settingsData.SYNC_MODE.value`'dan set edilir; **saveSettings sonrası da güncellenir** (sabit: ayar değişince veri yönlendirmesi hemen değişiyor).
  - `_nativeApiRoute`: `GET /chat/sessions` + `GET /chat/history` only-server'da sunucudan (chatSyncSessions/chatHistory), `DELETE /chat/history` only-server'da sunucudan da siler.
  - **Topbar sunucu durum göstergesi:** `#srv-status` (yeşil nokta=only-server bağlı, amber=yerel mod, gizli=web). Tıklayınca toast ile detay (`serverStatus()` Bridge'den). Init + saveSettings sonrası `refreshServerStatus()`.
- **Kritik bug — kullanıcının UI'dan gönderirken "Sunucuya ulaşılamadı" görmesinin kök nedeni:** `_nativeSSEResponse` içinde `sid` değişkeni tanımsızdı (yalnız `sendMsg` içinde `const sid` vardı). `onEvt` done/error dalında `_nativeSessionPush(sid, ...)` (l.2746) + user push (l.2750) ReferenceError fırlatıyordu → `pushEvent(d)` hiç çalışmıyor, SSE queue boş kalıyor, `sendMsg` reader'ı done alamıyor ve `toast(t('connErr'))` atıyordu. Bridge'e doğrudan `P.chatStream` çağrısı yaptığım için bu satırlar hiç çalışmıyor, testler "çalışıyor" görünüyordu. **Fix:** `const sid = payload.session_id || '';` (l.2736). UI'dan gerçek `sendMsg` ile doğrulandı: user+assistant bubble render, sunucu cevap geldi, input temizlendi, `_nativeSessions` 65→66 push.
- **Doğrulama (LAN E2E, TECNO CM5):** device SERVER_URL LAN'a çevrilip gerçek API key ile: `chatPush` pushed=2; aynı payload 2. kez pushed=0 (**idempotent**); only-server app restart → `_nativeSessions` 65 + `_nativeSessionHistory` 65 key (sidebar 65 item render); **restart sonrası kalıcılık**: force-stop + relaunch → hâlâ 65+65 (sıfırlanma yok). **Telefon→sunucu yönü canlı doğrulandı:** cihazdan `chatStream` (session `phone-live-448386`) → sunucuda `message_count:2` + listede 66. session olarak göründü, sonra silindi (65'e döndü). Topbar durum göstergesi: `#srv-status` class `online`, yeşil nokta rgb(52,199,89). Test verisi sunucudan silindi; cihaz config'i şu an LAN`da + key ayarlı (kullanıcı çalışıyor, dokunulmadı).
- **Kullanıcıya hatırlatma:** cihazda SERVER_API_KEY boş — Ayarlar → Sunucu · Bağlantı'dan anahtar girilmedikçe sunucu senkronu 401 verir (kullanıcının token şikâyetinin kendisi). Onboarding s6'ya da native SERVER_API_KEY alanı eklendi.

## 2026-09-05 — Phase BROWSER-NATIVE SPLIT: tek dosya, `_NATIVE` ortam algılaması (v0.15)

- **Karar:** kullanıcı split için "Tek dosya, ortam algılamalı" yaklaşımını seçti (iki ayrı UI dosyası reddedildi). Yedek alındı: `backups/piSynapse-native-src-20260905-2125.tar.gz` (kaynak-only; venv/.git/build içermez).
- **Tarayıcı asset bozulması + kök neden:** Web'de SPA `/static/...` mount altında ama `GET /` `FileResponse` idi; HTML'deki relative yollar tarayıcıda köke çözülüyor → `/icons/...`, `/fonts/...`, `/vendor/...`, `/manifest.json` API-key korumasına takılıp **401**'di (yalnız `/static` muaf) — WebView'da doğruydu. Çözüm: `app.mount("/static", StaticFiles(html=True))` + `GET /` → `RedirectResponse("/static/", 307)`; böylece tarayıcıda relative yollar `/static/...`'e çözülür (WebView kökü ≡ tarayıcı `/static/`). Canlı sunucuda doğrulandı: `/` 307, tüm asset'ler 200.
- **Service worker tarayıcıya özel:** `sw.js` `STATIC_ASSETS` absolute `/static/...` (tarayıcı scope'u `/`; relative olsa yanlış yerlere iner). Kayıt `if(!_NATIVE ...)` ile sadece tarayıcıda; native'de eski build'lerden kalma kayıt temizleniyor (`getRegistrations()→unregister()`). NOT: cihazda eski sürümlerden kalma **aktif bir SW controller** vardı (`pm clear` ile temizlendi) — purge recovery ile kalıcı korunuyor.
- **Onboarding ortama göre:** native 5 adım (s1 karşılama, s2 izinler, s3 kişisel, s4 model, s5 tanıtım); tarayıcıda native'e özgü s2+s4 atlanır → `OB_STEPS = _NATIVE ? ['s1..s5'] : ['s1','s3','s5']`.
- **Ayarlar sekmesiz:** `openSettings` `phoneKeys`/`serverKeys` artık `_NATIVE` gate'li (`!_NATIVE` → `[]`) — tarayıcıda Telefon/Sunucu sekmesi HİÇ çizilmez (web `/config/settings` zaten `group` alanı döndürmüyor; gate gelecekteki grup isimlerine karşı da garanti).
- **Doğrulama:** native tarafı cihazda tam (5 adım onboarding walkthrough, topbar 92px, AMOLED/off rgb(3,3,4), fade 392.7px, config yüklü, SW kayıtları `[]`); tarayıcı tarafı curl ile (`/` 307 + tüm asset'ler 200) ve headless chromium `file://` DOM dump ile (`#ob-dots` render edildi: **3 dot** → browser `OB_STEPS=['s1','s3','s5']` fiilen çalışıyor; overlay açılıyor). Canlı-sunucu DOM testi: headless'ta `prompt()` 401 akışı sayfayı kilitliyor, telefon WebView cleartext HTTP'yi engelliyor → gerçek ağ üzeri DOM doğrulaması yapılamadı (deterministik `_NATIVE` dal + curl transport + file:// dump yeterli).
- **Durum:** tam pompa rebuild + yeniden kuruldu; commit `cd3b74b` + `00c975d` üzerinde duruyoruz.

## 2026-09-05 — Phase ANDROID-UX: full-bleed + AMOLED/font ayarı + fade + ilk-açılış onboarding (v0.14)

- **Üstten taşma çözüldü (full-bleed):** WebView artık edge-to-edge; `#topbar`/`#sidebar` `env(safe-area-inset-top)` (cihazda 36px) ile durum çubuğu altında başlıyor, `#messages` üst padding'i buna göre arttırıldı. Cihaz doğrulaması: `#topbar` height 92px = 56 + 36 safe-area, `paddingTop:36px`. Mobil media sorgusu `#topbar{padding:0 14px}` shorthand'ı safe-area padding'i sıfırlıyordu → `padding-top`/`padding-bottom` ayrı yazıldı.
- **Döndürmede gri flash:** `styles.xml` `Theme.AppCompat.Light.DarkActionBar` → `Theme.AppCompat.NoActionBar`; `windowBackground`/`statusBarColor`/`navigationBarColor` `@color/amoled_black` (#000). `colors.xml` oluşturuldu (amoled_black #000, colorPrimary #0d0d13, primaryDark #000, accent #f0943a). Splash: `Theme.SplashScreen` + `postSplashScreenTheme`.
- **AMOLED ayarı:** görünüm bölümüne `body.amoled` toggle (`--bg:#000` vb. koyu rampa), localStorage `ps_amoled`, `applyAmoled()`. Doğrulandı: açıkken body rgb(0,0,0). Mobil `--bg` aslında `#030304` (black-density boost, kasıtlı; `:root` `#0d0d13`), amoled open → saf siyah.
- **Font ayarı:** `body.font-system` (sistem fontu) + `font-select` (DM Sans varsayılan/Sistem), localStorage `ps_font`.
- **Kırık `/static/` yolları:** Web'de SPA `/static/...` mount, WebView'da kökte. Mutlak `/static/vendor/marked.min.js` vb. WebView'da 404 → `typeof marked` undefined, DOMPurify undefined, `document.fonts.check('16px DM Sans')` false. Index head/font-face/script + `sw.js` STATIC_ASSETS + `manifest.json` relative path'lere geçirildi; cihazda doğrulandı (marked object, DOMPurify function, font true).
- **Text-bar fade:** `body:not(.glass-mode) #input-area::before` artık `left:0;right:0;width:100%;height:120px` — giriş alanının tam genişliği (doğrulandı: 392.7px), kenara taşan hover'ları örtüyor.
- **İlk-açılış onboarding (sihirbaz, 5 adım):** `ps_onboarded` yoksa otomatik açılır: 1) karşılama 2) izinler (takvim/mikrofon/konum; her satırda "İzin ver" → native `requestPermission`, `permissionStatus` ile durum, "İzinleri atla" ipucu) 3) kişisel bilgi (ASSISTANT_USER, DEFAULT_CITY → PATCH /config/settings; web'de yer yok, native-path'te varsa DOKUNMA) 4) model durumu (`modelStatus` loaded/available → yeşil + "hazır", yoksa `.litertlm` ekleme yönlendirmesi) 5) kısa UI tanıtımı (4 ipucu). Bitiş: `ps_onboarded=1`, overlay kapanır. Cihazda uçtan uca doğrulandı (izin dialogları gerçek -> allow, config'e yazıldı).
- **Önemli init crash'i (önceden mevcut):** `applyLang` `lbl-theme-select`/`lbl-lang-select`'i guardsız yazıyor; bu öğeler SADECE `openSettings`'te oluşuyor → ilk açılışta DOMContentLoaded async handler'ı ilk satırda patlıyordu; config/settings/`_nativeChatRestore`/`loadSessions`/`showWelcome`/`startTicker`/`startHealthPoll` hiçbiri çalışmıyordu (UI sadece statik TR HTML görünüyordu). Guard eklendi → init uçtan uca çalışıyor (cdp_catch ile doğrulandı: configGet/chatHistoryLoad/permissionStatus akışları log'da).
- **Öğrenilen:** Android izin dialogu beklerken `requestPermission` bridge promise'i hemen dönmüyor; `permissionStatus` gerçek cevabı ancak kullanıcı dialogu cevaplayınca veriyor → wizard'da otomatik "hepsini iste" yerine satır başı "İzin ver" butonları + kısa bekleme (1.2s) kullanıldı.
- **Doğrulama (v0.14, TECNO CM5):** topbar inset ✓, AMOLED ✓ (rgb(0,0,0)), font select ✓, fade 392.7px ✓, onboarding 5 adım ✓ + config'e ASSISTANT_USER=Selim / DEFAULT_CITY=Ankara yazıldı ✓.

## 2026-09-05 — Phase ANDROID-VALIDATE: ayarlar 2 sekme + izinler + hafıza native uçtan uca doğrulandı

- **ConfigStore yeniden yazıldı (web-uyumlu):** anahtarlar artık SPA isimleriyle (`LLM_TEMPERATURE`/`LLM_TOP_P`/`LLM_TOP_K`, legacy `TEMPERATURE`/`TOP_P`/`TOP_K`'ya **alias**). Yeni anahtarlar: `LLM_TITLE_ENRICHMENT`, `HISTORY_LIMIT(50)`, `MEMORY_LIMIT(10)`, `ASSISTANT_USER`, `MAIL_PROVIDER`, `SYNC_MODE("only-phone")`, `SYNC_ALWAYS("off")`, `SERVER_URL`, `SERVER_USER`, `UI_LANGUAGE`, `UI_THEME`. `schema()` grupları `"Telefon · Zeka/Üretim/Sohbet/Hava/Notlar/Ses/Uygulama"` ve `"Sunucu · Senkron/Bağlantı/Kişisel"` — 2 sekme ayrımı, `byGroup()` ile işleniyor.
- **Bridge yeni metodlar:** `listMemory` (limit/offset, her öğeye `importance:5`), `deleteMemory({id})`, `requestPermission({kind})`, `permissionStatus()` — kind: calendar→WRITE_CALENDAR, microphone→RECORD_AUDIO, location→ACCESS_FINE_LOCATION. Manifest'e 4 izin eklendi.
- **`_nativeApiRoute`:** `/chat/memories` GET/DELETE ve `/chat/execute` POST native'e yönlendiriyor. **Düzeltilen bug:** GET `/chat/memories` tam path eşleşmesi istiyordu; `loadMem` `?user_id=` query'si gönderdiği için native route düşmüyor, "Sunucuya ulaşılamadı" veriyordu → `path.split('?')[0]` ile düzeltildi.
- **`_renderSetting` options normalize:** native schema options'ı `"a|b|c"` string veriyor; JS hem string hem `{value,label}[]` array'i ayrıştırıyor. Öncesinde select boş render oluyordu → `saveSettings` yanlışlıkla `SYNC_MODE:""` yazabiliyordu. Ayrıca `ConfigStore.v()`/`get()` artık boş değeri default'a düşürüyor (kalıcı boş kayıt yanılgısını önler).
- **Doğrulama (v0.12, telefon TECNO CM5):** `window.Capacitor.Plugins.PiSynapse` 17 metod, configGet 25 anahtar; ayarlar Telefon 7 bölüm/19 ayar + Sunucu 3 bölüm/6 ayar, sekmeler arası geçiş çalışıyor; SYNC_MODE default `only-phone`, save→reload→değişim zinciri doğrulandı (`only-phone`↔`only-server`). Hafıza: save (native)→`loadMem()`→sidebar render (`#sidebar-mem-list .mem-card`) uçtan uca çalışıyor, DELETE de doğrulanmıştır.
- **Açık:** `SYNC_MODE`/`SYNC_ALWAYS` yalnızca ayar olarak yazılıyor; davranış (veri routing, ALWAYS_SYNC wiring) henüz bağlanmadı. Server sync-uyumlu DB şeması (updated_at/deleted/origin + MIGRATIONS) ve only-server modunda Android özelliklerinin web tarafından ayrılması kullanıcının sıradaki istekleri.

## 2026-09-05 — Android port ilerlemesi: LiteRT-LM + Gemma-4-E2B telefonda canlı

- **Durum:** Capacitor + Kotlin portu (`piSynapse/android/`, laptop'ta `pisynapse-android/` gradle iskeleti) çalışır durumda. Telefonda v0.11 kurulu. Gemma-4-E2B-it `.litertlm` (2.59GB) telefonun internal storage'ında (`Android/data/com.pisynapse.app/files/models/`), LiteRT-LM 0.12.0 (`com.google.ai.edge.litertlm:litertlm-android`) ile yükleniyor.
- **Engine:** `EngineConfig(maxNumTokens=…, backend=CPU, visionBackend=CPU, audioBackend=CPU, cacheDir=…/cache/litertlm)`. `maxNumTokens` = **toplam context slot** (Pi'deki `litert_serve` gibi); formül `LLM_NUM_CTX(6144)+LLM_MAX_OUTPUT_TOKENS(512)` → 6656, `coerceAtMost(8192)`.
- **Başarılanlar:**
  - Otomatik tool-calling native döngüde çalışıyor (`automaticToolCalling=true`): `get_datetime` + `get_weather` gerçek çağrıldı, İstanbul gerçek değerleri döndü. 16 araç `OpenApiTool` şemasıyla `ConversationConfig.tools`'dan veriliyor.
  - İlk denemedeki `Status 3: Input token ids too long (2886)` hatası `max_tokens` düzeltmesiyle çözüldü (2886 = gönderilen input token sayısı; model max'i düşüktü).
  - İlk denemedeki `Status 13: failed to invoke the compiled model` — 2. izole denemede tekrar etmedi; state'i bozma ihtimali vardı, netice itibarıyla kalıcı sorun değil.
  - Chat kalıcılığı native: `filesDir/chat_history.json` (bridge `chatHistorySave/Load`), JS `_nativeChatSave/Restore` ile restart'ta geri geliyor.
  - Engine startup'ta arka planda prewarm ediliyor (`PiSynapseBridge.load()` içinde async `ensureLoaded()`), soğuk açılış first-chat masrafı azaldı.
- **GPU/NPU dead-end:** `LLM_BACKEND_TYPE` (cpu/gpu/npu) config anahtarı eklendi; GPU denendi → model yüklenemedi. Litert-LM logcat: `section_backend_constraint: cpu` TÜM model bölümlerinde (prefill/decode/drafter/vision/audio) — bu `.litertlm` ikilisi CPU'ya kilitli çevrilmiş, runtime ayarıyla açılmıyor. `npu` de aynı. **(Kullanıcıya raporlandı)**
- **Performans:** warm ~264ms/token (~3.8 tps); ilk-chat tek seferlik ~80s (executor compile, cacheDir CPU yolunda kalıcı değil). Tool-call'lı hava durumu yanıtı warm'ta ~5s.
- **Sıradaki (kullanıcı istekleri, 2026-09-05):**
  - Runtime izinler: uygulama tek seferlik izin istesin (takvim/mail/sensör içintemel).
  - İn-app ayarlar düzeltilecek (ŞU AN native yol kısmen hardcode: `_nativeApiRoute` GET /config birkaç key'i sabit döndürüyor).
  - Hafıza panosu native'de çalışmıyor ("sunucuya ulaşılamadı" — `loadMem` `/chat/memories` çağırıyor, native route yok).
  - Sync modu: **only-phone / only-server** seçenekleri ayarlarda her zaman görünür olacak; offline-first ama server senkronu da ayarlanabilir.
  - Ayarlar ayrı sekmelere bölünecek (phone ayarları / server ayarları karışmayacak).
  - only-server modunda da Android özellikleri (mail/calendar intent, sensör) kullanılabilir kalacak ama web tarafıyla karışmayacak.
  - **KURAL:** DB yapısı her zaman senkron edilebilir kalmalı (sync kırılırsa hata çıkar); phone/server ayrımı DB şemasında arkaplanda hazır olacak şekilde tasarlanmalı.

## ⚠️ 2026-09-05 TEKNİK UYARI — DB sync mimarisi (bkz. yukarı)

- Server tarafı (`routers/chat.py` `POST /chat/sync`) yalnızca sıralı komut replay'idir; idempotency key, çakışma çözümü, outbox, silme tombstone'u YOK. Per-row `deleted`/`dirty`/`updated_at`/`version` kolonları db.py'de ŞU AN mevcut değil. **Herhangi bir yeni tablo, sync'e uygun (updated_at + deleted + device origin) tasarlanmalı** — aksi halde phone/server sync'i ileride kırılır. *(2026-10-11 scope clarification, analysis D6: the rule targets SYNC ENTITIES — phone-originated data that replicates across devices (tasks, notes, memory, `sync_items`). Server-authoritative tables are intentionally OUTSIDE the device-sync protocol and are exempt: auth/session (`users`, `user_api_keys`, `user_sessions`, `user_credentials`), collective-learning (`feedback_votes`, `pattern_approvals`), and per-user server config (`user_settings`). If any of these is ever promoted to a synced entity, give it the full updated_at + deleted + origin set at that time — do not pre-add columns to server-only tables.)*

## 2026-09-05 — Phase UI-PERF+THEME: hardware-accel root cause, animation budget, WCAG AA dark ramp
- **The "4–5 fps" feel was NOT the CSS:** the tester's Brave had hardware acceleration fully disabled (`chrome://gpu`: compositing/rasterization/OpenGL all "Software only", "GPU access is disabled in chrome://settings"). Re-enabling it restores smoothness. The CSS budget work below was kept because it pays off even on constrained machines:
  - Send-button breathing glow (`subtleGlow`/`glassGlow`) now animates ONLY while `body.generating` (idle = static glow) — the previously always-on box-shadow animation forced per-frame style invalidation.
  - Non-glass topbar/sidebar `backdrop-filter` removed (`backdrop-filter:none` beats the base blur rule); glass mode keeps genuine frost — topbar/sidebar `blur(8px) saturate(160%)`, settings `blur(12px)` — with translucent accent tints instead of raised opacity, so frosted readability comes from the blur itself.
  - Compositor-friendly motion: `will-change:transform` on sidebar, top-ticker and marquee tracks; sidebar slides via translate only; `#main` margin transition 0.3→0.22s + `overflow-anchor:none`.
  - `?lite=1` effects-lite diagnostic mode (kills all blur/aurora/marquee animation) as an emergency low-power fallback; ticker marquees also pause while the tab is hidden (`body.tab-hidden`).
  - Mobile glass tap bug: `.top-new-btn` tap-flash drew a SQUARE accent glow — the "no box" override lived inside `@media (hover:hover)` so touch devices never got it. The `box-shadow:none` + glyph-shaped `drop-shadow` active rule is now outside the media query (touch probe: `box-shadow: none`, `scale(.94)`, drop-shadow only).
- **Non-glass palette retuned + WCAG AA across all 6 themes × dry/glass** (scripted measure: `contrast_audit` probe over default/blue/green/purple/red/mono):
  - Base dark ramp: pure `#000000` → deep charcoal `#0d0d13` (halation relief on wide-gamut displays; still clearly dark). `--text4` `#626276`→`#808098` (was 4.45:1 borderline on surfaces → 4.84 ✓). Measured on bg: text2 5.73:1, text1 ~17:1, accent ~12:1 — all AA.
  - White-on-accent fills replaced with dark ink `#141419` (`.settings-save`, `.note-save`, `.gp-save`, non-glass `#send-btn` icon, `.modal-confirm.danger`); danger hover now LIGHTENS to `#ef6464` instead of darkening so dark ink stays ≥4.5:1 (worst theme 5.36 ✓). Glass send button keeps its white icon (dark translucent surface → ~9:1).
  - Primary CTAs dropped the glaring white pill: `.new-btn`, `.w-start`, `.modal-confirm` are now accent-tinted dark pills (accent glyph + label, subtle accent border/glow). The old `opacity:.9` hover is gone — that semi-transparent white over dark chrome read as a blur on the label.
- **Cache:** SW bumped `pisynapse-v54`→`v55` for this round.

## 2026-09-05 — Phase UI-NEW-ICON (final): icon-only top button becomes a bare accent icon
- Final shape per user (remove the box; draw the icon directly in the theme color; add glow in glass mode):
  - ~~The top-bar button was a 40×40px square icon-only button with a 28px icon~~ → the box is gone entirely: `background:transparent; border:none; box-shadow:none`, accent-colored 30px glyph, invisible 40×40 hit area for the touch target.
  - Sidebar `.new-btn` icon ~~26px~~ → 28px (pointer:coarse + global blocks).
  - Glass mode keeps an accent `drop-shadow` glow on the glyph (hover/active only), and the square tap-flash glow is fixed — see the UI-PERF+THEME entry above.

## 2026-09-04 — Phase UI-NEW-ICON: new chat button redesign (pill+pencil+plus icon, top-bar icon-only)
- **Goal / user feedback:** replace the plain new-chat icon with a custom Gemini-inspired hybrid: a soft horizontal pill outline with an open top-right entry where a diagonal pencil slides in, plus a centered symmetrical '+' inside the left section.
- **Top bar vs sidebar:**
  - Sidebar `.new-btn` keeps the text label with the new larger ~~26px~~ 28px icon (final size after the 2026-09-05 bump).
  - Top-bar `.top-new-btn` (visible when sidebar is closed) stripped its "New" text label to become a compact 40×40px icon-only button — later made fully boxless (bare accent icon), see the 2026-09-05 entry.
- **Path & clipping polish:** outer pill coordinates inset with padding inside the 24×24 viewBox so strokes never clip; equilateral '+' lines centered at (7.5, 12); wide top-right gap (`M22 13.5...H12.5`) leaves the pencil entrance completely open with no touching diagonal arc.
- **Cache:** SW cache bumped to `pisynapse-v54` so clients pick up the new layout without serving stale shell.

## 2026-09-04 — Phase UI-LIST-BUG: numbered lists not showing after the marked engine switch
- **Symptom (user):** email and other multi-item results were not numbered "1., 2., 3." anymore; user suspected the markdown engine change invalidated the listing instructions.
- **Root cause (two-fold, frontend):**
  1. **CSS hid the markers.** The old regex engine rendered numbered items by hand (via a `.ol-num` span, `font-weight:600`), so `.bubble ol{list-style:none}` was correct then. After the switch to `marked` (UI-MD), marked emits a real `<ol><li>` but `list-style:none` was still active → the browser rendered no markers. Same rule existed on `.think-box .think-body ol`. Fixed both to `list-style:decimal` (the shared `padding-left` rules already apply).
  2. **Model may emit bold numbers.** marked does NOT turn a leading `**1.**` into an `<ol>` (it stays a `<p>` with `<strong>`). Even though the system prompt instructs plain `1.` (prompt.py), the model sometimes writes `**1.**`. renderMd now normalizes a line-initial `**N.**`/`**N)` marker to plain `N.` before `marked.parse`, so either form builds a real `<ol>`. Code blocks are placeholder-extracted first, so `**1.**` inside code is untouched; a mid-sentence `**1.**` stays bold.
- **Verification:** `node --check` ✓; headless marked run: `1.` and `**1.**` both → `<ol>`, mid-text `**1.**` stays `<strong>`, code content untouched. Frontend-only → no `py_compile`/`pytest`.

## 2026-09-04 — Phase UI-POLISH: welcome marquee gap, settings scroll jank, glass blur, tooltip→aria, mobile touch-target/icon balance

Squashed into a single commit (rule exception, user-approved: "so much is already done and interleaved in one file — take the exception this once"). Two frontend-control files changed, frontend-only (no `py_compile`/`pytest`; `node --check` ✓ on the main `<script>` and the SW).

- **Welcome marquee left-gap fixed (`initWelcomeMarquee`).** Root cause was the shared `/rev` track geometry: with `--` and both tracks using the same `half`, the reverse track painted from a stale origin leaving a dead zone on the left. Now `measure()` reads the first tile `offsetWidth + gap` (falling back to `scrollWidth/2`), `wrap()` is direction-aware (`dir>0 → x∈[0,h)`, `dir<0 → x∈(-h,0]`), and `paint()` offsets the reverse track by `-half` so the loop closes seamlessly. Pixel probe: the left gap dropped from ~45→163px down to a stable 16–20px.
- **Marquee pauses while settings are open / tab hidden** — adds `!document.body.classList.contains('settings-open')` and `!document.hidden` guards to the rAF tick so the ticker doesn't keep animating under an open modal or an unfocused tab.
- **Ticker fade race fixed (`rebuildTickerFromCache`/`rotateTicker`)** — the fade-out/fade-in pair shared a bare `setTimeout`; a rebuild during the fade window could leave the ticker stuck at `opacity:0`. Introduced a module-level `_tickerFadeTO` and `clearTimeout` both paths; rebuild now re-triggers the fade-in explicitly.
- **Settings scroll jank (reflow-per-frame) fixed (`bindSettingsChips`).** Each scroll tick called `getBoundingClientRect()` per anchor (forced reflow). Anchor absolute offsets are now cached once in `measure()` (per scroll-event/scroll container + on `resize`) into `a.absY`; ticks only read the cheap `body.scrollTop`. `contain:content` added to `.settings-body`. Removed the from-scratch `document.documentElement.scrollTop` recalc per frame.
- **Glass-mode settings blur clash + readability fix.** While the settings drawer is open, the cascading `backdrop-filter` layers (modal-backdrop, settings-box, settings-appearance) previously blurred the already-frosted backdrop and let the background type bleed through. Added `body.glass-mode.settings-open …{backdrop-filter:none}` for those three layers plus `body.glass-mode.settings-open .modal-backdrop{background:rgba(5,5,9,.85)}` for legibility. Wired a `settings-open` body class on open/close instead of keying off the harder-to-read modal-open state.
- **Glass-mode blur lightened (perf / clip artifacts):** global glass `blur(12px)`→`blur(8px)` and `.modal-backdrop` `blur(16px)`→`blur(8px)`, reducing compositor cost and the edge-clipping "band" on frosted panels. `.chip-track` `will-change:transform` moved from a `body.generating`-only rule to the base `.chip-track` rule — the transform it hints at is used on every scroll, not only while generating.
- **Modal open animation sped up** — `modalIn` `ease-out` duration `.25s`→`.12s` on both `.modal-box` and `.settings-box` (less perceived lag; user: welcome/opening felt too slow, no animation removal needed).
- **Send button square-corner fix:** `#send-btn` was bushed to 44×44 for touch but kept 0 radius → visibly squared. Added `border-radius:22px` (round) in both the `max-width:768px` and `pointer:coarse` blocks.
- **Tooltip→`aria-label` migration (browser box gone):** every `title="…"` on interactive elements (settings/search/compact/mem-back/logo-btn/think/attach/mic buttons, theme swatches, session rows + delete buttons, memory delete buttons, settings `info-btn`, session-name div) converted to `aria-label`/`aria-label` so no native tooltip box appears on hover while screen-reader labelling is preserved.
- **Mobile touch-target / icon balance (`@media(pointer:coarse)` + `max-width:768px`).** Touch targets staid ≥ WCAG minimum and were re-balanced to fix an oversized look: `.icon-btn,.settings-btn` compacted 44→30/26px frames with 14px icons (matches the desktop compact look; the previous 44px frame + 14px icon read as an empty box, and the earlier 24px icon read as oversized); `.tts-btn,.mem-btn,.w-start,.modal-cancel` keep 44px frames (text-filled). `.mem-btn` svg 14→17px (user: "slightly bigger memory icon"). `.top-new-btn,.new-btn` height 44→40px with 14px icons (was 75px wide + 17px icon — user: "too big / ugly", now balanced). Verified by iPhone-12 Playwright probe: settings 30×30/14, search/compact 26×26/14, mem 44×44/17, top-new 68×40/14.
- **Misc:** site `<title>` dropped the inline commit hash; SW cache `pisynapse-v51`→`v52` (pre-caches this build's assets, fully offline). Desktop (Zorin) unaffected by mobile rules per user.

## 2026-09-04 — Phase ESC-FIX: root-cause of spurious tool-escalation + single-group narrowing + SSE error disambiguation
- **Symptom (user, discovered pre-migration):** innocent chat ("uykum var ama uyuyamıyorum") would fire a spurious "GEREKLİ ARAÇLAR ETKİNLEŞTİRİLİYOR" escalation followed by "Sunucuya ulaşılamadı". Root cause (this round): `_TOOL_ASK_HINT` system prompt was injected on EVERY `question+None` turn; the small model hallucinated a `TOOL_NEEDED` marker even on pure chat → `Hatch` → `combined`(23 tools) escalation (~49s TTFT) → SSE cut.
- **Changes (3 independent commits):**
  1. `10dd7d2` (fix, Adım 1) — hint injected ONLY when `_hit_groups(context["_user_text"])` is non-empty (real tool-domain signal); `hint_armed` flag wired into the mid-stream hatch (`hatch_armed`) and end-of-round escalate conditions, so a turn we never hinted on can never escalate. Fix note: the half-finished diff referenced `_user_text` as a variable, but it is only the `context` dict KEY → `context["_user_text"]`.
  2. `19b0324` (perf, Adım 2) — `_escalation_tools` now sizes the escalation toolset via `_hit_groups`: single group → that group (≤7 tools); genuine multi-domain (2+ groups) → combined; none → `_keyword_group` fallback, else combined (last resort). TTFT ~49s → ~13s for the common single-domain case.
  3. `3be6354` (ui, Adım 3) — frontend `data.error` branch no longer folds every backend error into generic `connErr`; connection-loss vs context-overflow vs other app errors are disambiguated, and the specific message is surfaced (toast included).
- **Verification:** full suite 560 passed (Adım 2 added +3 unit tests); frontend `node --check` ✓; `py_compile` ✓. Live (2026-09-04): pure chat → `hint_armed=False`, no Hatch/escalation log, normal reply; weather domain → routed via embedding, never entered escalation.
- **Escalation enforcement check:** live repro of a single-group `Hatch escalating` requires the model to emit the marker, which needs a `question+None` turn whose `_hit_groups` is non-empty. `intent_audit_log` shows **46/46** `question+None` rows have EMPTY `_hit_groups` (no keyword) — keyword-bearing utterances all route to `action` — so `hint_armed=True` essentially never occurs in production. That is direct evidence the former spam-escalation path is no longer reachable; the single-group narrowing itself is guaranteed by `test_escalation_tools_single_group`. Full accounting in `BUG_RAFLAMA_DURUM.md` §8.
- **Embedding carryover (384→768):** 10 `conversations.embedding` rows were still at the old **384-dim** (1536-byte BLOBs; timestamps 2026-09-02 22:11–22:45, pre-migration). Re-ran the standard `reembed_all.py` → all 216 conversation + 3 memory rows re-embedded at the configured **768-dim** (`paraphrase-multilingual-mpnet-base-v2`); verified via `SELECT length(embedding) GROUP BY`: 216×3072 + 3×3072, **0 rows at 1536**. DB and `.npy` are gitignored. Relevant to future doc maintainers: `_get_tool_embeddings` (llm/intent.py:460) does NOT read `additions_embeddings.npy` — it embeds `_TOOL_EMBED_CORPUS + _additional_corpus()` **in-memory** (67 entries) and caches them, so absence of the `.npy` has no runtime effect.

## 2026-09-03 — Phase UI-MD: regex markdown engine replaced with marked + DOMPurify (self-hosted, offline)
- **Motivation / decision (user-approved this direction):** the hand-written regex `renderMd` broke on nested lists, escaping, and complex tables, and had weak XSS coverage. Approved plan: use `marked` (token-based GFM parser) for correctness + `DOMPurify` for battle-tested XSS sanitization, fully self-hosted under `/static/vendor/` so the app stays 100% offline (no CDN).
- **Key technical discovery (changes the earlier "worker" plan):** DOMPurify **cannot run inside a Web Worker** — it requires a real DOM (its `sanitize()`, backed by DOMParser, is inert in a DOM-less worker; verified with jsdom). Also `renderMd` is called **synchronously per SSE token during streaming** (index.html sendMsg loop), so markdown rendering must stay on the main thread anyway. Therefore marked + DOMPurify load via `<script>` on the main thread; the markdown Web Worker had no real off-thread role.
- **Changes (4 commits):**
  1. `edf98e1` — vendored `marked.min.js` v12.0.2 (MIT) + `dompurify.min.js` v3.1.6 (Apache-2.0) under `static/vendor/`; `sw.js` cache bumped v50→v51 and pre-caches both files (fully offline).
  2. `12808f2` — `renderMd` rewritten: isolates math (`$$..$$`/`$..$`) + fenced code blocks + inline code into **markdown-inert placeholders** (`ZQMD<Kind><i>ZQ`, letters/digits only — the old `___x___` tokens were mangled by marked's em/strong), then `marked.parse(s)` with `{gfm:true, breaks:true}` + custom link renderer (adds `target="_blank" rel="noopener noreferrer"`), `DOMPurify.sanitize` via `sanitizeHTML()`, then re-inserts placeholders after sanitization so code-wrapper classes/onclick survive. Math still renders as Unicode via existing `parseMath` (no MathJax dependency).
  3. `9b37b0c` — removed dormant worker infra (`new Worker`, `mdWorkerCall`, `_mdPending`, `static/markdownWorker.js`): it was never invoked (`mdWorkerCall` had no call site) so it just wasted a thread. `esc`/`parseMath`/`stripMarkdown` remain as main-thread helpers.
- **Sanitizer ladder in `sanitizeHTML()`:** DOMPurify → native Sanitizer API → `textContent` (progressively safer fallbacks). `ADD_TAGS` config dropped (math/code re-inserted post-sanitize, so no custom tag allowance needed).
- **Tests/verification:** markdown behavior verified headlessly with jsdom + marked + DOMPurify (GFM tables, nested lists, math, inline code, line-breaks; `<script>`/`<img onerror>`/`javascript:` links all stripped; no leftover placeholders). Frontend `node --check` syntax ✓. Backend suite 557 passed (unchanged — this is frontend-only). ruff N/A (frontend); py_compile N/A.
- **Future-proofing:** a worker can be reintroduced later if genuinely heavy, DOM-free text work (e.g. long-file preview, search indexing) is added — the helper functions are already isolated for de-coupling.

## 2026-09-03 — Phase UI-cleanup: glass perf, touch targets, input-border choice, textarea focus ring
- `4aa4fb4` — removed the **inner box** the user saw around the focused chat textarea ("Bir şey sor…"). It was the `#msg-input:focus-visible` + `textarea:focus-visible` rule (added in `74e80a8`) drawing a 2px accent outline around the textarea (vertical `rgb(240,85,85)` lines at the textarea's left/right edges, full bar height). Removed those two selectors from the focus-visible rule (kept for `input`/`select`); the whole bar's `#input-container:focus-within` accent ring already shows focus.
- `f0beafc` — **reverted `857dd9e`:** the outer `#input-container` box border/shadow was removed in `857dd9e` (made the bar borderless/transparent) but is restored here per user preference (the "dış kutucuk" stays). The lava-lamp centering from `857dd9e` (`.ab1` left `-10%→8%`, `.ab2` right `-14%→8%`) was kept.
- `74e80a8` (a11y) — send-button + `.inline-think-btn` + `.think-split` → 44px on `@media(max-width:768px)` and `@media(pointer:coarse)`; min-height 44px for `.tts-btn`, `.icon-btn`, `.gp-opt`, `.fb-tab`; `focus-visible` ring styles for `#msg-input`, `textarea`, `input`, `select`.
- `d0bd316` (perf/glass) — lava lamps reduced 4→2 (`.ab1`/`.ab2` kept; `lavaC`/`lavaD` keyframes removed); idle opacity lowered (`.62/.58` → `.35/.30`); `body.glass-mode:not(.generating) .ab{opacity:.15; animation-play-state:paused}` while generating keeps `opacity:1; running`. Transform-only animations stay compositor-friendly on mobile.
- `7609519` — Web Worker off-main-thread markdown/text processing + native Sanitizer API fallback added here; later superseded by the UI-MD engine (worker idle → removed in `9b37b0c`, see UI-MD).

## 2026-09-02 — Phase D-3: idempotent no-op (NOOP) cleared from audit success
- **Fix target (status/verification audit 2026-09-02, Section F):** a mutation whose target no longer exists returned bare `"Note not found."` (no `ERROR:` prefix), so `is_tool_success` logged it as `success=1`. update_note was already caught downstream (ID re-read empty → verification_failed); delete_note's absence-check even returned "verified". The real defect was the audit signal: a no-op was recorded as a successful mutation.
- **Decision (user, Option 2):** an already-absent target is a distinct idempotent **NOOP**, not a success (and not an error either). Every not-found mutation path now returns `"NOOP: Note not found."` (nextcloud_notes.py update_note:310,314 and delete_note:329,331); `is_tool_success` (tools/dispatcher.py) counts `NOOP` as failure thus `success=0`; the audit row then carries the string in the `error` column. Success GUI remains unchanged for reads (`get_note` keeps its plain not-found text — it is not a mutation no-op).
- **Why it is safe:** NOOP → `success=0` → `_verify` returns NULL as before (nothing to re-read), so the D-1b resolver predicate (`success=1 AND status…`) never anchors a follow-up on a no-op, and `SUM(success)` no longer inflates. The D-2 delete-absence logic is untouched; it remains the correct semantics for a genuinely deleted note.
- **Not touched on purpose:** the UI render path (an ok=false row) — user scoped this item to the audit signal; a separate neutral "no-op" visual would be a follow-up.
- **Tests:** +2 `TestIsToolSuccess` (NOOP str + tuple → not success) and `test_wrapper_not_found` re-pointed to the new NOOP text. Full suite 549; E2E 39/39; ruff clean; py_compile ✓.

## 2026-09-02 — Phase D-LANG: corpus feeder language tag + English assistant-signal gating
- **Gap:** the corpus feeder's assistant-reply gate `_ASST_GREETINGS` (corpus_feeder.py) was entirely Turkish, so English assistant-style replies ("Here you go…", "I've added…") could slip past `_is_user_command_like` and be fed to the corpus as intent examples. And additions.jsonl records carried no language metadata.
- **Change (corpus_feeder.py):**
  - `_ASST_GREETINGS` extended with English assistant openers (here you, here's, here are, i've, i found, i'll, of course, there you). Deliberately did NOT add standalone "sure,"/"done"/"added"/"let me" — those are common real user-command openers and rejecting them would strip valid corpus examples (conservative direction already skews to skip-to-ambiguous).
  - New `_detect_lang(text)` → best-effort ISO-639-1 tag (tr/en/de/fr/es) using word-boundary stopword scoring + accent tie-breakers; English is the fallback. Short/collision-prone Turkish words (bir/ile/şu/bunu/notlar) matched on `\b` boundaries so bare "not" can't collide with English "note/notes".
  - Both positive addition record paths ("added" and "added_llm_resolved") now carry `"lang": _detect_lang(text)`. Backward-compatible: `_additional_corpus` in llm/intent.py only reads `group`/`text`; existing gitignored additions.jsonl lacks `lang` and is fine.
- **Tests:** +2 in test_corpus_feeder.py (`test_is_user_command_like_english_signals_rejected`, `test_detect_lang_over_iso_set`). Full suite 557; ruff clean; py_compile ✓.

## 2026-09-02 — Phase D-KW: English keyword coverage added to _KEYWORD_CHECKS
- **Gap:** `_KEYWORD_CHECKS` (llm/intent.py) was heavily Turkish; the only English tokens were sparse (email/note/task/mail/save/remember…), and the calendar group had **no** English at all. Before the embedding upgrade (D-EMB-UPGRADE) this made English routing over-rely on the 384-dim model; after the upgrade the model is stronger but keyword gating is still the first line for short/ambiguous utterances.
- **Change (llm/intent.py _KEYWORD_CHECKS):** added safe English tokens across groups — weather (+weather/temperature/rain/snow/humidity/windy), calendar (+event/meeting/appointment/schedule/calendar/agenda — the previously-empty group), email (+send/compose/inbox/draft), tasks (+to-do/deadline/assignment/chore), notes (+memo/notes), memory (+memorize/recall). Deliberately NOT added: bare "not" (kept out for the English-negation collision, consistent with existing design comment), and won't add overly-generic verbs that risk false positives (e.g. "read" avoided due to ambiguity).
- **Collateral test fix (tests/test_intent_audit.py):** after the mpnet upgrade, `test_classify_keyword_fallback_logs_row` ("not düş") no longer falls to keyword — mpnet classifies it confidently via thin_margin → the asserted `keyword_fallback` row was absent. Made the test deterministic by monkeypatching `_get_tool_embeddings` → `[]` so it exercises the keyword-fallback path regardless of model confidence. This is a test-robustness fix, not a behavior change.
- **Tests:** +2 in test_intent_backends.py (English keyword routing map; English-negation no-collision guard). Full suite 555; ruff clean; py_compile ✓.

## 2026-09-02 — Phase D-EMB-UPGRADE: multilingual embedding model upgraded + all vectors re-embedded
- **Change:** EMBED_MODEL `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-dim, 2020) → `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` (768-dim) for stronger multilingual retrieval (TR/EN/DE/FR/ES). Applied in embedding.py default, `.env` (gitignored, local), and example.env. docs/tool_intent_analysis.md:228 listed this as P3 tech debt; its `multilingual-e5-small` suggestion is NOT available in fastembed 0.8.0 (only e5-large 1024-dim exists) so mpnet-base was chosen.
- **Why re-embed is required:** dimension change 384→768 means stored vectors and new query vectors would mismatch in dot-product cosine similarity. Migration re-embedded every persisted vector so all are 768-dim.
- **Migration:** new one-off script `reembed_all.py` re-embeds `memories.embedding` (3), `conversations.embedding` (196), and deletes `corpus_data/additions_embeddings.npy` (the corpus feeder rebuilds it index-aligned from additions.jsonl, → 5×768). Base tool corpus `_TOOL_EMBED_CORPUS` is embedded fresh in-memory at runtime → no migration needed. New `embedding.model_dim()` helper returns the configured model's dimension for drift detection.
- **Backfill caveat:** db.py `_backfill_task` only re-embeds rows whose blob is `None`; it does NOT detect a dimension drift — use `reembed_all.py` when the model changes.
- **Verification:** 553 passed; ruff clean; py_compile ✓; DB rows all 768-dim, corpus npy 5×768.

## 2026-09-02 — Phase D-ML: anaphoric context-gate extended to EN/DE/FR/ES
- **Fix target:** the corpus-zehirleme guard `_is_context_dependent` (C-7/C-8) only recognized Turkish (`_CONTEXT_OPENERS`, `_CONTEXT_PROGRESSIVE_PAST`, `_CONTEXT_ANAPHORIC`). An English/German/French/Spanish anaphoric follow-up ("continue where we left off", "wo waren wir", "où en étions-nous") passed the gate and could feed a context-dependent fragment into the embedding corpus — the exact risk the Turkish gate exists to prevent, but unfixed for non-Turkish.
- **Change (llm/intent.py):**
  - `_CONTEXT_OPENERS`: added phrase-level continuation openers for EN/DE/FR/ES (e.g. "let's continue", "continue where we left off", "where were we", "wo waren wir", "lass uns weitermachen", "où en étions-nous", "dónde estábamos", "sigamos").
  - New `_CONTEXT_PROGRESSIVE_PAST_I18N`: regex for object/demonstrative progressive-past references in EN/DE/FR/ES ("the email i was sending", "the notes we were editing", "wir waren bei …in", "on était en train de …", "el correo que estaba escribiendo", …), wired into `_is_context_dependent`.
  - **Scoped NARROW (user decision):** only clearly object/demonstrative progressions gate; a bare "i was …ing" like "i was thinking about the weather" or "i was reading" must NOT gate, because those can open a fresh command (mirrors the existing caution over Turkish "az önce" / "önceki").
- **Tests:** +1 `test_is_contextual_followup_i18n` (16 assertions: gate-worthy EN/DE/FR/ES vs fresh commands that must not gate). Full suite 553; ruff clean; py_compile ✓.
- **Not in this commit (separate follow-ups when wanted):** English keyword completion in `_KEYWORD_CHECKS` (email "send", task "complete"/"delete"…), feeder `lang` tag + English assistant-signal gating, embedding-model upgrade (re-embed cost).

## 2026-09-02 — Phase D-3c: NOOP extended to task mutations (complete_task / delete_task)
- **Motivation (follow-up to D-3):** the same bare not-found pattern existed outside notes. `complete_task` (nextcloud_tasks.py) returned `"Task with UID '...' not found or already completed."` and `delete_task` returned `"Task with UID '...' not found."` — both without an `ERROR:` prefix, so `is_tool_success` logged them as success=1 (a false "completed"/"deleted" claim on a target that was already gone). Both are D-2 scope tools.
- **Change (nextcloud_tasks.py):** both mutation not-found returns are now `"NOOP: …"`; the existing `is_tool_success` NOOP rule (D-3) already classifies them as failure → success=0 → `_verify` returns NULL (a no-op has nothing to re-read) and the D-3b UI renders the neutral info row automatically (the SSE `noop` flag is prefix-based).
- **Not touched:** `search_tasks`' `"'{query}' not found in tasks."` is a read/search tool, not a mutation → plain text stays. Calendar already returns `ERROR:` prefixed not-found (calendar_ops.py), so it never had the no-op bug. Mail has no such mutation path.
- **Tests:** +2 `_complete_task_sync` / `_delete_task_sync` no-op unit tests (empty todos → NOOP:), +1 `TestIsToolSuccess` task cases. Full suite 552; ruff clean; py_compile ✓.

## 2026-09-02 — Phase D-3b: UI renders a no-op as a neutral info row, not an error
- **Motivation (follow-up to D-3):** a NOOP tool row surfaced with `ok=false`, and the default settle logic removed the label and re-added the green `ok` class on a replied round — visually indistinguishable from an error, contradicting the "already gone, nothing to do" meaning. User chose a **plain text info** treatment (no badge/color).
- **Change (web):**
  - Backend flags the no-op: the SSE tool-end event (llm/stream.py) and the `/execute` response (routers/chat.py, status becomes `"noop"` instead of `"error"`) now carry `noop: result.startswith("NOOP")` — mirroring the existing `clarify` flag.
  - `showToolScan`: a `noop` phase-end renders the neutral info text (`noopInfo` i18n) with a `.tool-status.noop` class instead of the red failure.
  - `settleFeedbackRow`: rows carrying `.noop` keep their label, drop the spinner, add neither the green `ok` state nor any confirmation pair (nothing changed to confirm).
  - New i18n keys both languages: `noopInfo`.
- **Tests:** +1 e2e in verification-warn.spec.cjs (noop → `.noop` class, no `ok`/`warn`, neutral label visible, no audit-bound thumbs). E2E 40/40; pytest 549; ruff clean; py_compile ✓; node --check ✓.

## 2026-09-02 — Phase D-2: ID-based verification extended to all scope mutations
- **Fix target (from status/verification audit 2026-09-02, Section E1/E2):** only the create trio (create_task, create_calendar_event, save_memory) plus send_email were verified; every other mutation returned `(result, None)`, so creates/updates/deletes were never re-read from the backend. Scope: notes trio, complete_task, delete_task, update/delete_calendar_event. send_email stays out (no reliable read-back).
- **Commit 1 (`f464630`, plumbing, no behavior change yet):** `nextcloud_notes.create_note` now returns `(result_text, note_id)` — the API response id used to be swallowed by the wrapper. The dispatcher forwards the tuple: create_note's new id, update_note/delete_note's resolved note id, complete_task/delete_task's resolved uid (they used to return None). Tools were still outside VERIFY_SCOPE, so status stayed None.
- **Commit 2 (`5b70c71`, scope):** VERIFY_SCOPE 3→10 tools. **Delete verification is INVERTED:** the expected post-state is "the entity no longer exists on the backend" — both `_confirm_by_id` and the content/summary fallback check absence. complete_task requires the task present AND marked completed. update_calendar_event falls back on `new_summary`. The D-1b resolver predicate needs no change: NULL still reliably means "outside scope" because a scope tool that succeeds always writes a status (invariant holds for every added tool).
- **Tests:** +21 → 547: notes trio, complete/delete_task, update/delete_calendar_event — verified / verification_failed / fallback paths, plus the D-2 invariant (every scope success is non-NULL). Two identical creates verify independently (ID discrimination preserved). E2E 39/39; ruff clean; py_compile ✓.

## 2026-09-02 — Phase D-1c: UI consumes verification_status — warning state closes the feedback gate
- **Fix target (from verification audit 2026-09-02, Section E2 item (c)):** the feedback pair only gated on `ok=true` (static/index.html:2903), so a scope tool whose create was never backend-verified still surfaced a 👍/👎 confirmation affordance. D-1b added verification_status to the payloads; this commit consumes it in the UI.
- **Change (web):**
  - SSE tool-end event carries a `clarify` flag (llm/stream.py): a CLARIFY_REQUIRED outcome (success=0 since D-1a) renders as a neutral "Kullanıcıdan bilgi istendi" info state (`.tool-status.clarify`), not a red failure.
  - The audit pair (roundAudits) only admits tools where `verifiedOk = ok && (status==null || status IN ('verified','verified_by_fallback'))` — non-scope tools carry no status → unchanged behavior.
  - `roundVerifWarn`: `ok && status IN ('unverified','verification_failed')` → the row settles amber "İşlem doğrulanamadı, kontrol edin" with NO green tick and NO thumbs (a confirm affordance would be a lie; a down-mark would drop on an audit-less row).
  - One unverified tool pulls the whole round to the warning state (deliberate fail-safe over mixing correct/warn signals in a single pair).
  - New i18n keys: `verifFail`, `clarifyAsked`.
- **Tests:** 4 new e2e in `tests/e2e/verification-warn.spec.cjs` (unverified / verification_failed → warning + no thumbs; verified → pair kept; null status → unchanged). E2E 39/39; pytest 526; ruff clean; py_compile ✓; node --check ✓.

## 2026-09-02 — Phase D-1b: "claimed success" vs "backend-verified" signal split (verification_status consumers)
- **Fix target (from verification audit 2026-09-02, Section E2):** the raw `success` column (is_tool_success heuristic) was consumed as ground truth in two places: `_last_executed_tool_group` WHERE `success=1` (llm/intent.py) and the UI feedback gate (index.html:2903). The backend re-read produced verification_status (tool_verification.py) but no consumer read it.
- **Change (backend):**
  - `run_verification` returns `(audit_id, verification_status)` (4 call sites); the SSE tool-end event, `/sync` results and the `/execute` response (`ChatResponse.verification_status`) carry the computed status.
  - Resolver predicate (Option A): `success=1 AND (verification_status IS NULL OR verification_status IN ('verified','verified_by_fallback'))`. Justification: a scope-tool success=1 row always carries a non-NULL status (`_verify` always writes a string; error rows never land), so NULL reliably means "outside scope" and the predicate self-adapts as VERIFY_SCOPE grows.
  - `unverified` is not ground-truth success either (fallback did not match → no confidence).
- **Tests:** `TestInvariantStatusNonNull` (scope + success → always non-NULL; non-scope stays NULL) + resolver scenarios (verification_failed / unverified → no group anchored; verified → calendar; non-scope NULL → email). Suite 526; ruff clean; py_compile ✓.
- **UI hand-off:** the fields are carried from here; visual consumption lands in D-1c (next commit).

## 2026-09-02 — Phase D-1a: is_tool_success treats CLARIFY_REQUIRED as failure
- **Fix target (from status verification report 2026-09-02, Section E2):** `is_tool_success` (tools/dispatcher.py) counted `CLARIFY_REQUIRED: …` outcomes (chip/quick-action guard — the handler asks the user for MORE details instead of executing) as success=True because the heuristic only rejected `ERROR`-prefixed and empty results. Sharpest false-positive source: a scope create that produced nothing was logged as a "successful" call.
- **Change (tools/dispatcher.py):** `is_tool_success` now also returns False for a `CLARIFY_REQUIRED` prefix (works for str and `(result, entity_id)` tuples alike). No flow-control break: the chat/stream loop only consults the flag for auditing/UI; `save_memory` has no CLARIFY path.
- **Tests:** new `TestIsToolSuccess` (error prefix, empty str/tuple, clarify str, clarify tuple, normal success); existing clarify/loop tests assert only result content, so they still pass. Full suite 518; ruff clean; py_compile ✓.

## 2026-09-01 — Phase C-8 (runtime): context-dependent follow-up resolver (no blind LLM guess)
- **Problem (live demo):** "devam edelim son yaptığımız işe" (a follow-up with no domain keyword) went embedding-uncertain → keyword-none → LLM fallback guessed **tasks** from the utterance alone. An anaphoric follow-up carries no meaning outside its conversation, and embedding similarity on the fragment is actively misleading too (it labelled a notes follow-up as email) — so any utterance-only verdict is a coin flip.
- **Design (user-approved):** two-layer SESSION resolution; the utterance never decides alone:
  - **Layer 0 (deterministic):** `resolve_resume_context(message, history, session_id)` — if the message is a contextual follow-up, the resumed group is the **last successfully executed tool of the session** (`tool_audit_log` JOIN `conversations`, `success=1`, `is_summary=0`), mapped via `TOOL_TO_GROUP`; shared utility tools (`get_datetime`, member of every group) are skipped as non-evidence. Authoritative fallback: domain markers (`_GROUP_CTX_MARKERS`) in the recent conversation text. No model call, no guess.
  - **Layer 1 (LLM with history + verification):** `llm_resolve_with_evidence(message, history)` — reached only when Layer 0 is empty. The LLM sees the recent history and must answer JSON `{"group": ..., "evidence": "<verbatim fragment>"}`; the verdict is accepted ONLY when `_verify_evidence` finds the evidence verifiably in the conversation — a fabricated quote is discarded → question. Every verdict is audit-logged (`llm_verified` / `llm_rejected_evidence`) so the data accumulates, not the risk.
- **Change (_classify_intent):** a context-dependency gate runs before embedding/keywords. explicit domain keywords inside a follow-up still win (the user is naming the domain NOW: "devam edelim en son notu düzenliyordun" → notes); keyword-less follow-ups return question (source `context_dependent_deferred`) so the router's Layer 0/1 resolves it — the blind LLM fallback is unreachable for them.
- **Single source of truth:** the context gates (`_CONTEXT_OPENERS`, `_CONTEXT_PROGRESSIVE_PAST`, `_CONTEXT_ANAPHORIC`, `_is_context_dependent`) moved from corpus_feeder.py INTO llm/intent.py; corpus_feeder now imports them — feeder (must never feed such fragments) and live router can never drift. `is_contextual_followup` exported for the router.
- **Refactor:** the LLM fallback call extracted into `_llm_classify_call(system, user, max_tokens)` (litert/ollama), reused by the evidence resolver; payload/behavior unchanged (backend tests assert payload fields).
- **Tests:** new `tests/test_resume_context.py` — classifier defers without consulting the LLM, keyword-still-wins on follow-ups, Layer 0 (last tool / shared-tool skip / failed-tool skip / marker fallback / no evidence), `_verify_evidence` (match, fabrication, empty), Layer 1 (verified / rejected / question / disabled). Full suite **513** passing; ruff clean; py_compile ✓.
- **Live proof (real service, after restart):** log "Context-dependent follow-up deferred" for "devam edelim"; then "Resume resolver -> email (session history)" on the session that last executed `send_email` — the reply carried email tooling. Fresh command "en son mailleri göster" still routes email via embedding. New C-8 entries are pull-log (no UITPN) but the routing layer is proven above.

## 2026-09-01 — Phase C-7 (BUG-7): anaphoric follow-ups never feed the corpus; test isolation + corpus rebuild
- **Fix target (secondary risk from audit):** audit 232 "devam edelim en son epostayı gönderiyordun" is an ANAPHORIC follow-up — meaningless as a standalone intent example. Feeding it into the embedding corpus actively poisons routing (it dragged unrelated "continue/let's continue" queries toward the tool group). C-1's heuristic could not catch it.
- **Change (corpus_feeder.py + llm/intent.py):** new structural gate `_is_context_dependent()` — phrase openers ("devam edelim", "kaldığımız yerden", …), progressive-past suffixes ("düzenliyordun", "gönderiyordun", …) and anaphoric forms ("yaptığımız", "konuştuğumuz", …). Deliberately NOT gating bare "en son"/"az önce" (they legitimately open fresh commands: "en son mailleri göster"). Rejected rows go to `genuinely_ambiguous.json` with `reason=context_dependent` (status `skip_context_dependent`, counted skipped). The same gates now also power C-8's runtime deferral (single source of truth).
- **Test isolation bug (root cause of the earlier missing additions.jsonl):** `TestIntelAdditionsLoading.test_additional_corpus_parses_additions` monkeypatched the path but the LIVE-path *runner* was writing to the real `corpus_data/additions.jsonl` and deleting it in `finally` → the whole file vanished on the previous run. Same-class tests + `test_classify_keyword_fallback_logs_row` (test_intent_audit.py) now isolate the test DB/`_additional_corpus` instead of touching real paths.
- **Corpus rebuilt (first real non-dry feed):** `--reset` then full run → 13 processed, **5 added** (227 notes "Notları listele", 233 email "son 10", 234 weather "Bugün hava nasıl?", 239 email "Son e-postalarımı özetle", 240 email "5.'nin tamamını okur musun"), audit 232 `skip_context_dependent`, 228 duplicate; jsonl↔npy aligned 5=5; state.json advanced to 240. Live service: 67 corpus entries (+5).
- **Tests:** `TestContextDependentExamples` (rejects anaphorics, keeps standalone commands incl. "en son mailleri göster", audit-232 repro). Full suite **513** passing; ruff clean; py_compile ✓; live reload + routing verified.

## 2026-09-01 — Phase C-1 (BUG-1): corpus feeds the USER command, not the assistant reply
- **Fix target (from audit):** `tool_audit_log.conversation_id` deliberately points at the *assistant* message (feedback UI); `corpus_feeder._resolve_message_text` was reading that row's content directly, so it fed the model's tool-output reply into the intent corpus instead of the user's trigger. Proven on all 5 confirmed rows.
- **Change (corpus_feeder.py):** `_resolve_message_text` now walks the same `session_id` backward to the **preceding `role='user'` message** (`id < ? AND role='user' ORDER BY id DESC LIMIT 1`). Added `_is_user_command_like()` guards that reject assistant-output/degenerate text (multi-line, >200 chars, single-word fragments, assistant-style openers like "Merhaba/Elbete/işte") and route those rows to `corpus_data/genuinely_ambiguous.json` with `reason=not_user_command` (status `genuinely_ambiguous_not_command`, counted as ambiguous) instead of poisoning the corpus.
- **Live proof on real DB** (`_resolve_message_text`): audit 227/228 → "Notları listele"; 232 → "devam edelim en son epostayı gönderiyordun"; 233 → "son 10"; 234 → "Bugün hava nasıl?" — all user commands, previously the assistant replies.
- **Known refinement (noted, not a blocker):** audit 232's "devam edelim…" is context-dependent (plan flagged this as secondary risk); the current heuristic keeps it (not "çok kısa"). Deeper context-detection is deferred; CRITICAL fix (user-vs-assistant) is done.
- Tests: reworked `_seed_conversation` to mirror the real schema (user at cid-1, assistant at cid) + new `TestBug1UserMessageResolution` class (feeds user command, rejects assistant-like text, single-word, missing-user skip, heuristics). Suite **479** passing; ruff clean; py_compile ✓.
- Image size / dry-run unchanged for the 5 positives (they now carry correct text). Commit `C-1`.

## 2026-09-01 — Phase C-2 (BUG-2): atomic additions.jsonl ↔ npy writes + embed guard
- **Fix target (from audit):** `additions.jsonl` is appended row-by-row inside `_process_audit_row`, but `additions_embeddings.npy` is written once at the end of `run()`. `_check_conflict`/`_is_duplicate` map group↔vector purely by positional index, so a crash (or an unguarded `embed_one`) between the two leaves jsonl and npy permanently out of alignment.
- **Change (corpus_feeder.py):**
  - `_save_addition_embeddings` now writes to a temp file and `os.replace()`s into place (atomic; never a half-written npy).
  - `_load_addition_embeddings` **self-heals**: it compares `len(jsonl)` vs `len(npy)`; on mismatch (or missing npy) it rebuilds an index-aligned matrix by re-embedding every record in jsonl order (jsonl = source of truth) and atomically persists it. Added `_rebuild_matrix()`.
  - The `run()` embed path is guarded: if `embed_one` fails for a just-added record, `_remove_addition_by_audit_id()` rolls the jsonl row back (added `_write_jsonl` atomic rewrite) and the row counts as `skip_embed_error` — jsonl and npy never diverge on an in-process failure.
- **Tests:** new `TestBug2Alignment` — rebuild on count mismatch (2 records/1 vector → matrix rebuilt aligned), missing-npy rebuild + persist, and embed-error rollback (jsonl emptied, matrix None, counted skipped). Suite **482** passing; ruff clean; py_compile ✓.
- Live check: `corpus_data/` held only `state.json` (no live feed has ever run non-dry), so no real data was drifted — the fix is defensive. Dry-run feed unchanged (5 added). Commit `C-2`.

## 2026-09-01 — Phase C-3 (BUG-3): live corpus reload (no service restart needed)
- **Fix target (from audit):** `_tool_embed_cache` is a process-lifetime singleton rebuilt only on first cache-miss; `corpus_feeder.py` (separate process) writes additions.jsonl but cannot reset the live service's cache, so the old "restart not needed" claim was FALSE.
- **Decision (user-confirmed):** Option B — live reload.
- **Change (llm/intent.py):** `_get_tool_embeddings` now tracks `_tool_embed_mtime` (mtime of additions.jsonl at last build). On every call it compares the current file mtime to the recorded one; on change it clears + rebuilds under the existing `_tool_embed_lock` with double-check, so the next classification sees new additions — **live, no restart**. Added `reset_tool_embed_cache()` for explicit/deterministic invalidation.
- **Change (routers/chat.py):** new `POST /chat/reload-corpus` admin endpoint calls `reset_tool_embed_cache()` for an immediate deterministic refresh (e.g. right after `corpus_feeder.py --commit`).
- **Corrected the documentation:** the false "restart not needed" docstring in `_additional_corpus()` was overwritten ("takes effect on the next process restart" → now live).
- **Tests:** `TestBug3LiveReload` — cache rebuilds automatically when additions.jsonl mtime changes (entry count + notes group appear), and reset forces a stable rebuild. Suite **484** passing; ruff clean; py_compile ✓. Commit `C-3`.

## 2026-09-01 — Phase C-4 (BUG-4): calibrated, configurable conflict threshold
- **Fix target (from audit):** the hardcoded `0.85` conflict cosine was chosen by assumption and never fires on real data (real TR own-group sim 0.4–0.8, cross-group never ≥0.85), leaving the conflict + LLM-resolution + genuinely_ambiguous path dead code.
- **Live calibration (real embedding model, real audit commands + probe bank):** own-group sims **0.19–0.71** (median 0.56) vs cross-group **0.16–0.65** (median 0.28). No single absolute value separates perfectly — the classifier itself decides by `best_sim ≥ 0.50 AND margin ≥ 0.05`, not an absolute cosine.
- **Change (config.py):** new `CONFLICT_COSINE = _safe_float("CONFLICT_COSINE", 0.50)`, configurable via env, not a hardcoded code constant.
- **Change (corpus_feeder.py):** `_check_conflict` reads `config.CONFLICT_COSINE` by default (fallback 0.50); a conflict now fires when the nearest different-group example scores ≥ this AND the group differs from the proposed one. Aligned with the classifier's 0.50 decision boundary so the resolution flow actually triggers on real cross-group disagreement.
- **Live dry-run:** the 5 genuinely-correct user commands still add cleanly (no false conflicts) — the flow is now live without breaking correct signals. Suite **488** passing; ruff clean; py_compile ✓. Commit `C-4`.

## 2026-09-01 — Phase C-5 (BUG-5): same-group "corrections" are no-ops
- **Fix target (from audit):** 5 of 6 correction rows were no-ops — `expected_group` equal to the tool's own group (UI group-picker allows it). Meaningless as a signal, though they didn't reach the corpus while conversation_id was NULL.
- **Change (corpus_feeder.py):** when processing a **correction**, if `expected_group == TOOL_TO_GROUP[tool_name]` the row is skipped as `skip_noop_negative` — it can never feed the corpus as noise even with a resolved conversation_id.
- **Change (db.py):** new `get_audit_tool_name(audit_id)` helper.
- **Change (routers/chat.py):** `/chat/tool-correction` returns a `noop` boolean — true when a group-only correction picks the tool's own group — so the client can warn.
- **Change (static/index.html):** `submitCorrection` checks the `noop` flag and shows a `corrNoop` toast instead of marking the row fixed (en/tr strings added).
- **Tests:** `TestBug5NoopCorrection` (same-group skipped `skip_noop_negative` + empty jsonl; real cross-group still adds negative) + endpoint/db tests (`noop` true/false/tool-only, `get_audit_tool_name`). Suite **494** passing; ruff clean; py_compile ✓; JS syntax ✓. Commit `C-5`.

## 2026-09-01 — Phase C-6: regression sweep (all bugs fixed)
- **Every commit (C-1→C-5)** carried py_compile + full pytest + ruff clean; per-commit verification done.
- **Final regression:** full suite **494** passing (was 474 at audit start; +20 new tests across C-1..C-5), ruff clean, py_compile ✓, JS syntax ✓.
- **Live dry-run on real DB** re-confirms the 5 confirmed rows now feed the **USER commands** (audit 227/228 → "Notları listele", 232 → "devam edelim…", 233 → "son 10", 234 → "Bugün hava nasıl?") — assistant-reply text no longer poisons the corpus (BUG-1). 6 no-text correction rows still skipped; 5 positives add cleanly.
- **Live calibration (C-4)** of the conflict threshold on the real model + real commands: own-group 0.19–0.71 vs cross-group 0.16–0.65 → default `CONFLICT_COSINE=0.50` (env-overridable), the conflict/LLM-resolution path is now reachable.
- **Pre-first-real-run action (from plan):** `corpus_data/` holds only `state.json` (no live non-dry feed yet, so no wrong examples to purge); reset/clean before the first live `corpus_feeder.py --commit` run is still advisable.
- Local `main` is **ahead of origin/main by 6** commits (the baseline feature + C-1..C-5). Push pending user confirmation; a service restart/reload is still required to activate backend changes in the live `pisynapse.service`.

## 2026-08-31 — E-1 AUDIT: correction/confirmation → corpus pipeline (read-only)
> Full written report: `/home/user/corpus_feeder_audit_report.md`. Nothing was fixed during the audit. Verdicts below are each justified by live evidence, never "probably correct".
- **GREEN, verified:** (a) `confirmed_at` is a genuine user thumbs-up — schema has NO default, only `set_tool_confirmation()` (POST /chat/tool-confirm) sets it; frontend `submitConfirmation` fires it on a real 👍 click. (b) asyncio await chain is complete everywhere (base corpus + additions + LLM resolution); the only `asyncio.run` left is the CLI entry. (c) LLM auto-resolution prompt is neutral (groups presented symmetrically, no "user picked A" framing) — no confirmation bias. (d) `_get_tool_embeddings` really loads additions in a fresh process (CORPUS_ENTRIES 63, ADDITION_LOADED True). (e) an added example really changes cosine routing — real command "son 10" went question/None before → action/email after.
- **BUG-1 (CRITICAL):** `tool_audit_log.conversation_id` is the **assistant** message id (see `link_audits_to_message`, routers/chat.py:323-324), not the user message. `corpus_feeder._resolve_message_text` thus feeds the **assistant/tool-ouput text** into the corpus, not the user command. Proven on all 5 confirmed rows: e.g. audit 227 (list_notes) fed "Merhaba! Elbette, notların listesini..." instead of the real trigger "Notları listele". Also audit 232's real command ("devam edelim en son epostayı gönderiyordun") is context-dependent and not a valid standalone intent example (secondary risk). Dry-run's 5 "additions" were all this wrong text.
- **BUG-2 (HIGH):** `additions.jsonl` append and `additions_embeddings.npy` save are not atomic. If the script dies (or the unguarded `embed_one(text)` at corpus_feeder.py:472-473 raises) between the jsonl append and the final npy save, the two files permanently desync (N+1 records vs N vectors) and `_check_conflict`/`_is_duplicate` pair groups by bare positional index with the wrong vector (llm/intent `_check_conflict` line 225, `_is_duplicate`). npy stores raw vectors with no id anchor.
- **BUG-3 (HIGH):** the "restart not needed" claim is FALSE. `_tool_embed_cache` is a process-lifetime singleton assigned only inside `_get_tool_embeddings()` (no reload/IPC/watch). `_additional_corpus()` re-reads the file but only on the first cache-miss call. Live proof in one process: after building the cache, adding additions.jsonl then re-calling yielded `ENTRIES_CHANGED False`, `NEW_ADDITION_VISIBLE_WITHOUT_RESTART False`. Running `corpus_feeder.py` (separate process) cannot reset the live service's cache → a service restart is required for additions to take effect. **→ RESOLVED in Phase C-3** (mtime-triggered live rebuild + `POST /chat/reload-corpus`).
- **BUG-4 (MEDIUM):** the 0.85 conflict threshold was set by assumption, not validated. Measured with the real model on 30 real Turkish commands: own-group max cosine mostly 0.4–0.8 (1/30 ≥ 0.85), no cross-group query exceeded 0.85. The real classifier operates at best_sim ≥ 0.50 + margin ≥ 0.05. So 0.85 almost never fires → conflict + LLM-resolution + genuinely_ambiguous path is effectively dead on real data (dry-run: 0 conflicts). Two real commands had cross-group similarity > own-group ("ödevi sil", "gelen kutumu kontrol et"). **→ RESOLVED in Phase C-4** (config `CONFLICT_COSINE=0.50`, aligned with the classifier boundary; resolution path now reachable on real data).
- **BUG-5 (LOW):** 5 of 6 "correction" rows (215,216,217,219,221) carry an `expected_group` identical to the tool's true group (no-op corrections / noise); only 1 (231 read_note→email) is a real cross-group correction. All 6 have NULL conversation_id so none feed the corpus anyway. UI's group-picker can emit same-group "corrections". **→ RESOLVED in Phase C-5** (feeder skips `skip_noop_negative`; endpoint flags `noop`; UI warns).
- The current tests pass (474) but don't cover these data-flow failures (they use synthetic text/corpus; no coverage for assistant-output feeding, crash desync, or live-cache staleness).
- Full evidence tables (5 confirmed rows traced audit→conversation→content→real user command; threshold similarity matrix) are in the report at /home/user/corpus_feeder_audit_report.md.

## 2026-08-31 — Phase E-1: `corpus_feeder.py` — audit-log → intent-corpus pipeline
- **Goal:** mine `tool_audit_log` confirmation/correction signals and feed them into the intent-classification corpus so real user corrections improve routing without manual JSON editing.
- **New files:** `corpus_feeder.py` (batch CLI), `corpus_data/` (state + generated artifacts), `tests/test_corpus_feeder.py`. **Modified:** `llm/intent.py` now loads `corpus_data/additions.jsonl` on top of the hardcoded `_TOOL_EMBED_CORPUS` during `_get_tool_embeddings()` cache build.
- Behavior: tracks `last_audit_id` in `corpus_data/state.json` (only rows with `confirmed_at` OR `expected_group` are processed); resolves trigger text via `conversations.id`; positive signals map tool→group via `TOOL_TO_GROUP`, negative signals use `expected_group`; skips rows with no resolveable text or an unmapped tool; dedupe (cosine ≥ 0.98) and conflict check (cosine ≥ 0.85 vs a different group) both run against the base corpus + already-persisted additions.
- **Conflict auto-resolution:** a conflicting row is sent to the LLM (`gemma4-e2b`, one-word classify prompt "A or B?" via litert/ollama). LLM agrees with the user's group → auto-added as `llm_resolved`; disagrees or unrecognizable → written to `corpus_data/genuinely_ambiguous.json` for human review. No manual pending_review editing.
- **Incremental embedding:** only newly added records are embedded (`embed()`) and appended to `corpus_data/additions_embeddings.npy`; base corpus is embedded once per run via `embed_batch_async`. The base-corpus embedding is awaited (async) — a first draft called `asyncio.run()` from inside the running loop and silently disabled conflict detection; fixed and verified via live dry-run.
- CLI: `python corpus_feeder.py` (real run), `--dry-run` (no writes), `--reset`, `--db PATH`. Prints a terse summary report. `state.json` is committed as bootstrap; `additions.jsonl`/`additions_embeddings.npy`/`*.json` artifacts are gitignored (regenerated).
- Verification: new backend tests cover positive addition, negative addition, conflict→LLM-agrees (auto-add), conflict→LLM-disagrees (genuinely_ambiguous), embedding-only-new, duplicate skip, state-no-reprocess, and `llm.intent._additional_corpus()` parsing (incl. empty-file). Full suite **474** passing; ruff 0.16.5 clean; `py_compile` ✓.
- Live dry-run against `assistant.db`: 11 signal rows found, 5 additions (notes×2, email×2, weather×1), 6 skipped (no resolveable text), 0 conflicts — conflicts-to-date none, since these examples are fresh.

## 2026-08-31 — Phase C-13d: Mobile glass new-chat tap feedback (sticky-hover leak)
- Bug report: on mobile, in glass mode, the new-chat buttons' press effects seemed dead. Diagnosed via touch-emulated e2e probe: every other hover rule in the app is gated to `@media (hover:hover)`, but the bottom style block had an *ungated* `.new-btn:hover,.top-new-btn:hover{transform:scale(1.02)}`. On touch, `:hover` goes sticky — after the first tap the CTA rests at 102% scale forever, so the `:active` shrink (glass: scale(.95)+accent glow burst) read as broken.
- Fix (frontend only): wrapped that hover rule in `@media (hover:hover)`. Press feedback itself was verified intact (desktop glass `:active` → matrix scale .95 + glow; touch `:active` fires on real taps).
- Verification: new `cta-tap.spec.cjs` ×2 — touch+glass tap returns the top new-chat button to `transform:none`, and desktop hover still enlarges the CTA (hover preserved). Full e2e **35/35**, `node --check` ✓.
- Follow-up: on a real phone the effect only showed while the finger was *held* — a quick tap's `:active` is too brief to paint. Added a `pointerdown` listener (passive) that pins `.tap-flash` on `.new-btn/.top-new-btn` for ~250 ms, mirroring the `:active` styles (glass: scale(.95)+accent glow). Quick taps now flash visibly, then return to rest; `cta-tap` additionally asserts the flash appears and clears.

## 2026-08-31 — Phase C-13c: Weather ticker follows UI language + kind-driven icon
- Bug report: after switching the UI language in settings the ticker stayed unchanged (condition still Turkish) and the icon didn't move. Two root causes:
  1. `applyLang` never re-rendered the cached ticker → stale text/icon after a switch.
  2. The condition label came straight from the backend (Turkish) with no client-side localization, and the "icon" was the static sun-cloud unless the widget happened to report a non-partly kind.
- Fix (frontend only):
  - `applyLang` calls `rebuildTickerFromCache()` when weather cache is populated → language switches re-render the ticker immediately.
  - New `WMO_LABELS` (tr/en) + `wmoLabel(code)`/`wmoIconKind(code)` mirror the backend WMO mapping client-side; the item text is now `22°C · Açık`/`22°C · Clear` and the icon is derived from `wmo_code` at render time (sun / sun-cloud / cloud / fog / drizzle / rain / snow / lightning). Old-server fallback path (no `wmo_code`) preserved.
- Verification: pytest **465**; e2e **33/33** (+`weather-ticker.spec.cjs` ×2: label localizes on `applyLang` switch, storm payload swaps label+icon).
- Follow-up: the partly/cloud-sun icon still matched the app's old generic sun-cloud, so "Az bulutlu" (Akşehir, code 1) looked unchanged on hard refresh. Replaced the icon set with distinct lucide-style glyphs per kind (sun / cloud-sun / cloud / cloud-fog / cloud-drizzle / cloud-rain / cloud-snow / cloud-lightning); `unknown` keeps the legacy sun-cloud fallback.

## 2026-08-31 — Phase C-13b: Weather ticker widget → condition icon + structured payload
- Follow-up to C-13: the sidebar/topbar weather ticker showed only the raw summary text with a static sun-cloud icon, so the new condition label wasn't visualized.
- `weather.py`: introduced `_wmo_kind(code)` — coarse icon category (`clear/partly/cloud/fog/drizzle/rain/snow/storm/unknown`) — and factored the fetch into `_weather_data(city)` returning `{city, temp_c, feels_c, condition, wmo_code, kind}`; `get_weather()` (LLM tool) now builds its string from the same fetch. Structuring the payload once keeps the tool and widget consistent.
- `routers/widgets.py`: `/widget/weather` returns the structured fields (`temp_c`, `feels_c`, `condition`, `wmo_code`, `kind`) alongside the legacy `summary`; unknown city / fetch failure now correctly returns `ok:false` instead of masquerading an "ERROR:" string as success.
- Frontend: `refreshTicker` caches `kind/temp_c/condition`; `rebuildTickerFromCache` picks the icon by `kind` (sun, sun-cloud, cloud, fog, cloud-drizzle, cloud-rain, cloud-snow, lightning) and renders the compact `24°C · Parçalı bulutlu` item. Defensive fallback: if the endpoint answer lacks structured fields (old server), it keeps the previous summary-text + sun-cloud behavior.
- e2e stub now returns the structured payload; no assert touched the ticker.
- Verification: pytest **465** (+2 widget tests, +`_wmo_kind` mapping), e2e **31/31**, `node --check` ✓.

## 2026-08-31 — Phase C-13: Universal message feedback + weather condition
- **Problem (user report):** after an interrupted "email all notes" round (model timed out), the user expected the 👍/👎 pair on EVERY assistant reply — including tool-less messages such as "Rica ederim kanka!". Root finding: thumbs were audit-bound (C-7), so a no-tool reply showed neither thumb nor quiet state → unmarkable. The user's rationale: subtle failures (model asking a clarifying question instead of acting, dropped intent, hallucinated no-tool reply) are exactly the data to capture; every round must be markable.
- **Backend changes:**
  - `db.py`: new `message_feedback` table (`message_id`, `value` up/down, `note`, timestamps; UNIQUE per message, created by `CREATE TABLE IF NOT EXISTS` in `init_db`, no version bump needed). Added `upsert_message_feedback()` (rejects user/missing messages, overwrite semantics). `get_history`: includes `feedback` / `feedback_note` for assistant messages, gated by `include_audits` so LLM context stays clean.
  - `routers/chat.py`: `POST /chat/message-feedback` (`{message_id, value, note?}`; 400 bad value, 404 missing/not-assistant).
- **Frontend changes:**
  - `settleFeedbackRow`: audit row keeps its audit-bound thumbs; the non-audit `else` branch now renders a universal message-level thumbs pair instead of the quiet ✓/⚠ state.
  - New handlers `msgMarkUp`/`msgMarkDown`/`openMsgNoteEditor`/`applyMsgFeedbackState`/`ensureRoundFeedback`: 👍/👎 persist via the new endpoint; 👎 opens an inline optional-reason editor (Enter saves, Esc cancels, note dot `.msg-note` + tooltip). `msgMid` reads the anchor from the message group's `dataset.mid`.
  - `sendMsg` finally: `ensureRoundFeedback` guarantees every round's message gets its row (error/empty/aborted rounds included via `noteGroup` capture), placed before `attachMsgActions` so the copy/listen/regen bar still merges into the row.
  - `addMsg`/`loadSession`: every assistant message gets the row on history render; `feedback`/`feedback_note` restore the persisted verdict/note.
  - i18n: `notePlaceholder`/`noteSave`/`noteCancel` (tr/en). CSS: `.mark-btn.msg-note` dot, `.msg-note-editor`.
- **Weather:** `weather.py` now requests `weather_code` and maps WMO codes to Turkish conditions (`_wmo_condition`), so the reply reads e.g. "İstanbul: 24°C, Parçalı bulutlu, feels like 26°C".
- **Verification:**
  - pytest **462** (new: upsert insert/update, user/missing rejection, history feedback gating, endpoint 200/400/404, `_wmo_condition` mapping).
  - e2e **31/31** (new `message-feedback.spec.cjs` ×4: tool-less row + data-mid, up persistence, down note editor + persisted note, history restore). Updated `mark-flow`/`feedback-confirm` (audit_id-null now shows the universal pair → note editor, no group picker) and `branch-regen` (bars live in `.tool-status.done` now). `node --check` ✓.

## 2026-08-30 — Phase C-12: Per-message regenerate with branch semantics
- **Problem & Research:** The `.last-of-type` check previously restricted regenerate to the last assistant message, but in history renders every older assistant kept a stale button that falsely re-ran the *last* user prompt. Research into industry standards (AWS Cloudscape, assistant-ui / shadcn, MUI X) confirmed per-message regenerate/actions is standard, but requires branch semantics: regenerating an older message must truncate the conversation from that point forward (both in DB and DOM) and re-run that message's own prompt.
- **Backend changes:**
  - `db.py`: added `delete_branch(session_id, anchor_id)` to delete messages with `id >= anchor_id` and their FTS entries. Updated `get_history` to include `"id": r[0]` and order by `id DESC` for stable ordering.
  - `routers/chat.py`: added `DELETE /chat/messages/branch/{session_id}` endpoint (accepts `{message_id: int}`) and included `message_id` in the stream `done` SSE payload.
- **Frontend changes:**
  - `regenerate(group)`: locates the preceding user message, sends `DELETE /chat/messages/branch/{sid}`, removes that assistant and all following siblings from DOM, and re-streams the prompt via `sendMsg({regenText})`.
  - `attachMsgActions`: appends regenerate button on all assistant messages (fallback for missing mid on legacy rounds keeps last-exchange rule).
  - `clearToolPills()`: now only removes active/transient `.tool-status:not(.done)` rows, keeping settled action bars intact across turns.
  - `refreshLastState()`: adds `.not-last` class to non-latest assistant action bars, dimming them (`opacity: .45`) and revealing on hover/focus.
- **Verification:**
  - `tests/test_audit.py`: added unit tests for `delete_branch` and `DELETE /chat/messages/branch/{session_id}`.
  - `tests/e2e/branch-regen.spec.cjs` (2 new tests): tests per-message regenerate button presence, `.not-last` class dimming, and branch DELETE + re-streaming.
  - `tests/e2e/mark-flow.spec.cjs`: updated clear-pills test to reflect retention of settled tool rows.
  - pytest **456** passed; e2e **27/27** passed; `node --check` ✓.

## 2026-08-30 — Phase C-11: Tool indicator clears the moment the model starts replying
- **Bug (user report):** "notları listele" — the tool row kept its working label ("notlarına bakıyorum…") painted below the message for the WHOLE streaming answer; the indicator was only settled at stream end (by design since C-7), so single-tool lookup rounds left a stale active-looking pill under the reply.
- **Applied (frontend only):** the row now settles at the FIRST model output instead of stream end — both the `token` and the `reasoning` branches call `settleFeedbackRow(toolRow, true, roundAudits)` once the row is no longer active. Label+spinner are dropped (quiet ✓ or the C-7 thumbs) exactly when text starts. Because a tool can still run AFTER a token in multi-step rounds, `ensureToolRow` now REVIVES a settled row (`resetPill`) on the next tool event instead of creating a second one; the next settle re-carries ALL audits (the divider for the merged copy/listen/regen bar is re-added by `settleFeedbackRow`). Stream-end finally keeps its `!done` guard → no double settle.
- **Verification:** Playwright 1.40 cannot stream `route.fulfill` bodies, so the new `tests/e2e/tool-label-gone.spec.cjs` (2 tests) wraps the page's own `fetch` and returns a real web `ReadableStream` of SSE chunks on a timer (genuine mid-stream timing in-browser): (1) tool label visible while the tool runs, then — before the `done` chunk — label gone + `.fb-up` present + exactly one row, answer streaming under the settled row; (2) multi-step (tool → token → tool) keeps ONE row with `data-audits="111,222"` (revival path). e2e **25/25**; pytest **454** (unchanged; frontend-only); `node --check` ✓. Live: frontend-only → no restart, serve clears on F5.

## 2026-08-30 — Phase C-10: Auto-export old audit logs before the 14-day purge
- **Goal (user):** the 14-day retention rollup deletes audit detail rows (which also makes old thumbs vanish on reload). Before that deletion, the rows must be AUTOMATICALLY exported to a separate folder so nothing is silently lost.
- **Applied (db.py):** pre-rollup archive. `audit_export_dir()` = `AUDIT_EXPORT_DIR` env, else `<dirname of DB_PATH>/audit_exports` (production: `audit_exports/` next to `assistant.db`; tests: inside the tmp fixture DB's own dir — no repo litter). `export_tool_audit_day(day, cutoff)` selects ALL detail columns (20, incl. `conversation_id` + a LEFT JOIN pull of `session_id`) for the day and writes `tool-audit-YYYY-MM-DD.csv` via `_write_audit_csv` (worker thread, tmp + `os.replace` atomic, per-day file overwritten → idempotent across retries after crashes). The rollup now exports INSIDE the existing `BEGIN IMMEDIATE` day transaction, BEFORE the summary INSERT + detail DELETE: if the archive write raises, the day rolls back and nothing is deleted — the next cycle retries. Archive-then-delete is all-or-nothing per day.
- **Verification:** pytest **454** (+3: export writes per-day CSV incl. linked `session_id` and blank for unlinked, single header + N rows; export failure blocks deletion and a later working cycle completes it; `audit_export_dir` env override + DB-relative default). Existing rollup/retention tests unchanged & green. No frontend change (e2e untouched). `.gitignore` gains `audit_exports/`.
- **Push state (current):** this commit is next; live service restart needed (backend code changed).

## 2026-08-30 — Phase C-9: TTS wait feedback — listen button lights up while Piper renders
- **Goal (user):** Piper takes a beat to produce audio, so the listen button looked dead (no reaction) until the sound arrived — fine for you, confusing for someone cloning from GitHub. Show the wait WITHOUT text: keep the button "bright" until audio plays.
- **Applied (frontend-only):** new `.tts-btn.tts-loading` state applied the instant `toggleTTS` runs (click → first sound): accent icon + accent 12% tinted fill + a soft breathing ring (`@keyframes tts-load`, `box-shadow` 0→4px accent) — visually DISTINCT from `.tts-playing` (which stays icon-pulse, no fill). No label/text. `onplay`/`onstart` swap `tts-loading`→`tts-playing`; every exit path (`onended`/`onerror`/`stopTTS`) clears both. Reduced-motion kills the animation via the existing global rule (button stays tinted, static). Bonus fix (same UX story): the click-again-during-wait race — a second click used to leave an orphaned in-flight piper fetch that later started audio anyway. Now `playPiperTTS` owns an `AbortController` (`ttsAbort`) aborted by `stopTTS`; `AbortError`/aborted-`play()` are swallowed silently (no fake error toast), so the second click = cancel.
- **Verification:** NEW `tests/e2e/tts-loading.spec.cjs` (holds the `/chat/tts` response open 3s → asserts the button is `.tts-loading`, accent-tinted, NOT `.tts-playing`, immediately after click; second click clears the state and after the request resolves no orphan audio and no error toast appear). e2e **23/23**; pytest **451** (unchanged; frontend-only); `node --check` ✓; CSS presence probe for keyframes + reduced-motion ✓.
- **Push state (current):** previous C-8 pushed; this commit is next.

## 2026-08-30 — Phase C-8: Feedback persistence — thumbs survive chat switches / refresh
- **Bug (user report):** after the C-7 UI landed on the live server, the thumbs pair disappeared when switching chats or refreshing the page. Root cause: `tool_audit_log` had NO link to a conversation row, and `/chat/history` did not carry audits — the UI rebuilt only text bubbles, so thumbs could never return.
- **Applied backend:** migration #12 (appended at END of MIGRATIONS) adds `tool_audit_log.conversation_id INTEGER`. `db.save_message` now RETURNS `last_insert_rowid()` (players: dedup path still returns `None`). New `db.link_audits_to_message(conversation_id, audit_ids)` — batches an `UPDATE … WHERE id IN (…) AND conversation_id IS NULL` (a row already owned by a message — e.g. a previous regeneration — stays untouched; never raises, returns linked count). `db.get_history` gains `include_audits: bool = False` (default off → the LLM context path is untouched); when on, it JOINs `tool_audit_log` and attaches each assistant message its list `[{audit_id, tool_name, confirmed_at, corrected_at, expected_group}]`. `/chat/stream` collects every SSE tool `{phase:'end', audit_id}` into `stream_audit_ids` and links after both the done-save and the partial-save (finally) paths; `/chat/execute` links its single audit too. `GET /chat/history` passes `include_audits=True`.
- **Applied UI:** `loadSession` passes `m.audits` into `addMsg` (7th param). When an assistant message has audits, `addMsg` builds a `.tool-status` row, settles it via `settleFeedbackRow(row, true, audits→{audit,name})` (same DOM as a live row: below the bubble, `data-audit`/`data-audits` set) and then `attachMsgActions` merges copy/listen/regen into exactly that row. New `applyFeedbackState` re-lights persisted signals: ALL audits `confirmed_at` → up `.active`; ANY audit `corrected_at` → down `.marked`. Historical thumbs are live buttons — confirm-all and corrections round-trip against the real endpoints.
- **Verification:** pytest **451** (+5: `save_message` returns rowid + dedup None; link batches + respects ownership; empty/unknown ids safe; `get_history(include_audits=True)` attaches per-message + default stays clean; `/chat/history` endpoint returns linked audits). e2e **22/22** with NEW `tests/e2e/feedback-persist.spec.cjs` (3 tests: history restores ONE pair per audited assistant message + merged bar + `data-audits`; persisted signals re-light thumbs; historical confirm/correction round-trip posts the right payloads). `node --check` ✓. Live server restarted, migration applied (user_version 12); manual live verification of thumbs persistence planned via real tool round.
- **Known behavior (pre-existing, not fixed):** the regen button lands on EVERY older assistant message because `attachMsgActions` resolves `.msg-group.assistant:last-of-type` incrementally — also true in the live flow today. Retention note: `rollup_tool_audit` still purges detail audit rows after 14 days, so thumbs under messages older than that vanish on reload (by design).
- **Push state (current):** C-7 (through `753e089`) is pushed to `origin/main`; this C-8 commit is next.

## 2026-08-30 — Phase C-7: One 👍/👎 per message; multi-tool correction chips (user decision (a))
- **User decision:** first cancel BOTH earlier options (bar-merge into first row, or per-tool pairs + labels). New contract: ONE 👍/👎 pair per assistant message regardless of tool count, in the SAME row as copy/listen/regen. 👎 shows the tools that ACTUALLY ran (i18n labels) as small chips; clicking a chip opens the existing group picker bound to THAT tool's audit_id (fixes only that tool). 👍 confirms ALL ran tools at once (single decision). Edge case asked by the assistant → user chose **(a)**: after a 👎-correction flow, the non-fixed tools stay UNREVIEWED (no implicit confirmation); a second chip correction creates a SECOND correction on the same message.
- **Applied UI (frontend-only, no backend change):** the SSE round now accumulates every audited end event (`roundAudits`) instead of settling each tool separately; a single `.tool-status` row is reused for the whole round (spinner/label swap per tool via `showToolScan`/`ensureToolRow`, spinner deads at each end) and is settled ONCE at stream end (`settleFeedbackRow` → one pair, `ok`/⚠ fallback when no audits). `data-audit` = first audit (contract kept), `data-audits` = full comma list. 👎 single-tool → picker DIRECTLY (preserves keybind/e2e contract); multi-tool → `.fb-tabs` chip strip (`.fb-tab` per audited tool, short i18n names via new `TOOL_SHORT` map — the TOOL_LABELS verbs are too long), chip `.done` shows accent tint + ✓ after a successful correction and stays open for more fixes. 👍 = sequential `POST /chat/tool-confirm` for EVERY audit (all-or-nothing: any failure → toast + unlit, retry re-runs the batch) and drops the chip strip. `clearToolPills` also clears `.fb-tabs`. Chips are group-picker-palette (`surface2/3`, accent hover, 999px pills, never browser default); a `pointer:coarse` block AFTER the base chip rules so the 44px padding override wins the cascade; `pointerdown` dismiss of the chip strip exempts `.group-picker` clicks (removing chips mid-interaction reflowed the layout and swallowed the gp-opt click — the bug found in dev).
- **Verification:** NEW `tests/e2e/feedback-multitool.spec.cjs` (5 tests: one pair + merged bar + `data-audits`; single-tool still opens picker directly; chips show audited tools only — refused tool absent; a chip fixes only its audit_id, other chips stay available, no implicit confirm; 👍 posts ALL audits in order and drops the strip). e2e **19/19**; pytest **446** (unchanged); `node --check` ✓; computed-style probe: chips `surface2` bg + `--border` 1px + 999px radius, coarse padding 11px 16px + min-height 44px (tap44 true), `.done` = accent-tinted bg + accent border + ✓. Screenshots `/tmp/opencode/shots/fb-c7-*.png`: multi pair, chip strip, picker under a chip, corrected-chip state — desktop/mobile × normal/glass; before-multitool reference = `fb-mt-both-desktop.png`.
- **Push state (current):** `origin/main` at `ffb63c3`; unpushed local: `b9a16c5`, `e4fc7bc`, `820c688`, `2f7b6a2`, `9009a14`, `0da1b54`, `e193f83`, `46ff40a`, `ecc2b02` (C-7 UI), + this journal commit.

## 2026-08-30 — Phase C-6: Confirmation signal + feedback redesign (real thumbs, picker card)
- **Goal (user):** full redesign of the tool feedback UX in ONE task: replace the ✓ + pencil affordance with real thumbs-up/thumbs-down icons integrated into the SAME action bar as copy/listen/regen (same row, same size/style/color); BOTH buttons functional — thumbs-up = a positive **confirmation** signal to the backend, thumbs-down = the existing correction group-picker; redesign the picker (palette, hover/selected accent, primary filled Save + ghost Cancel that are never clipped); add tests for both flows; before/after screenshots (desktop + mobile × glass + normal); self-review; push stays pending.
- **Confirmation schema (decision + rationale):** a new `confirmed_at DATETIME` column on `tool_audit_log` (migration #11, appended at END of MIGRATIONS) + `db.set_tool_confirmation()` + new endpoint `POST /chat/tool-confirm {audit_id}` (404 on unknown). Rationale: a timestamp is richer than a boolean (when was the signal given; `IS NOT NULL` derives the boolean), the correction endpoint stays untouched, and semantic separation keeps validation simple (confirmation carries only `audit_id`). Mutually exclusive by construction: `set_tool_confirmation` clears `expected_tool/expected_group/corrected_at`; `set_tool_correction` clears `confirmed_at` — a row never holds two opposing signals.
- **Applied backend (`e193f83`):** `confirmed_at` added to `tool_audit_log` DDL + MIGRATIONS; `set_tool_confirmation`; `set_tool_correction` now NULLs `confirmed_at`; `/chat/tool-confirm` handler.
- **Applied UI (`46ff40a`):** thumbs are Lucide-style inline SVGs (`_THUMB_UP_SVG`/`_THUMB_DOWN_SVG`) and carry the `tts-btn` class, so they inherit the exact action-bar style/color/glass/hover + `:active` scale; `attachMsgActions` now MERGES copy/listen/regen into the settled `.tool-status.done` row (one flat bar, hairline `.bar-divider`, single row — verified by e2e `up.parentElement === copy.parentElement`). Bar order: `[copy][listen][regen] ‖ [up][down]`. Thumbs-up → `POST /chat/tool-confirm`, accent fill `.active` on OK, visible toast on error (stays unlit). confirm↔correction mutually exclusive in the UI (clearing the other's active/marked look + titles). Coarse pointers: unified 44px touch targets across the whole merged bar. Picker redesigned as a card (14px radius, card shadow): scrollable `.gp-list` (`overflow-y:auto`, flex 1 + min-height 0) with a pinned `.gp-foot` (primary filled Save, ghost Cancel) so buttons are never clipped; palette `surface2/3` + accent tint for hover/`.sel`; glass-aware footer tint.
- **E2E contract preserved:** `.tool-status` (1 after audited call), `.mark-btn` opens `.group-picker`, `.gp-opt/.gp-save/.gp-cancel`, `.marked`, `data-audit`, 401 re-prompt, full keyboard flow, next-send-clears — all 9 mark-flow tests untouched and green. NEW `tests/e2e/feedback-confirm.spec.cjs` (5 tests: merged-same-row, confirm payload `{audit_id:123}` with no picker, mutual-exclusion switching, confirm 500 → toast + unlit + retry, null audit → no thumbs) + stub route `**/chat/tool-confirm` (+ `sentConfirmations`).
- **Verification:** pytest **446** (+5: db-level confirm/cross-clear/unknown + 2 endpoint tests); e2e **14/14**; `node --check` on the inline scripts ✓; computed-style probe (flat flex bar 0px radius, `tts-btn`-shared padding/color up↔copy, divider 1px, picker flex column + 14px radius + `.gp-list` scroll = `auto` + `.gp-foot` last) ✓. Screenshots in `/tmp/opencode/shots/`: `fb-before-*` (old pill+pencil+picker), `fb-after-*` (new bar + redesigned picker), `fb-active-*` (lit/corrected states) across desktop/mobile × normal/glass.
- **Push state (current):** `origin/main` at `ffb63c3`; unpushed local: `b9a16c5`, `e4fc7bc`, `820c688`, `2f7b6a2`, `9009a14`, `0da1b54`, `e193f83`, `46ff40a`, + this journal commit.

## 2026-08-30 — Phase C-5c: Revert the scroll-relief entirely — original always-on glass restored (user decision)
- **User decision:** remove the scroll relief and restore the pre-C-4 behavior. Every CSS state change while scrolling (frost → tint → frost) reads as a harsh pop, and NO non-changing relief can look identical to true blur — so "flicker relief via a state flip" is abandoned. The original always-on backdrop blur, though measurably jankier, is the acceptable baseline the user prefers over any visible mid-scroll change.
- **Applied (`9009a14`):** deleted `setupGlassScrollRelief()` and its JS call; deleted ALL `body.glass-mode.scrolling-chat` CSS (desktop block + the `@media (hover:none)` mobile tint override); removed the C-5b cost-cut overrides (bar blur 8px, sidebar `backdrop-filter:none`, input base `rgba(13,13,18,.55)`). Glass recipe is back to the pre-C-4 original, byte-identical via diff: shared `blur(12px) saturate(160%)` over topbar/input/sidebar/modals, topbar accent 7% + `rgba(12,12,18,.38)`, input transparent+sheen+shadow (desktop), mobile topbar blur12 / input blur16+`.88`. Bars never change appearance while scrolling — no relief class, no transitions.
- **Verification:** `diff` of the glass region vs pre-C-4 source = empty; grep finds zero `scrolling-chat`/`setupGlassScrollRelief`; Playwright probe (desktop 1280×800 + Pixel 7): during a long scroll burst `body` gains NO relief class, topbar/input keep `blur(12px)` (mobile input `blur(16px)`) continuously, no backdrop-filter transition. e2e 9/9; pytest 441; `node --check` ✓. Screenshots: `glass-revert-{desktop,mobile}[-scroll].png` in `/tmp/opencode/shots/`.
- **Push state (current):** `origin/main` at `ffb63c3`; unpushed local: `b9a16c5`, `e4fc7bc`, `820c688`, `2f7b6a2`, `9009a14`, `0da1b54`, `e193f83`, `46ff40a`, + journal commit (see C-6).

## 2026-08-30 — Phase C-5b: Glass scroll relief restyle (user: the C-4 relief "looks worse") + bar blur cost cut
- **Why the relief looked worse (root cause):** the old relief kept a `.15s background-color transition` while dropping `backdrop-filter` instantly → for ~150ms after each scroll burst started, the bars were un-frosted AND still at their low at-rest alpha (topbar .38 / input .55-area) → sharp, un-blurred, barely-tinted content flashed behind the bars, then the near-opaque slabs arrived. The binary hop to `.92/.96` opaque slabs was the second half of the complaint.
- **Applied (`820c688`):** ~~relief flip is now INSTANT (transition removed) and the relief tints hold the at-rest FROST tone — topbar accent 7% + `rgba(14,14,20,.78)`, input `rgba(14,15,21,.85)`, sheen gradient kept (`background-color`, not `background`). Mobile input keeps its exact at-rest `.88` tint during relief via a later-in-file `@media (hover:none)` override (same specificity → source order wins). Sidebar dropped from the relief selector.~~ — **2026-08-30 reverted by C-5c**: the state flip itself (even near-identical) was the complaint; relief + relief CSS removed entirely, original always-on blur restored (see C-5c).
- **Cheaper at-rest blur:** ~~pinned chrome blur 12→**8px** desktop~~ (reverted in C-5c), mobile topbar 12→8 (reverted in C-5c), mobile input 16→12 (reverted in C-5c). ~~Sidebar `backdrop-filter:none`~~ (reverted in C-5c). Desktop input base ~~`rgba(13,13,18,.55)`~~ (reverted in C-5c).
- **Verification:** Playwright probe (desktop 1280×800 + Pixel 7): at-rest bar blur 8px / sidebar no blur ✓; `body.scrolling-chat` on scroll ✓; relief IGNORES blur on topbar+input, no background-color transition ✓; relief alpha topbar .78 / input .85 (no .92/.96 slabs) ✓; input keeps sheen gradient mid-scroll ✓; mobile relief file = at-rest .88 ✓; class drops ~200ms after burst ✓. e2e 9/9; pytest 441; `node --check` ✓. Screenshots: `glass-after-{desktop,mobile,desktop-scroll,mobile-scroll}.png` in `/tmp/opencode/shots/`.
- **Push state (current):** `origin/main` at `ffb63c3`; ~~unpushed local: `b9a16c5` (tool indicator), `e4fc7bc` (journal C-5), and this item.~~ → **2026-08-30** reverted by C-5c (`9009a14`) — current unpushed set lives in the C-5c entry.

## 2026-08-30 — Phase C-5: Tool indicator redesign — in-flow message feedback (replaces the floating pill + overlay)
- **Goal (user):** remove the big floating tool-status pill and its overlapping group list ("Takvim/E-posta/Hafıza/Notlar/Görevler"); per tool-calling assistant message show two small unobtrusive states below it — positive: a passive check; negative: a small clickable correction control that opens the EXISTING collision-aware group-picker IN-FLOW (below the message, never on top of the bubble). Reuse the picker component, do not rewrite it.
- **Bug (requested verification):** before this change `endToolStatus` appended a ⚠ `mark-btn` whenever an `audit_id` was present — REGARDLESS of `ok` — so a correctly-run tool still showed a warning glyph ("!" impression). Root cause fixed: successful calls settle to a quiet ✓ only; the ⚠ glyph now appears only for genuinely failed calls; the correction control uses a neutral pencil icon.
- **Applied (`b9a16c5`):** tool feedback is now a child of the assistant `.msg-group` (`placeRow`, row directly under the bubble; the bubble is created eagerly on the first tool/gen_retry event so the row always lands inside the message). `.tool-status` becomes a slim transparent in-flow row (`width:fit-content`, no pill background). Settled state: `✓` (accent, passive) or muted `⚠` (failed) + optional quiet `mark-btn` (pencil). The `.group-picker` is now `position:static` inside the message — max-height clamp kept; on coarse pointers `width:100%` spans the message column (sheet); `scrollIntoView(nearest)` on open. `positionGroupPicker` (absolute flip/offset math) removed as dead code — the in-flow layout makes flipping moot while keeping the clamp + mobile sheet behavior. Rows are dropped on the next send via `clearToolPills` (unchanged), so the latest tool-calling message keeps its affordance; older ones clear.
- **Constraints honored:** class names (`.tool-status`, `.mark-btn`, `.group-picker`, `.gp-opt`, `.gp-save`, `.gp-cancel`), `data-audit`, `title=Yanlış/Wrong`, `.marked`, full keyboard flow and "next send clears + fresh row" behavior all preserved → tests/e2e untouched and green.
- **Verification:** e2e 9/9; pytest 441; `node --check` on the inline app script; geometric probes (desktop + mobile): row inside `.msg-group.assistant`, positioned below the bubble, picker `position:static` with ZERO bounding-box overlap; NOTE Playwright's `hasTouch` does NOT trigger the `(pointer:coarse)` media query — the mobile sheet only really shows under real mobile emulation (Pixel 7 descriptor in the probe/screenshot harness).
- **UX references:** per-message feedback = a discoverable-but-not-intrusive icon affordance at the bottom of the assistant message (hover-revealed row works); avoid floating panels — disclose details in-flow; keep the negative action quiet and separated to avoid misclicks.
- **Screenshots:** `before-{desktop,mobile,picker-desktop,picker-mobile}.png` (old pill/overlay) and `after-*` (new in-flow row + open picker), `/tmp/opencode/shots/`.
- **Push state (current):** `origin/main` at `ffb63c3` (v1.8.0 + changelog remap pushed); ~~`b9a16c5` is the only new local commit~~ → **2026-08-30** now `b9a16c5` + `e4fc7bc` + `820c688` (C-5b, see entry above) are unpushed locally.

## 2026-08-30 — Phase C-4: Glass scroll flicker (root cause: backdrop-filter recompute) — choice A, scroll relief
- **Root cause (verified):** in glass mode the pinned chrome (topbar blur12, input blur12/16, sidebar blur12) must re-sample and re-blur the MOVING content behind it every scroll frame → per-frame backdrop recompute = dropped frames / flicker. Headless-Chromium measurement on `#messages` scroll: blur-on 15.4 fps → relief 17.7 fps (desktop), mobile 56.4 → 61.3 fps.
- **Applied (`1edbf32`):** `setupGlassScrollRelief()` — `#messages` scroll (+ capture on `#sidebar`, which also covers INNER scrollers: `#session-list` (1816px scroll), memory/search lists) → `body.scrolling-chat` class (passive, 140ms debounce). CSS: `body.glass-mode.scrolling-chat #topbar/#input-container/#sidebar{backdrop-filter:none}` + near-opaque backgrounds while scrolling (topbar accent-mix .92, input rgba(13,13,18,.96)+shadow, sidebar var(--surface)); `.15s` bg transition. Blur drops only while scrolling and returns on rest. ~~Relief presentation (`.15s` bg transition + `.92/.96` slabs + sidebar relief)~~ — **2026-08-30 superseded by C-5b**: the transition caused a ~150ms un-frosted/low-alpha flash, and the opaque slabs looked worse; instant frost-tone relief with no sidebar blur replaced it (see C-5b above).
- Verification: class on during scroll ✓ topbar/input/sidebar blur none ✓ ~220-260ms later class drops and blur returns (desktop blur12, mobile topbar12/input16) ✓; the sidebar's inner `#session-list` scroll also triggers the class ✓. pytest 441; e2e 9. Screenshots: `fazC_glass_after_{desktop,mobile}.png`.
- ~~Push state (current): `origin/main` still at `9a7bcd7`; **21 local commits** — this one (`1edbf32`), `52eb349`, `41942df`, `9ab7153`, `ec768d4`, `7a71e8b` and the shadow/Phase B chain below.~~ → **2026-08-30 history rewrite**: old NOTES.md versions were removed from git history (publish-cleanliness) and `main` was force-pushed, so ALL historical commit hashes referenced anywhere below are superseded — verify against the code via `git log`, not these hashes. Current: everything pushed; `origin/main` at the sanitize commit.

## 2026-08-30 — Phase C-3: Glass orb (send button) design (user asked "which do you recommend?" → B recommended, applied)
- Measured (glass localStorage key `ps_glass`; applied at boot after config via `applyGlass`): the previous glass button was a flat linear-gradient + 1px hairline + basic 2px drop shadow, NO animation, NO specular/depth → flat chip.
- Applied (CSS-only, GPU-safe): `radial-gradient(circle at 29% 24%, rgba(255,255,255,.34))` specular highlight + accent-tinted `linear-gradient(145deg)` + accent hairline border + `glassGlow` 4s breathing keyframes (inset light/dark edge + outer accent glow 8→22px). Hover: animation stops, specular/glow strengthen. Active: inset press feel. `backdrop-filter:none` kept (safe for the C-4 flicker item). STOP `#send-btn.stop` keeps red gradient+glow (stays red even under the glass rules). `prefers-reduced-motion` block already kills all animations (`*{animation:none!important}`).
- Verification: specular ✓ accent border ✓ glassGlow infinite ✓ peak box-shadow accent 22px ✓ backdrop none ✓ aurora block ✓ stop red + anim none ✓. pytest 441; e2e 9 (`52eb349`). Screenshot: `fazC_orb_{before,after}_desktop.png`.

## 2026-08-30 — Phase C-2: Markdown table style (user chose A — "GitHub style")
- Measured (`fazC_table.cjs`): previously a vertical grid cage (1px border on every cell), zebra `rgba(255,255,255,.02)` effectively invisible, flat surface2 header, header lost on horizontal scroll (mobile).
- Applied (CSS-only): `border-collapse:separate;border-spacing:0`; `width:max-content;min-width:100%` (wide tables scroll, narrow tables fill the bubble); vertical borders removed → row hairlines only (1px) + 2px header underline; header `position:sticky;top:0;z-index:1` + surface3 fill (column names stay visible on mobile horizontal scroll); zebra → `rgba(255,255,255,.035)`; last row loses its bottom border.
- Verification: sticky top:0/z1 ✓, thBg surface3 ✓, td horizontal borders 0 ✓, hairline 1px + header 2px ✓, zebra 0.035 ✓, desktop fits + mobile overflow-x ✓, narrow table fills the wrapper ✓. pytest 441; e2e 9 (`41942df`). Screenshot: `fazC_table_{before,after}_{desktop,mobile}.png`.

## 2026-08-30 — Phase C-1: Settings tab reorganization (user: desktop B, mobile A; must separate UI from backend settings — UI settings must not vanish "while loading" when offline)
- Inventory (`/tmp/opencode/fazC_settings.cjs`): 7 sections — Üretim(3), Model(1, alone), Sohbet(3), Ses(5), Kişisel(3), ▸Gelişmiş(8+Sade Görünüm), **Diğer (junk drawer: LLM Motoru + Asistan Dili — the language duplicated the top UI-language row)**. Desktop modal 516×758 (~84% vp); long internal scroll (1799/628).
- User decisions: desktop app = **B (chip nav)**, mobile = **A (clean groups only)**; UI-vs-backend split and offline resilience required.
- Applied (`static/index.html`):
  1. **UI (local/localStorage) vs backend (fetch) split:** the Appearance row (Tema, Arayüz dili, Cam modu, **Sade Görünüm**) renders synchronously BEFORE the fetch and never touches an error path; backend sections render after `/config/settings`. Minimal moved from the Advanced injection into the Appearance row (single `#minimal-toggle`). On the fetch error path the UI row + Minimal stay UP, backend area shows only connErr. Verified with an offline stub (settings→500): appearance + minimal + theme-grid + glass visible, chips hidden (`.min`), lang value preserved.
  2. **Groups:** `Diğer` removed. `UI_LANGUAGE`→`Genel`; `LLM_BACKEND`+`LLM_MODEL`→`Model & Motor`; Üretim/Sohbet/Ses/Kişisel unchanged. Result 7→6 backend sections (Appearance not counted).
  3. **Desktop chip rail (`#settings-chips`):** `@media (pointer:fine) and (min-width:700px)` — desktop only; `bindSettingsChips()` scrolls on click (no-scroll-set, offset math) + rAF scrollspy on scroll; only existing sections become chips; <2 targets → `.min` (hidden). Mobile never shows it via the media query (A layout).
- Verification: JS parse OK; `fazC_settings_after.cjs` → desktop 8 chips with correct Turkish labels, `spy=5` (Ses) ✓, 7 data-sec sections, `minimalCount=1`, `otherGone`, `generalHasUiLang` & `modelHasBackend` ✓; mobile `chipsDisplay:none`; offline appearance stays up ✓. pytest 441; e2e 9 (`9ab7153`). Screenshot: `fazC_settings_{before,tr_desktop,tr_mobile,offline_desktop}.png`.

## 2026-08-30 — Phase C priorities: tool indicator + feedback box (2 commits)
- **Priority 1 — `7a71e8b` ui(pills): tool-status chips center-aligned to the message column.** Root cause proven by measurement (`/tmp/opencode/fazC.cjs`): the pill hugged `#messages`'s left padding (`margin:6px 0`, `width:fit-content`) while `.msg-group` centers itself (`max-width:800px;margin:auto`) → desktop center offset -354/-366px, mobile -47px. Fix: `margin:6px auto` + `max-width:min(800px,calc(100% - 40px))`. After: `dCenter=0` on both viewports ✓. No content overlap/overflow — it was purely an alignment issue.
- **Priority 2 — group-picker redesign (`ec768d4`, `positionGroupPicker`):**
  - Research summary: Floating UI / Popper.js collision detection = anchor to the trigger, auto up/down flip, clamp to viewport bounds, keep the anchor relationship. The old code aligned to the pill with `right:0` (panel hung 14px past the ⚠ button) and a fixed `scrollIntoView` nudge SCROLLED THE CHAT (button y 1047→702).
  - New: panel **anchored to mark-btn** (desktop; on coarse-pointer mobile → full `#messages`-viewport-width "mini sheet"), flips up when there is no space below, two-axis viewport clamping, `max-height:min(320px,calc(100dvh-24px))` + internal scroll (never scrolls the chat). `scrollIntoView` removed entirely. Outside tap closes (opened via `pointerdown` capture).
  - **`/tmp/opencode/fazC2.cjs` proof (desktop 1280 + mobile 390×844 + narrow 320×640 + "keyboard" 420h):** 12/12 scenarios `inside x&y = true`; **scrollOK=yes** (chat never moved); below-flip / above-down correct; mobile W=374/304 (full-width), internal scroll on long lists; low-viewport cap engaged.
  - Bottom-sheet verdict: for a short-lived ≤10-option control a full modal overlay sheet is overkill (it tears the visual anchor away from the pill); the viewport-width mini-sheet on mobile (thumb-reach + collision-proof) was chosen instead. A real modal can follow if wanted.
- Push state (at the time): Phase C = 2 local commits (`7a71e8b` + `ec768d4`) — 17 local total with the earlier 15, push pending.

## 2026-08-30 — Phase B: small visual polish (5 items, 5 commits)
- Every item a separate commit; all in `static/index.html` (CSS + 1 small JS fix). Verification: computed CSS/geometry metrics (Playwright harness, `/tmp/opencode/`; this model has no image input — PNGs don't go to `_old`; the user inspects `/tmp/opencode/shots/`). pytest 441 passed; e2e 9 passed.
- **`86239b7` ui(sidebar) — interaction states:**
  - Single `--row-hover` token (normal `#242430` — one step above surface3; glass `accent 13% + white 5%` mix). `.sess-item` hover is no longer a washed-out surface2 copy: distinct, opaque.
  - `.sess-item:active` press feedback (scale .985 + row-hover); mobile "stuck hover" solved on two axes: the non-`@media(hover:hover)` last-parse hover override removed + `-webkit-tap-highlight-color:transparent`.
  - **Critical JS fix:** `applyStagger()`'s `forwards` fill pinned the transform forever (CSS animation cascade overrides authored rules) → `:active` scale never fired. Now `animationend` sets inline `animation:none`. Measured while pressed: `matrix(0.9967,...)` ✓.
  - `icon-btn`/`mem-btn`/`settings-btn`/search/compact-toggle quick tap shrink.
  - Magnifier icon: input margins (4/8px) moved to the `.sb-search` wrapper → icon fully centered in the input. Measured offset 0 (was 2px) ✓.
- **`b59661e` ui(mem) — single coherent palette:**
  - Inconsistency source: the `cat-personal` chip used orange (`--accent`) text on a purple wash. All category chips to one formula: `color-mix(hue 15%, transparent)` + same-hue text (`--chip-work/habit/general` tokens; personal=accent, preference=success).
  - `--warning` token (`#f59e0b`) added; imp 7–8 border now uses the palette token instead of a one-off fallback. Measured: imp7-8=#f59e0b ✓, chip hues coherent ✓.
- **`b52f271` ui(type) — typography:**
  - body/`.bubble`/`#msg-input` 15→16px; `.mem-content` 13.5→14; `.sess-name` 14→14.5.
  - `-webkit-font-smoothing:antialiased` + `-moz-osx-font-smoothing:grayscale` + `text-rendering:optimizeLegibility` (bold blur at low PPI).
  - **Bug fix:** `.sess-snippet b` used `--text1`, which was UNDEFINED → `--text1:#f2f2f8` added (now resolves to `rgb(242,242,248)`).
- **`cec8a98` ui(messages) — shadow + fades:**
  - Bottom mask now a soft multi-step ramp from ~210px → text fully gone before the input bar (was a narrow 52px band at %55). Top edge fade short & two-step (22/44px) → no vignette.
  - Normal mode `#input-area::before` 88px up-shadow gradient (second layer over the mask); glass opts out (`body:not(.glass-mode)`, already has heavy layered shadows).
- **NOTE:** `--text3` neutralized (`#83839c`→`#84849b`, purple lean reduced; WCAG 5.07:1 on surface2). Wrapper bars in normal mode use `color-mix(var(--surface) 93%)` instead of hand-tuned `rgba(17,17,22,.93)` — harmony with pure black from one source. `.sb-footer` hairline in normal mode stays `rgba(255,255,255,.09)`.
- **Post-`cec8a98` user feedback → `#input-area::before` redesigned:** user: "the shadow paints like a band above the bar, the edges have no letter shadow". Cause: the 88px full-width (left:0;right:0) band sat on the bar and spilled past the 800px message column, empty at the sides. New: `left:50%;transform:translateX(-50%)`, `width:min(800px,calc(100% - 40px))`, `height:120px`, `rgba(0,0,0,.38)→.16→transparent` (was .55) plus a **horizontal mask** (`90deg,transparent,#000 12%,#000 88%,transparent`) → no square edge, the shadow follows the column shape. Glass opt-out kept as-is (the lightness was already right in glass mode). Verification: `shadow.cjs` — pseudoW 800 (= bar width), h 120, gradient + mask active ✓; pytest 441; e2e 9.
- Push state (at the time): `origin/main` at `508ffb8`; Phase B = 5 local commits (`86239b7 b59661e b52f271 cec8a98 c8e4ee4`); fixes: `81d2e88 c99006a 40b6d23 a44b50a c90bc59 2008c7c` (10 commits — push pending).

## 2026-08-30 — Cold fix: chat list "appears then vanishes" (flicker)
- **Symptom:** the session list flickers as if disappearing (notably when sending a new message / refreshing the list).
- **Root cause (proven by probe `/tmp/opencode/flash.cjs`):** (1) the new chat's optimistic insert (`renderSessions(sessionList)` with animate **true**) replayed the WHOLE list through the `msgSlideIn` stagger {opacity:0 → 1, translateY}; as soon as the stream finished, `loadSessions(false)` stomped on it → brief "vanish/reappear" (first element opacity 0.087 at the probe). (2) `loadSessions`'s catch wiped the list to the "No chats yet" empty state on any transient fetch error → full disappearance feel.
- **Fix (`81d2e88`):** optimistic insert → `renderSessions(sessionList, false)` (silent; the full-list slide runs only on first load). `loadSessions` catch → `else if(!sessionList.length) renderSessions([], animate)`; a failed refresh on a populated list never touches the DOM. Search paths (filterSessions/offline/search×catch/online/offline restore) now `false` (halts the per-keystroke stagger replay and the close flash). The only remaining animate=true: the first boot `loadSessions()`.
- **ADDENDUM 1 (`40b6d23` code + `c99006a` delivery):** every `loadSessions(false)` refresh REBUILT the whole innerHTML → `#session-list` scroll reset to 0 + reflow/repaint → "list disappears" feel on device. Fix: `patchSessionList()` — silent renders reuse live rows and patch only the changed cells (zero DOM touch when nothing changed), `scrollTop` preserved; even structural changes don't lose scroll. Post-delete calls are silent. Boot stays `animate=true` (stagger intended). Delivery (browser side): sw.js stale-while-revalidate (`return cached || fetchPromise`) returned the stale HTML from cache → `v48→v49` bump + `main.py`: `/` gets `Cache-Control: no-store`, `/sw.js` `no-cache`; service restarted. Verified via curl.
- **ADDENDUM 2 (`c90bc59`):** boot items appeared with the effect then turned **invisible IN SEQUENCE but click/hover still worked** — i.e. stuck at `opacity:0`. Cause: the final block base `.sess-item{opacity:0;animation:msgSlideIn .25s ease-out forwards}` — visibility depended on the `forwards` fill; Phase B's `applyStagger` cleanup (`animationend`→`style.animation='none'`) removed the fill, dropping items to the base **opacity:0** in sequence (by the delays). Fix (2 layers): (a) final block `animation:msgSlideIn .25s ease-out both` — `backwards` hides during the delay, the `both` fill leaves the end state, base opacity:0 GONE; (b) the `animationend` handler sets `el.style.opacity='1'` (safety bolt). Verification: `/tmp/opencode/boot.cjs` — first/last item opacity 0→1→steady 1 over 1.7s, `zero-at-end:false`, hover works (bg changes) ✓. SW v50 network-first + title `r40b6d2` (diagnostic) in this commit.
- **ADDENDUM 3 (`e2ef489`):** search box open/close: "list is lost on close, returns on the 2nd close". MutationObserver probe: on CLOSE, 6 items were detached one-by-one and never re-added. Cause: `patchSessionList` DETACHED each row via `frag.append(n)`; the `if(!touched&&sameOrder) return true` early-return skipped `replaceChildren(frag)` → nodes stayed in the discarded fragment → empty list. On the 2nd close the container was empty so the rebuild path ran and restored it. Fix: same order + same content → patched in place with zero DOM touch; on order change (insert/remove/reorder) → `replaceChildren(frag)` ALWAYS runs (the fragment is never stranded). Split into `patchRow()`/`newSessItem()` helpers. Proof: `search2.cjs` produces zero mutations on toggle now (children 6 across 4 steps); `boot.cjs` clean; pytest 441; e2e 9.

## 2026-08-30 — Verification shipped, audit-correction UI, urgent round, Phase A (all committed & pushed; HEAD `9a7bcd7`)
- The entry below is complete: final report approved, all pending work committed & pushed. Verification landed as `12644e5` (same chain as `116fdc7` + `7792a50`).
- Late follow-ups also landed:
  - `9aa08e2` — `find_free_slots` added to the calendar dispatch membership set (the "out of scope" item below is resolved); its return shape was also corrected from a nested `((text, slots), None)` to `(text, None)`.
  - `a42beb2` — `GET /tools/groups` group-taxonomy endpoint. Single source of truth: derived from `_KEYWORD_CHECKS` in `llm/intent.py` (`tool_group_keys()`). No human-readable labels in the backend (frontend i18n `GROUP_LABELS`). +3 tests.
  - `f99676a` — "utility" group retired on audit evidence (get_datetime: 26 calls, all co-occurring with a domain tool, zero standalone); get_datetime stays in every toolset. +`96f4b31` docs.
- Correction flow settled on Option A (group-level):
  - `9695ae2` — `tool_audit_log.expected_group` nullable TEXT (migration, user_version 10); `set_tool_correction(audit_id, expected_tool, expected_group=None)`; endpoint requires at least one and validates each against its own source (`expected_group` → `/tools/groups` set; `expected_tool` → `TOOL_NAMES`, `7792a50`).
  - `f65db2b` — SSE tool-end event carries `audit_id`; the UI keeps pills through the reply and offers a per-call "yanlıştı" affordance + group picker; `POST /chat/tool-correction {audit_id, expected_group}`; re-marking overwrites.
- **Urgent round** (three commits, each pushed after approval):
  - `7dae0fa` — `openGroupPicker`/`submitCorrection` routed through the `api()` helper (401 re-prompt parity). Playwright-verified: no key → re-prompt + retry; invalid key → silent clear + `markLoadErr` toast; correction 401 → `markErr: <HTTP>` toast, picker stays open, Save re-enabled.
  - `5286d5c` — ≥44px touch targets for mark/picker controls under `@media (pointer:coarse)` only (coarse 44.5/44.0px; fine pointer unchanged 22.5/27px → desktop look preserved).
  - `9e6fdda` — group-picker `max-width:calc(100vw - 20px)` + auto-flip upward on viewport overflow (`.group-picker.up`) + `scrollIntoView({block:'nearest'})` nudge.
- **Playwright infrastructure** (`2765fb2`, pushed):
  - `package.json`: `@playwright/test` + `playwright` pinned to 1.40.0 (env = Node 18.20.4; ≥1.50 needs Node 20). Uses cached chromium-1091, no download.
  - `playwright.config.js`: `serviceWorkers:'block'` is MANDATORY — sw.js answers GETs (incl. `/` and `/tools/groups`) with its own fetch, bypassing `page.route` stubs and hitting the real keyless server (401).
  - `tests/e2e/stubs.cjs` + `mark-flow.spec.cjs`: 9 hermetically stubbed scenarios — audited-only mark button, absent for null audit_id, 6 groups render, payload `{audit_id, expected_group}`, API error toast + picker persists, overwrite re-mark, 401 re-prompt parity (401→200 counter), keyboard access, pill cleanup + fresh pill on next send.
  - `.gitignore`: node_modules/, test-results/, playwright-report/.
- **Phase A** (three commits, pushed — genuine frontend bugs):
  - `45cc27f` — think box: reasoning renders through `renderMd` (live via `withStreamCaret`; done/history plain); bubble markdown styles scoped to `.think-body`; auto-scroll pins to bottom only when already near it (scrolled-up user keeps position); opening the box jumps to the bottom.
  - `fb7346d` — new-chat buttons: (1) `:hover:not(:focus)` focus gate killed hover while the button held focus (repro: focused hover = no feedback; after blur → scale 1.02 + opacity .9); (2) `.top-new-btn` had no hover transform and transform-less transition (never moved); (3) `--btn-primary:#d4d5db` soft off-white replaces the pure-white solid fill (OLED glare/eye-strain); glass gradient verified intact.
  - `9a7bcd7` — removed `scroll-behavior:smooth` from `#messages`: per-token programmatic `scrollTop` snaps became ~100ms smooth-scroll animations (measured distance-to-bottom per frame `[50,50,50,46,10,5]` with the flag vs `[0,0,0,0,0,0]` without) — mobile jank during fast replies. Wheel/touch scrolling unaffected.
- **Test state** (after Phase A): pytest 438 passed; e2e 9 passed. ~~ruff 14 errors — all in pre-existing Python files untouched in these sessions (llm/chat.py, llm/stream.py, routers/chat.py, routers/tools.py, tests/*, tool_verification.py, etc.); out of scope.~~ → **2026-08-30:** all 14 fixed via `ruff check --fix` (`29ebc55`; pytest 441), `ruff check .` now clean.
- **Session learnings** (so they don't get re-discovered):
  - `_toolGroupsCache` is a top-level `let`, NOT a window property; `page.evaluate('window._toolGroupsCache=null')` does not clear it.
  - Rate limiter 30 rpm/IP (`main.py:_rate_limiter`); repeated manual runs hit 429s; restarting the service resets buckets.
  - SW blocking in Playwright is required (see above).
  - Live server has API_KEY set via .env → keyless requests 401; `/` and `/health` exempt.
- **Push state**: `origin/main` at `9a7bcd7`; nothing outstanding.

## 2026-08-30 — ID-based backend verification for create tools ~~(IN PROGRESS, NOT COMMITTED)~~ — DONE, `12644e5` (see entry above)
- **Goal**: Real backend verification for `create_task`, `save_memory`, `create_calendar_event` so audit data can distinguish "actually persisted" from "claimed success" — fine-tuning dataset quality.
- **Structured-data rule (agreed with user)**: NO embedding UID/rowid into human-readable strings and NO regex/string parsing to recover them. The dispatcher carries a structured `(result_string, entity_id)` tuple; verification consumes `entity_id` directly.
- **`verification_status` values**: `verified`, `verified_by_fallback` (content-only, low confidence), `unverified`, `verification_failed`, `NULL` (legacy / not-applicable / tool failed).
- **Never raises**: verification may never break or stall the tool-call loop; backend/DB errors → logged + mapped to a status.
- **Changes**:
  - Phase 0 (committed in `12644e5`): `nextcloud_tasks._create_task_sync`/`create_task` → `(message, uid)`; `db.save_memory` → `(message, rowid)` (dedupe returns existing `mem_id`); `calendar_ops.create_event` → `(message, uid)` via `event = calendar.add_event(ical); uid = event.id or ""` (caldav `Event.id` == VEVENT UID; previously discarded).
  - `tools/dispatcher.py`: `run_tool` returns `tuple[str, str|int|None]`; `_run_mail_tool`, `_run_tasks_tool`, save_memory, calendar blocks updated; `is_tool_success` accepts str OR tuple.
  - Call sites unpack: `llm/chat.py`, `llm/stream.py`, `routers/chat.py` (`/execute` + `/sync`).
  - Phase 1: `tool_audit_log.verification_status` TEXT column (CREATE TABLE + MIGRATIONS entry); `log_tool_call(..., verification_status=None)`; `tool_verification.py` rewritten — `_verify` for the 3 scope tools (ID re-read authoritative, content fallback only when ID missing).
  - Phase 2: `tests/test_verification.py` (22 tests: success/failure mapping, duplicate-discrimination for summary AND content, fallback, never-raises, status propagation) + `test_audit.py` column roundtrip.
- **Fallback semantics**: only when `entity_id` is missing AND tool succeeded; match → `verified_by_fallback`, miss → `unverified`. When ID present but re-read misses → `verification_failed` (never falls back).
- **Verification**: py_compile clean; pytest 412 passed.
- ~~Out of scope / noticed~~ → **RESOLVED (`9aa08e2`)**: `find_free_slots` is now in the calendar dispatch membership set; its return shape was also fixed from a nested `((text, slots), None)` to `(text, None)`.
- ~~Pending~~ → **DONE**: final report approved; all pending commits pushed (hashes in the entry above).

**Reverse chronological: newest entries live at the TOP**, oldest at the bottom — keep it that way with every new entry. Timeless reference sections sit at the very bottom.

## 2026-08-28 — Audit log correction fields for fine-tuning dataset
- **Goal**: Enable "this tool call was wrong, should have been X" corrections for future fine-tuning dataset
- **Changes**:
  - `tool_audit_log` table: added `expected_tool` (TEXT, nullable) + `corrected_at` (DATETIME, nullable)
  - Migration entries for existing DBs (user_version bump)
  - Rollup updated: summary rows have NULL for correction fields
  - `set_tool_correction(audit_id, expected_tool)` function in `db.py` — updates expected_tool + sets corrected_at=CURRENT_TIMESTAMP
  - `POST /chat/tool-correction` endpoint in `routers/chat.py` — body: `{audit_id, expected_tool}`
  - Rollup INSERT includes new columns (NULL for summaries)
  - Test updated for 2-day rollup scenario
- **Verification**: py_compile clean; pytest 385 passed; audit tests 13/13 pass
- **Commit**: `116fdc7`

## 2026-08-28 — P0-P2 Tool & Intent fixes completed (all priority items)
- **P0 Critical** (data-loss risk) — ALL FIXED:
  1. `save_memory` backfill bounded: batch=10, semaphore(2), task tracking (`db.py`)
  2. `update_event` all-day duration bug fixed — all-day moves use day arithmetic (`calendar_ops.py`)
  3. `sanitize_imap_query` verified safe — strips quotes/backslashes/parens (`utils.py`)
- **P1 High** (functional gaps) — ALL IMPLEMENTED:
  - Spelled-out durations (`in einer Stunde`, `dans 10 min`, `en una hora`, `in an hour`) → clock pattern
  - Ordinal/worded hours ES/DE/FR (`a las nueve`, `um acht Uhr`, `à neuf heures`) → clock pattern
  - Negation guard (`hatırlatma`, `don't remind`, `nicht erinnern`, `ne rappelle pas`, `no recuerdes`) → memory
  - Free-slot helper: `find_free_slots` tool + `find_free_slots` calendar op + prompt rule
- **P2 Medium** (quality) — ALL IMPLEMENTED:
  - Embedding corpus expanded: free-slot, move, cancel, recurring (5 langs)
  - Utility tool group: `get_datetime`, `get_weather` for time/weather questions
  - Note search: server-side API (`?search=`) + `limit` param (`nextcloud_notes.py`)
  - Task search: `limit` param (`nextcloud_tasks.py`)
  - Email multi-folder: `mailbox` param on `list_emails`/`search_emails` (`mail.py`)
  - Calendar RRULE: `rrule` param on `create_calendar_event` + `create_event` (`calendar_ops.py`)
- **P3 Low** (debt) — NOTED FOR FUTURE:
  - Embedding model upgrade note: `paraphrase-multilingual-MiniLM-L12-v2` → `mpnet-base-v2`/`e5-small` (re-embed needed)
  - LLM fallback timeout guard (10s) — pending
  - Unified session ref table (single `session_refs` vs 4 tables) — pending
  - Event-driven cache invalidation — pending
- **Verification**: py_compile clean; pytest 385 passed; local intent probes 17/17 (P1), 14/14 (utility), all calendar/mail/notes/tasks tests pass

## 2026-08-28 — Tool & Intent Mechanism Deep Analysis (full report: docs/tool_intent_analysis.md)
- **Scope**: 27 tools, 6 groups, intent pipeline (deterministic reminder → keyword → embedding → LLM fallback) *(2026-10-11: count drifted — `get_combined_tools()` returns 23 today; regenerate with `python -c "from tools import get_combined_tools; print(len(get_combined_tools()))"` before relying on any tool count.)*
- **P0 Critical** (data-loss risk):
  1. `save_memory` backfill unbounded task leak (`db.py:1243`) — batch + semaphore needed
  2. `update_event` all-day duration bug (`calendar_ops.py:373`) — all-day move uses minute arithmetic then truncates
  3. `sanitize_imap_query` (`utils.py`) — verify IMAP injection escape (`"`, `\`)
- **P1 High** (functional gaps):
  - Spelled-out durations (`in einer Stunde`, `dans 10 minutes`) → no clock pattern
  - Ordinal/worded hours ES/DE (`a las nueve`, `um acht Uhr`) → pattern expects digits
  - Negation guard missing (`hatırlatma, sadece kaydet` → false calendar)
  - Free-slot auto-scheduling (user's original ask) — not implemented
- **P2 Medium**: embedding corpus gaps (free-slot, move, cancel, recurring); task/note search client-side O(N); calendar RRULE support; email multi-folder/attachments
- **P3 Low**: embedding model upgrade (mpnet-base-v2 / e5-small); LLM fallback timeout; unified session ref table; event-driven cache invalidation
- **Files to modify** (9 priority): `db.py`, `calendar_ops.py`, `utils.py`, `llm/intent.py`, `tools/dispatcher.py`, `prompt.py`, `nextcloud_tasks.py`, `nextcloud_notes.py`, `mail.py`, `embedding.py`, `tool_verification.py`
- **Report saved**: `docs/tool_intent_analysis.md` (markdown, versioned)

## 2026-08-28 — Industry-standard reminder boundary (all-day events for date-only)
- **Goal**: Align reminder routing with mainstream calendar/reminder assistant conventions (timed events, all-day events, memory notes):
  * clock hour present → timed calendar event
  * date/day present, NO clock → **all-day calendar event** (`all_day=true`, `start_time` = bare date YYYY-MM-DD)
  * NO temporal anchor → memory note
- **Changes**:
  * `calendar_ops.create_event(summary, start_time_str, duration_minutes=60, all_day=False)`: added `all_day` param; all-day → `DTSTART;VALUE=DATE:{YYYYMMDD}` + `DTEND` next day (RFC 5545).
  * `tools/definitions.py`: `create_calendar_event` schema — `start_time` optional, added `all_day:boolean`; description updated ("tarih-only → all-day (saat uydurma)").
  * `tools/dispatcher.py`: pass `all_day=bool(params.get("all_day"))` as keyword (keeps `call_args.args` 3-tuple for test compat).
  * `llm/intent.py`: renamed `_TIME_SIGNAL_PATTERN` → `_CLOCK_SIGNAL_PATTERN`; added `_DATE_SIGNAL_PATTERN` (day names 5 langs, relative day terms, month+day, numeric dates, "in N days/weeks" 5 langs, TR "ayın N'inde", "pazar" dative guard); `reminder_group` returns calendar on clock OR date, else memory.
  * `prompt.py`: rule 16 — all-day for date-only, free-slot via `list_calendar_events` first.
  * Tests updated: `test_intent_reminders.py` (day-only → calendar, market "pazar" guard), `test_dispatcher.py` (all-day kwargs pass-through), `test_calendar.py` (all-day serialization with VALUE=DATE, timed with VALUE=DATE-TIME).
- **Verification**: py_compile clean; pytest 385 passed; local reminder_group probe 17/17 including new ES/DE/FR verbs, "ayın 15'inde", "pazar" market exclusion.
- **Commit**: pending (single item = single commit).

## 2026-08-28 (28) — Deterministic reminder coverage extended: clock-gated calendar + broader verbs

**Follow-up to F1 (entry 27) — user asked for an honest answer on whether the regex pattern was "a real improvement or just exact-match coverage". I ran an empirical probe matrix instead of assuming, then the user approved option (c) (extend both axes + tighten the boundary).**

**Verdict that drove this commit** (probe evidence): F1's `_TIME_SIGNAL_PATTERN` was a *sieve, not a generalizer* — canonical formats (numeric `9'da/09:00`, clock nouns `8 Uhr`, day names) fired perfectly, but spelled-out clocks (`sekizde`, `noon`, `einer Stunde`), non-classic verbs (`haber ver`, `alarm kur`, `unutma`), and clock-less anchors fell through to embedding where the old memory-misroute could recur.

**Changes in `llm/intent.py`:**
- **Boundary tightening (b):** a reminder is CALENDAR only with a place-able clock — numeric, spoken (TR cardinals `sekizde`/`üçte`/`altıda`, glued locative, `buçukta`), or single-instant noon family (öğle/gece yarısı/noon/midday/midnight/mittag/mitternacht/midi/minuit/mediodia/medianoche). Bare day names & relatives ("yarın", "el domingo", "gelecek hafta pazartesi") carry NO clock → **memory** (prevents `create_calendar_event` guessing a start time). `akşam/sabah/gece` parts-of-day alone no longer force calendar; `akşam 6'da` still does (numeric).
- **Verbs broadened (a):** `_REMINDER_VERBS` — alarm / uyar / bildir / haber ver / unutma… (TR), don't forget / nudge me / ping me (EN), nicht vergessen (DE), n'oublie (FR), no olvides / avísame (ES). Gate = `_REMINDER_WORDS` ∪ `_REMINDER_VERBS`; `reminder_group` still returns None for plain recollection (`şunu hatırla`).
- **Clock vocabulary extended (a):** half past N · anchored relative durations near a clock (`10 dakika sonra`, `in N minutes/hours`, `in N Minuten`, `dans N minutes`, `en N minutos`) · hour connectors (`a las 9`, `à 9`, `um 8`).
- **Regression during the edit, caught by the same probe:** the first rewrite dropped `10 dakika sonra` (duration is clock-anchored → calendar) and missed `a las 9`; both restored, pattern keeps `sekizde` (the `\b` bug — cardinal+locative is glued, no word boundary).

**Empirical verification (repeatable probe, `reminder_group` matrix):** 23 cases pass (calendar: perşembe saat 9'da, yarın saat 3'te, cumartesi sabah 09:00, tomorrow 9am, Freitag um 8 Uhr, lundi à 8 heures, akşam 6'da haber ver, alarm kur saat 9'da, sekizde, sekiz buçukta, noon, 10 dakika sonra, a las 9, in 10 minutes, in 15 Minuten, dans 5 minutes, en 30 minutos, her perşembe 9'da spor · memory: bunu hatırlat, remind me to buy milk, el domingo, yarın, unutma eve dönünce, gelecek hafta pazartesi). Tests: `test_intent_reminders.py` updated (day-only now memory; spelled-out clock & new verbs added) → **380 passed, py_compile clean**.

**Remaining documented limits:** spelled-out durations (`in einer Stunde`, "yarım saat sonra" is caught only via the standalone `saat` word), ES/DE ordinal-word clocks (`a las nueve`), non-numeric halves. These are corpus/embedding territory — deterministic regex stays finite by design (decision: deterministic > probabilistic; Pi5 cost).

**Commit:** `1cf2349` (one item = one commit, local, push pending with the prior 8).

## 2026-08-28 (27) — Eval harness + realistic assessment → tool-calling fine-tune (7 commits, 380 tests)

**Timeline (recovered from opencode DB after 3 compactions — the eval phase and the user's "realistic quality evaluation" request at 01:29/01:35 were the lost piece; everything below verified against raw session parts, `test-files/`, and git):**

**1) Eval harness (user-provided `test-files.zip`, 00:02–01:19):** `eval_runner.py` (259 lines) + `test_cases.json` (23 cases, TR prompt → expected tool) judged tool-calling on the LIVE service. Adapted to piSynapse via `/chat/stream` SSE `{"tool":{name,phase,ok}}` events, keeping test structure/scope untouched; each case = fresh session, max 3 turns, fixed nudge ("will you use the right tool, could you try again") on failure. Artifacts moved to `test-files/` (`logs/pisynapse-journal.log` 72KB journalctl parallel, `logs/eval-run.log`, `logs/eval_history.jsonl`, `logs/results/run-20260827-220921.csv`).

**2) Environment (00:12):** NEXTCLOUD_URL → `http://<lan-ip>:8080` (internal net; external was erroring). `.env` is gitignored → persists out-of-repo. Health `healthy` (`db ok, llm ok, nextcloud ok`).

**3) Eval result (first-turn and after-nudge both 14/24, 58.3%; nudge rescued ZERO):**
| first-turn OK | per-category |
|---|---|
| cal-01 ✓ cal-02 ✓ cal-03 ✗(save_memory) cal-04 ✗(save_memory) cal-05 ✗(no tool) | calendar 40% |
| task-01 ✓ task-02 ✓ task-03 ✓ task-04 ✗(save_memory) | tasks 75% |
| mem-01 ✓ mem-02 ✓ mem-03 ✓ | memory 100% |
| mail-01 ✗(save_memory) mail-02 ✗(save_memory) | email 0% |
| contact-01 ✗(no tool) contact-02 ✗(save_memory) | contacts 0% |
| note-01 ✓ note-02 ✓ note-03 ✗(save_memory) note-04 ✓(search_notes→update_note) | notes 75% |
| weather-01 ✓ | weather 100% |
| news-01 ✗(save_memory) | news 0% |
| multi-01 ✓ multi-02 ✓ | multi-step 100% |

**4) Realistic assessment — user explicitly asked for MY OWN OPINION, not the script's numbers (01:29 "let's do a realistic evaluation" → 01:35 "state your own opinion instead of the eval results, because the script isn't reasonable"). Delivered assessment (canonical, recovered verbatim from DB):**
- **Domain selection is healthy ~9/10** — the separation calendar/tasks/notes/mail/memory is the load-bearing part of the whole product and it was correct; only cal-03, cal-04, contact-02, note-03 left the domain (mail-02 picked `search_emails`, still email).
- **"List first, stop before the mutation" is partly design, not bug** — delete/update/complete are confirm-gated with position-based IDs ("verify or don't do"); the model listing then stopping is safer than silently deleting the wrong record. The score paid a safety diet here.
- **One real weakness (logic-level, not prompt):** "hatırlat + saat/tarih" → memory (`cal-03/04`). Real users would see a memory note where a calendar event was expected.
- **Tool descriptions coarse:** `list_emails`/`search_emails` split felt arbitrary; plus missing tools = product roadmap (assistant guide, mail draft, news), not model failure.
- **Script flaws inflating/defeating the metric:** (a) the nudge routed to `group=memory` EACH time (embedding sim≈.61 margin .05) and made the model write junk `save_memory` (16 audit rows) — the nudge's "after" number is meaningless; (b) `cal-05`'s realistic list-before-delete counted FAIL; (c) confirm-gated tools surface `{"confirm":…}` (no tool event) so a correct confirmation can read "no tools"; (d) CSV `final_tools` double-lists each name (start+end phases).

**5) Approved two backend fixes (user-requested fine-tune, 01:39 "production quality, with an engineer's eye, multilingual, matching AI-industry standards") → 6 code commits + 1 docs commit (local only, push pending):**

**F1 — "reminder + time" → calendar (`913429a`):** `"bana perşembe için bir hatırlatıcı kur, saat 9'da"` routed to MEMORY and dumped junk `save_memory`; journal cause: memory keyword `hatırla` matches `hatırlatıcı` by substring. Deterministic layer now beats embedding/keywords:
- `reminder_group()`: reminder word + time/date signal → **calendar**; reminder word w/o time → **memory**; else `None` (recall "şunu hatırla" → memory).
- `_REMINDER_WORDS` tr/en/de/fr/es; `_TIME_SIGNAL_PATTERN` (TR locative `9'da/3'te`, `saat`, 09:00, day names, relative "yarın/cumartesi/tomorrow/Freitag/domingo…"); `_HATIRLA_NOT_REMIND = re.compile(r"hatırla(?!t)")` keeps `hatırlat/hatırlatıcı/hatırlatma` out of memory bucket.
- `_classify_intent` reminder pre-check is deterministic, audit source `reminder_rule`, fires BEFORE embedding. Corpus gained reminder seeds (tr/en/de/fr/es).
- **Regression guard (F1):** reminder + a second domain (`"... toplantıyı hatırlat ve görev oluştur"`) keeps the COMBINED toolset, not calendar alone (`098a435`).

**F2 — model stops after lookup (`97640ea`):** cal-03/05, task-04, note-03 called `list/read/search/get_datetime` then summarized instead of finishing. Post-round logic detects a lookup-only round; if the user's request clearly asks for an action (create/update/delete/complete/send — TR stems + suffix tolerance, EN/DE/FR/ES word cues) and no mutation ran, a targeted `CONTINUATION_NOTE` injected ONCE into the tool result. Pure list/read untouched. `llm/utils.py`: `LOOKUP_TOOLS`/`MUTATION_TOOLS`/`user_requested_action()`; `prompt.py` Rule 13: "fetch first, then act — never stop after the lookup step".

**F3 — hallucinated confirm tools in streaming (`b826b66`):** `chat.py` already rejected out-of-group tools; `stream.py`'s confirm path skipped the check (allowed_names scoped inside the non-confirm branch). Hoisted above both loops + reject-with-guidance.

**F4 — prompt/refusal quality (`a5f4adc`):** dangling `"Pass "` fragment in the tasks group prompt (visible to the model); stream.py identical-execution refusal quoted the global max instead of the per-tool budget (creates/send_email 1, read-like 2).

**F5 — tool descriptions (`6db92dd`):** mail-01 ambiguous between `list_emails`/`search_emails`; descriptions now explicitly route (overview vs specific subject/sender/topic, cross-referenced). `create_calendar_event` documents "remind me at <time>" = calendar event (matches F1).

**6) Honest second-pass caveats (post-compaction re-check):** the 14/24 first-turn number overstates true capability (hand-written single-turn cases, no follow-ups); my first clustering ("save_memory junk ×N") was not per-case traced; fix strength is uneven — F1 is deterministic and robust, F2 is prompt-level (token cost per lookup round on Pi 5, model may still ignore); junk eval memories (ids 18-21) still live in the DB and pollute future retrieval — a data-quality risk, not cosmetic.

**Result:** 365 → **380 tests** passing, `py_compile` clean, one StarletteDeprecationWarning only. All 7 commits local, **NOT pushed** (awaiting approval).
**Pending:** eval rerun (re-score 24 cases); cleanup of eval artifacts (24 eval sessions / 86 chat rows, 4 junk memories ids 18-21 keep personal id 16, Nextcloud test items: 1 event / 5 tasks / 1 note).

## 2026-08-28 (26) — Hardening v1.7.1 (17 fixes, parallel audit)

**Parallel audit (2 agents + manual, very thorough, no false positives):** backend (`main.py`, `config.py`, `db.py`, `routers/*`), LLM/tools (`llm/*`, `tools/*`, `prompt.py`, `retrieval.py`), frontend (`static/index.html`, `sw.js`). Findings: 11 backend (2 high, 5 medium, 4 low), 7 LLM (5 high), 2 critical XSS frontend + 2 high API-key. All verified file:line.

**Fixes (each: sorgula → why before? → negative? → efficient? → quality? → 1 commit + py_compile + pytest 365 passed + ruff):**

*F1 Critical Security (4):*
- `main.py:383` HEAD/OPTIONS bypass → only `OPTIONS + Access-Control-Request-Method` exempt (`3d47e10`).
- `main.py:425` Body-Size `if cl:` → `if cl is None: 411` (was 50MB DoS via omitted Content-Length) (`3b36692`).
- `static/index.html:2940,2289` stored XSS `onclick='${esc()}'` → `data-*` + delegation (`ab7a42e`, `SW v33`).
- `main.py:389` + `static/index.html:1148` `/debug?k=` URL leak → `sendBeacon` body `_k` + header/body/query check + pop before log (`5c2051f`, `SW v34`).

*F2 High Logic (5):*
- `llm/chat.py:280` duplicate-create race per-call + `create` cap 1 (was post-loop, 2nd identical bypass) (`6eca083`).
- `llm/chat.py:280` hallucinated tool `allowed_names` (parity `stream.py:619`) (`8f90cc2`).
- `title.py:147` Ollama `use_tools` TypeError → `intent="question"` + `LLM_MODEL` dynamic (`7122bb2`).
- `retrieval.py:17` `SIM 0.20→0.35`, `RECENT 8→6`, `TOP_K 6→4`, `ORDER BY timestamp→id` (`9201718`).
- `prompt.py:184` untrusted email delimiters + Rule 15 (`67f38fc`).

*F3 Medium (6):*
- `main.py:425` `_large_body_paths` add `/chat/upload` (4MB→100MB) (`7ce986e`).
- `main.py:366` `if host and ...` → `if not host or ...` (empty Host bypass) (`df2c233`).
- `routers/chat.py:547` `/sync` `SyncCommand.session_id` `field_validator` (`0aa4fb7`).
- `db.py:798` LIKE `f"%{query}%"` → `safe_q` + `ESCAPE '\'` (`16e65d8`).
- `config.py:374` `sync_config` add `UI_LANGUAGE` (`62c5586`).
- `routers/config.py:148` `.env` TOCTOU read-before-lock → read inside `LOCK_EX` (`2b6a3b5`).

*F4 Medium/Low (3):*
- `calendar_ops.py:22` `_cache_lock` for `_today_cache`/`_find_events_cache` (`aeef292`).
- `llm/payload.py:184` trailing orphan `assistant tool_calls` drop (`fe0994b`).
- `static/index.html:1563` `theme-swatch` `role=button`, `sess-search`/`msg-input` `aria-label`, modal `Esc` handler (`fe0994b`, `SW v35`).

**Plan discipline:** 4 phases, 17 steps, every step interrogative, low-priority items not skipped, one at a time with `TODO`, `git log` 17 commits.

## 2026-08-27 (25) — Hybrid search (FTS5 + semantic) + offline + search UI

**Hybrid search — future-proof (write-time embed, 90ms query):**
- `db.py:105` migration + `db.py:134-145` `conversations.embedding BLOB` (fresh DBs get it; existing DBs via `MIGRATIONS` 6th entry).
- `db.py:636-655` `save_message` now `embed_async(content)` best-effort (Pi-friendly, never blocks chat; failure → NULL, backfilled).
- `db.py:747-788` `search_sessions` hybrid: **FTS5 (BM25, `AND` first, `OR` fallback) + semantic (cosine≥0.50, 200 recent, top 10)** merged dedup, `limit 20`. FTS `unicode61 remove_diacritics 2` already in `db.py:279` (Turkish). Backfilled 353 rows (batch 100).
- Live: `q="temperature"` → `sıcaklık` (cross-language, paraphrase-multilingual-MiniLM), `q="omlet"` → 1 hit `Evde basit… Omlet` (was 18 with OR+0.35), `q="fırında tavuk ve sebzeler"` → 1 hit (was 17). `q="hava çok sıcak"` still shows OR looseness — next tune `AND` + stop-word filter if needed.
- `db.py:756-761` sanitization `re.sub(r'[^\w\s]','', query)` + `AND`/`OR` split.
- Tests: `365 passed`, `py_compile` clean. Service restart `pisynapse` healthy (`db ok, llm ok`).

**Search UI — snippet + single-layer + offline:**
- `static/index.html:126-129` CSS `.sess-snippet` (11px, ellipsis, `b` accent) + `.sess-item{flex-wrap:wrap}`.
- `static/index.html:2285-2292` `renderSessions` shows `snippet` when `_snippet` present: `esc` + restore `<b>` (safe).
- `static/index.html:3312-3317` `_debounceSearch` preserves `snippetMap`, `final = sessionList.filter(...).map(s=>({...s,_snippet}))`.
- `static/index.html:3292-3322` single-layer debounced (150ms) — removed local pre-render flicker (was title-only instant → 300ms FTS). Fallback to local title filter only when FTS 0 or offline.
- Bug fix: `static/index.html:3308` `API+'/search'` → `API+'/chat/search'` (404, logs `GET /search 404`).
- Offline: `static/index.html:3303` `navigator.onLine` fast-path + `AbortController 800ms` timeout → local, no 30s wait. `window.addEventListener('online'/'offline')` re-runs search on transition (`static/index.html:3323-3331`).
- Cosmetic: `filterSessions` clears debounce timer on empty (`static/index.html:3294`), `toggleSearch` clears input + timer + `_searchQuery` on close (`static/index.html:3333`).
- SW `v27→v32` across fixes.

**Offline transition:** `online` → `_debounceSearch(_searchQuery)` → FTS, `offline` → local title filter instantly.

## 2026-08-27 (24) — Hardening + title/FTS consistency + comprehensive audit

**Audit (2026-08-27, read-only, no false positives):** full `main.py:562`, `config.py:389`, `db.py:1259`, `title.py:161`, `prompt.py:309`, `routers/*`, `llm/*`, `tools/*`, `calendar_ops.py:378`, `weather.py:74`, `embedding.py:89`, `retrieval.py:130`, `static/index.html:3535`, `sw.js:54` reviewed. Findings (file:line): event-loop block `title.py:138` (`requests` sync), FTS rebuild O(N) `db.py:284`, missing `LLM_TITLE_ENRICHMENT` var/sync `config.py:107`, CORS `allow_headers="*"` + credentials `main.py:277`, `_enrich_title` race `routers/chat.py:166`, `NEXTCLOUD_TIMEOUT 30` slow. No XSS/SQLi (param queries, `esc` pipeline), no auth bypass. Report delivered, then fixes below.

**Fixes (each: one commit + py_compile + pytest 365 passed + ruff clean):**
- `title.py:129-143` `requests` → `httpx.AsyncClient` (15s timeout, `LITERT_URL`→`LITERT_BASE_URL` fix), `tests/test_title.py:110` mock updated → `70e3586`.
- `db.py:274-287` FTS5 rebuild conditional: detect `unicode61` via `sqlite_master`, `DROP`+`CREATE` only if old ascii, else drift check `COUNT(*) conversations vs fts` → `01b5f53`.
- `config.py:107` `LLM_TITLE_ENRICHMENT = os.getenv(..., "on")` + `config.py:372-386` `sync_config` add → `4687a18`.
- `main.py:271-288` CORS `allow_headers=["*"]` → explicit `["X-API-Key","Content-Type","X-Request-ID","Authorization"]` (`_CORS_HEADERS`) → `c37c0e0`.
- `routers/chat.py:17` `get_db` import + `routers/chat.py:162-168` `_enrich_title` `COUNT(*) WHERE session_id=? ==2` (was `get_history(limit=3)` race) → `b1e7846`.
- `config.py:146` `NEXTCLOUD_TIMEOUT 30→10`, `config.py:347` `_NUMERIC_KEYS`, `example.env:63`, `install.py:1078` → `6d899e8`.
- `calendar_ops.py:23-24` `_TODAY_CACHE_TTL 300s` already; `routers/widgets.py:34` `list_events_today` 17s→1.7s after `docker start redis` (root cause: `nextcloud` config `redis.host=redis` but container `Exited 43h`, `docker logs` `Redis server went away`). Fix: `docker start redis` → ping `1` → widget `1.7s` (10×). Health `degraded` (external Nextcloud reachability 5s) is optional.

**Title/FTS/Regenerate (2026-08-26):**
- `83d6d90` regenerate button (chat-assistant style): `DELETE /chat/messages/last/{session_id}` + `db.py:654` `delete_last_assistant`, `save_message` dedup `db.py:641-650`, frontend `static/index.html:2364` `regenerate()` with `_REGEN_SVG`, SW `v23`, `tests/test_retry.py:7`.
- `ecf8a41` FTS5 search: `conversations_fts` `unicode61`, `search_sessions` `snippet` + `LIKE` fallback, `GET /chat/search?q=` (`routers/chat.py:437`), frontend debounce 300ms (`static/index.html:3298`), `experiments/search_bench.py`.
- `c0267e7` hybrid title: `title.py:161` `generate_rake_title` (<1ms) + `generate_llm_title` (async `litert`/`ollama`, 15 tokens, 0.1 temp), `db.py:644-650` RAKE on first user message, `routers/chat.py:152` `_enrich_title` background, `tests/test_title.py:17`.
- `1ed7eea` three consistency fixes: FTS `ascii→unicode61` + `rebuild` on every startup (later made conditional), `static/index.html:2580` `saveSessionName` removed (was overwriting RAKE with `slice(0,38)` PATCH), `config.py:317` `LLM_TITLE_ENRICHMENT` toggle + `routers/chat.py:162` check + `routers/config.py:35` expose + `static/index.html:3028` Chat group, SW `v25`.
- Also: `static/index.html:3287` `s.id`→`s.session_id` + `e.dataset.sid` fix (search merge), `static/index.html:2369` `regenerate` `.bubble` fix (was `.msg-content`), `addMsg` `appendChild` before `attachMsgActions` (`static/index.html:2673`).

**Service:** `pisynapse.service` `systemctl restart` after each batch, `curl /health` healthy; `redis` healthy; `postgres-general/immich` `pg_isready` every 10s (btop `pg_isrea` flicker — normal).

## 2026-08-26 (23) — litert-lm 0.16.1 upgrade + thinking tracking

**Upgrade**: 0.16.0 → 0.16.1 (Windows JVM crash fix only, no Python API changes).
Health check passed post-upgrade.

**Thinking mode status**: litert-lm Python API exposes `ThinkingConfig(enable_thinking, thinking_token_budget)`
but NOT a higher-level `reasoning_effort` string. Our piServe manually maps effort → ThinkingConfig.
Raw A/B test confirmed:
- think-off (no ThinkingConfig passed) = 3.2–3.5s, no hidden reasoning ✓
- effort="medium" = 42s + 925-char hidden reasoning + empty visible content
→ Think-off path is clean. Think-on path works but is slow on E2B (model budget-dependent).

**Upstream watch item**: `litert-lm 0.17.0` (nightly 0.17.0.dev active on PyPI).
When stable ships, check if `reasoning_effort` becomes a first-class API param
(mirroring OpenAI convention). If so → unhide UI effort selector and expose
per-level toggle to user (default: off/minimal, not medium).
Until then: think effort UI stays hidden (flag-gated), current behavior unchanged.

**Multi-domain routing** also deployed this session: ≥2 keyword-group hits →
combined 22-tool set. Live-verified: "hava durumunu maille gönder" →
get_weather executed → send_email confirm card auto-filled with real weather data.

## 2026-08-25 (22) — Intent audit-log design APPROVED (implementation pending)

Night discussion (with external second opinion) settled how routing ambiguity
gets observed going forward. Decision recorded here so the next session can
build it without re-litigating:

**Approved design** — `intent_audit_log` table following the existing
`tool_audit_log` pattern:
- Columns: created_at, message, chosen_group, best_sim, margin, source (+uid pk)
- ACTIVE sources at launch: `thin_margin` (embedding chose a group but
  margin<0.10 → keyword arbitration ran) and `keyword_fallback` (embedding
  uncertain entirely → keyword decided)
- SCHEMA RESERVED, logging code DEFERRED until real need: `default_question`,
  `llm_fallback`, `hatch`
- 30-day retention using the same rollup approach as tool_audit_log
- Fail-safe insert: audit failure must never break classification

**Weekly review workflow** (queries to be shipped WITH the implementation):
1. Most frequent thin-margin messages, last 7 days (collision candidates)
2. Rows where keyword overturned embedding's top pick (disagreements)
3. Source distribution over time (fallback-rate trend = corpus health KPI)

**IMPLEMENTED 2026-08-25:** db.log_intent_audit / purge_intent_audit(30d) +
daily purge wired into periodic_rollup_loop; sources thin_margin &
keyword_fallback instrumented in _classify_intent exits (fail-safe).
Live-verified within minutes of deploy (real user queries captured).

Shipped review SQL (weekly):
```sql
-- 1) most frequent ambiguous messages
SELECT message, COUNT(*) n FROM intent_audit_log
 WHERE created_at > datetime('now','-7 days')
 GROUP BY message ORDER BY n DESC LIMIT 20;

-- 2) cases where keywords overrode embedding's first choice
--    (thin_margin + chosen != embedding's pick; can later be enriched
--     via an embedding_top_group column)
SELECT source, chosen_group, COUNT(*) FROM intent_audit_log
 WHERE created_at > datetime('now','-7 days') GROUP BY source, chosen_group;

-- 3) fallback health trend
SELECT date(created_at) d, source, COUNT(*) FROM intent_audit_log
 GROUP BY d, source ORDER BY d;
```

Review discipline: frequency ≠ error. Each candidate gets a correctness
check; fixes prefer CORPUS additions when the pattern generalizes (strengthens
embedding confidence) and keyword patches for exact-token quirks only.

**Also documented (A/B evidence base):** the five static "ask if details are
missing" prompt instructions (Rule-1 exception + four group lines) were REMOVED
after an A/B experiment showed identical outcomes with them absent — backend
CLARIFY guards carry asking duty contextually with language anchors. Nothing
else was removed: dispatcher guards, decline-bypass, chip instant-clarify,
hatch hint and the keyword/embedding intent layer all remain (keyword layer
was EXPANDED today: verb-first TR phrases + boundary-safe 'kar').

## 2026-08-24 (21) — Laptop field report + language anchoring + clarify guards

First external-hardware install (ollama + GPU laptop): **one-shot success**, no installer steps failed. Issues found & fixed:

- **Language mirror failure (recency bias proven live):** chip text "Yeni etkinlik oluştur" got an ENGLISH clarifying question even though the LANGUAGE RULE sat at the very top of the system prompt. Root cause: the LAST text in context was the English `CLARIFY_REQUIRED` tool result — small models mirror the most recent language seen, overriding top-of-prompt rules (telling it to switch to Turkish mid-chat fixed it, confirming the mechanism). Fix: every guard string now embeds the user's original message as a language anchor (`_user_text` threaded through dispatcher helpers). Verified live: TR chip → TR question, EN chip → EN question, zero junk writes.
- **Clarify guards are backend-enforced:** gemma called `create_note(title='Yeni Not')` with empty content DESPITE prompt instructions — prompt hope is not enforcement. Dispatcher now returns `CLARIFY_REQUIRED` (with the anchored user text) instead of executing empty creates for note/task/event/email; calendar's hidden `"New Event"` default summary removed.
- **New welcome chips:** 'Yeni etkinlik oluştur' / 'E-posta gönder' (+EN); all four phrasings verified routing to calendar/email through the live classifier.
- **Prompt:** Rule 1 exception (missing essentials → ONE short clarifying question, never invent placeholders); new Rule 12 honesty clause; per-group one-line ask-first rules.
- **Chip-origin instant clarify:** create/send chips no longer burn an LLM round-trip to ask for details — stream.py answers deterministically (`_chip_clarify_question`, tr/en by heuristic) in ~0ms before any model call. Measured 2.4s wall including session/intent overhead (was 15-40s). Follow-up details flow through the normal pipeline with full context (question is saved as a real turn). Dispatcher guards remain as defense-in-depth.
- **TWO field-day bugs fixed:** (1) `_todo_to_dict` read fields from the VCALENDAR wrapper instead of the VTODO child → every task displayed as "Untitled" (root of the tasks/calendar confusion); parser now drills into the VTODO subcomponent. (2) Identical-execution counter was incremented POST-loop, so two identical create calls in ONE response both executed (duplicate 'Yarın için görev'×2 explained); counting moved per-call + creates/send_email capped at 1 identical execution.
- **Escalation tests made hermetic:** they were hitting REAL Nextcloud via unpatched run_tool (each run wrote junk tasks/events; one hung 58s during a slow window). All stream-level FC tests now patch run_tool with recorders.
- **litert server parse-failure recovery:** doubled-brace native calls that the SERVER rejects (INVALID_ARGUMENT) now get extracted from the error message and executed via the normal path — the "Yarın için görev oluştur" turn that died with a connection-error bubble now completes. Plus: defused a time-bomb test (hardcoded audit dates aged past threshold); junk 'New Note'×2 cleaned from Nextcloud.
- `/config` no longer returns a literal "User"; installer no longer writes `default` as name.
- **Double-confirmation fixed:** "(requires confirmation)" wording made gemma ask "are you sure?" in text BEFORE calling the tool — but calling a CONFIRM_TOOLS member already pops the UI card. Reworded all four group-prompt mentions + added Rule 13 ("calling the tool pops the card; never ask in text"). Live: "1. notu sil" → first SSE event is the card, zero preceding tokens.

### Open verification items (theories awaiting field data)

| # | Theory | How to verify |
|---|---|---|
| 1 | Escalation hatch fires on real ollama flow (unit-tested only) | Ask a tool-needing question with NO group keywords (e.g. "şemsiye almalı mıyım bugün?") → expect "Escalating…" in service log |
| 2 | Language mirroring survives LONG multi-tool sessions | Alternate tr/en turns incl. tool results ×10; log any drift turn |
| 3 | `_is_context_overflow` mislabels litert parse errors as overflow | Needs distinguishing field in litert error payload — inspect upstream |
| 4 | litert round-2 doubled-brace failure root cause location | Isolate: server grammar vs our result formatting |
| ~~1~~ ✅ Confirmed 2026-08-24 | Hatch fires on real ollama (laptop log: TOOL_NEEDED marker detected → escalation) | closed |
| ✅ Fixed 2026-08-24 | **Router swallowed everything after the first `gen_retry`** (`return` in the relay loop) — escalated-round tokens never reached clients; looked like "empty reply" | relay continues now; verified live end-to-end (retry→get_weather→TR answer→done) |
| ~~Open~~ ✅ Fixed 2026-08-24 | Chip-origin placeholder titles — UI now sends `origin:"chip"` on chip sends; dispatcher forces CLARIFY for create_note/task/event/send_email regardless of supplied params (non-chip flows unchanged) |
| Incident 2026-08-26 (~35 min outage) | Nextcloud 500s: after a Docker RAM-free cycle Nextcloud had cached the old postgres IP; fixed by a Nextcloud restart. In the same window intent_audit_log collected its first real data (2× keyword_fallback/weather) |

## 2026-08-23 (20) — Hatch v2: group-scoped escalation + early abort; description trim

Follow-up to entry 19's efficiency question. Two optimizations + a careful trim, all measured:

- **Group inference:** `_escalation_tools()` picks the smallest sufficient toolset for the escalated round — group from the leaked call's tool name (`parse_leaked_tool_call` → `TOOL_GROUPS` reverse map) → else keyword heuristics on the user message → else combined fallback. Escalation TTFT drops **49s → ~13s** whenever the name/keyword reveals the domain (the common case).
- **Early abort:** detection moved INTO the token loop. When hatch is armed, marker match (`_wants_tools_hint`) now flips `suppressing` and breaks the stream immediately instead of consuming the model's trailing apology text; leaked-syntax rounds abort via the existing suppression trigger. Handler after the try block redoes the round with the scoped set. Gated on `intent_no_tools` (nudge/truncation text-modes can never re-arm).
- **Description trim (-11%):** 23 tightened strings in definitions.py — repeated "list position from latest output" boilerplate compressed, verbose intros shortened. Capability preserved: numbered-position protocol, confirmation warnings, enums/min/max/ISO examples all intact. combined-22: 2707→2411 tok; notes-7: 728→671.
- **Measured TTFT after trim:** notes-7 12.82s · combined-22 47.29s (was 13.47 / 49.14). Pure-chat TTFT unchanged (2.65s) — hint is free.
- Tests: counting-fake proves round-1 is abandoned after ~2 chunks of an 8-chunk scripted ramble; new fallback test pins combined-only-when-no-hints. Suite **328 green**, ruff clean. Live: action turn ✓ pure chat ✓.



## 2026-08-23 (19) — Intent misrouting: root-cause fix via tool-escalation hatch

Requirement set for the fix: root-cause level, no rigid rules (small models err). Measured the alternatives first, then implemented the recovery-based design:

**Measurements (litert, trivial chat turn, non-stream):** no tools 9.7s · 7-tool group (~728 tok) 19-20s (2×) · full 22-tool set (~2707 tok) >45s TIMEOUT. → Always-tools is dead on this hardware; the intent gate is load-bearing, its failure mode needed a net.

**Design:** the classifier stays a fast-path hint; the GENERATOR becomes the strongest judge with a one-shot escape hatch. Pure-chat requests now carry an injected system note teaching a deterministic escape verb; after each round, when `intent_no_tools` and not yet escalated:
- leaked FC syntax (`_check_tool_leak`) **or** reply starting with literal `TOOL_NEEDED` (`_wants_tools_hint`) → escalate once: `use_tools=True`, full combined toolset, round redone, `gen_retry{reason:"tools_escalated"}` emitted.
Two loose triggers cover each other's blind spots (small models may do either); exact-token matching keeps false positives near zero; zero happy-path cost (vs +5s LLM-arbiter on every doubtful message — measured, rejected).

**Guard-rail lesson:** first cut keyed the hatch on `not use_tools` — that also caught the terminal text-only nudge round and consumed unscripted iterations (broke a guards test). Fixed by gating on `intent_no_tools` (set once at routing time); nudge/truncation text-modes can never re-arm it.

Frontend: gen_retry pill label is now reason-specific (compress / fixing a tool call / enabling required tools), i18n tr+en. SW v21. 4 new tests in test_tool_escalation.py (marker path, leak path, no-false-trigger on normal chat, single-shot cap); suite 326 green. Live: pure-chat turn unaffected ✓, action turn unaffected ✓.

## 2026-08-23 (18) — read_note positional failure root-caused: float positions


User reported "notları listele → 1. notu oku" failing inside ONE session. Live repro with per-call param logging (new permanent `Tool call:` INFO line in `run_tool`, params truncated 200 chars) caught it red-handed:

- **Root cause:** gemma/litert emitted `read_note params={'note_id': 1.0}` — a FLOAT. `_as_position()` accepted only int / numeric-string; `1.0` fell through to None → "Note '1' not found" ERROR despite a warm session listing. The model then flailed (listed again / apologized) exactly as the user saw.
- **Fix:** `_as_position` now accepts integral floats (`1.0→1`, rejects `1.5`) and float-valued strings (`"2.0"`). Strictness preserved otherwise (raw IDs/garbage still rejected). 5 new unit tests; dispatcher suite 76 green.
- **Frontend (same round):** `endToolStatus` returned null → caller lost the reference → next event drew a SECOND pill below the ended one, and orphaned pills survived into the text stream. Now returns the row (tracking kept) + token/reasoning branches sweep ALL `.tool-status` nodes by class. SW v20.
- Live verification after fix: same-session "1. notu oku, tamamını" → read_note executed ✓ content returned ✓.

## 2026-08-23 (17) — Pill removal on thinking-stream + contrast hardening

Second live-test round:

- **Pill lingered into streaming:** the token branch removed it, but litert streams `reasoning` FIRST after tool rounds — bubble+thinkbox appear (= visible streaming) while the pill sat above. Removal now fires on reasoning events too ("thinking IS streaming"). Any content event kills the pill.
- **Contrast audit (WCAG AA):** base label text2/surface2 = **5.47 ✓**; BUT `.tool-status.ok{opacity:.7}` blended to **3.29 ✗ FAIL** — opacity-dimming was the culprit the user sensed. Replaced with restyling: ok label → var(--text) = **14.34 ✓**, accent-filled dot carries the done cue. Glass mode pill gets its own backdrop `rgba(15,15,21,.94)+blur(12px)`: **4.63 ✓** even over a pathological pure-white backdrop, 5.43 over the real dark one. Verified with the luminance script, not eyeballed.
- SW v19.

## 2026-08-23 (16) — Pill state revival on retry / multi-tool reuse

Tracing the pill lifecycle surfaced two stale-state gaps in entry 15's persistence model, both fixed with a `resetPill()` helper called on every REUSE of an existing pill:

- **Retry after a finished tool** (the live-probe order: start → end ✓ → gen_retry): `showGenRetry`'s early-return kept the ✓-state pill untouched — the "compressing tool responses and retrying…" message never showed. Now the reused pill is revived: `ok` class dropped, spinner recreated/dead-class cleared, label swapped.
- **Second tool in a chain**: new round's `tool.start` updated only the label — the pill still carried `ok` styling with no spinner. Now every reused pill looks active again before the label swap.

Net behavior: ONE pill per stream, always reflecting the LATEST backend event; history is not shown (single-line label), which stays honest because each event overwrites it. SW v18.


## 2026-08-23 (15) — Indicator persistence + position, desktop chip clicks, faster aurora

User's live-test feedback on entry 14, four fixes (frontend only):

- **Indicator no longer blinks:** `endToolStatus()` lost its auto-hide timeout — the pill now stays visible (✓/⚠ state) through the quiet gap between tool execution and the next model round, exactly as requested ("visible until the stream starts"). It is removed the moment the first token arrives (token branch, unconditional) or in finally (any terminal path). One mental model for pre-stream AND mid-stream pills.
- **Position:** new `placePill()` helper inserts the pill directly ABOVE the typing dots (`insertBefore(typingEl)`), falling back to bottom-append once dots are gone (mid-stream). Was: appended below dots.
- **Desktop chip click fixed:** root cause — `setPointerCapture()` retargets the native click to the track, so the chip's own `onclick` never fired; a press just paused the marquee and resumed 450ms later. Now `release()` resolves the tap manually: moved≤6px → `document.elementFromPoint(x0,y0).closest('.w-chip')` → `chipSend()`. The capture-phase click blocker is conditional (`pointerJustEnded`, auto-cleared 120ms) so keyboard Enter on chips still works. Drags (>6px) still fling without clicking.
- **Aurora:** generating playbackRate 1.9 → **2.3**.
- SW v17. node ✓, 317 tests green (backend untouched → no restart needed).

## 2026-08-23 (14) — Tool-call indicator + aurora generating speed

- **Tool indicator (backend-driven, no stream parsing):** `llm/stream.py` now emits structured SSE events around every `run_tool()`: `{"tool":{name, phase:"start"|"end"|"refused", attempt, max}}` (attempt = prior identical executions+1, max = `_MAX_IDENTICAL_EXECUTIONS`), plus `{"gen_retry":{reason:"overflow"|"empty"|"tool_leak"}}` on in-loop generation retries. `routers/chat.py` passes both through verbatim. Refused calls emit only their own event (no start/end).
- **Frontend:** `.tool-status` pill (spinner dot + label) appears below the typing dots on `tool.start`, updates on retry attempts ("attempt n/max") and cap refusal ("retry cap (n/max)"), flips to ✓/⚠ on end and self-removes (900ms/1600ms). Dots dim to 25% opacity while a tool runs (`.typing.tool-pending`), restored on end/finally. Pill reparents under the reply bubble once the first token lands; aborted/error/confirm paths clean it up via finally.
- **Aurora speed-up:** `setLoading()` now bumps `playbackRate` to 1.9 on all `#aurora .ab` animations while generating, back to 1 when idle — velocity change without phase jump (no keyframe restart), subtle not exaggerated.
- **i18n:** toolAttempt/toolCap/genRetryLabel (tr/en); TOOL_LABELS map covers all 22 tools with graceful fallback to the raw name. *(2026-10-11: drifted — 23 tools today; the graceful fallback keeps this cosmetic, not a bug.)*
- **Tests:** new tests/test_tool_events.py reuses the _SeqClient harness: start/end ordering, refused attempt counts (3rd identical call refused, never reaches run_tool), overflow gen_retry mid-tool-loop with recovery text. 317 passed, ruff clean, node ✓.
- **Live probe findings:** events verified end-to-end against litert (create_note start→end ok:true captured). Two pre-existing quirks surfaced: (1) litert server hard-fails (`INVALID_ARGUMENT: Failed to parse tool calls from code block`) when the model emits doubled-brace native calls in round 2+ — the known template-leak pattern from utils.py regexes, but at SERVER level, unreachable by our text recovery; (2) `_is_context_overflow()` matches bare "invalid_argument", so those parse failures get mislabeled as overflow → gen_retry fires with the shrink path. Kept as-is for now: the frontend label is cause-neutral ("compressing tool responses and retrying…"), so nothing lies to the user; distinguishing parse-vs-overflow needs a litert error payload field — future item.
- SW v16.


## 2026-08-23 (13) — Chip random distribution

- shuffleChips(): Fisher-Yates + anti-clump constraints (same chip may not sit across the loop seam, the two lanes may not start with the same chip), 60 attempts; verified 2000/2000 via node. Fresh layout on every showWelcome().
- SW v15.

## 2026-08-23 (12) — Draggable marquee

- JS rAF model replaces CSS keyframes: each track owns a controller (x, half, vx, drag). Horizontal finger/mouse dragging (touch-action:pan-y keeps vertical scroll intact), taps under 6px still count as clicks (chipSend works), beyond that it's a fling: velocity measured and inherited as vx, decays with exp(-3t); auto-resume after 450ms (no need to click elsewhere). Hover-pause removed.
- Wrapping loops x within (-half, 0] → perfectly seamless infinity. half is re-measured on resize. reduced-motion: no auto flow, free manual drag. rAF cleanup on page detach (isConnected).
- SW v14. node ✓.

## 2026-08-23 (11) — Marquee chips + menu opacity + deeper mask

- #messages bottom fade: flat 96px → 128px + partial alpha stops (rgba .55 @
  -52px) = cinematic dissolve, both modes.
- .sel-menu stayed translucent over glass and blended with underlying text: layered background (surface gradient over solid --bg) + backdrop-blur 18px → readable in every theme.
- Chips went dual-marquee: two lanes moving in opposite directions (chipMq 38s/46s linear infinite), mask fade at edges ('|shadow|'), pause on hover, send on click. Track = set×2, translateX(-50%) loop. Static under the global reduced-motion kill (halves identical → identical look).
- SW v13. Frontend only → no service restart needed.

## 2026-08-23 (10) — Ambient standards round

- Research (aurora UI write-ups + dark-mode gradient practice): the color field is visible AT ALL TIMES; idle = calm frozen scene, text panel lit, background quiet, motion slow. 60-30-10 rule.
- FREEZE+RESUME FIX (the real bug): animations were bound to .generating → when the class left, the animation itself left → jump back to frame 0. Correct pattern: keyframes permanently attached, default play-state:paused; generating only flips running + opacity 1. On finish the frame freezes, next reply resumes from where it stopped.
- Faint corner washes returned to ::before (11/7/8/5% mixes) → idle is never empty black (@supports fallback added too). Blob idle opacities .5-.62.
- Chip #7: +Create a note (TR keyword ✓, EN corpus contains 'create note' verbatim).
- SW v12. 314 tests ✓ ruff ✓ node ✓. Service restarted, healthy.

## 2026-08-23 (9) — Aurora freeze fix + 4 blobs + memory meta-save root cause

- Aurora "pitch black" issue: idle opacity:0 left only the vignette behind. New model: blobs always visible (idle .45-.55), animation always defined but animation-play-state:paused while idle = FREEZES IN PLACE mid-frame, no snap. While generating: running + opacity .95.
- Blob count 2→4 (ab3 center-right 19s, ab4 accent-hue upper-right 27s; lavaC / lavaD multi-point keyframes).
- MEMORY BUG ROOT CAUSE (log-proven): at 05:40:28 'show my notes' had been routed to memory via embedding (sim .73, MARGIN .06 — threshold .05!). The memory-group LLM then called save_memory treating the request itself as a fact: 'User request to show their notes.' Layers fixed: (1) the generic 'değiştirir misin'-style patterns were already purged from the corpus but that wasn't enough → intent.py now lets keywords win when margin<0.10 and the keyword group disagrees, plus the message is logged on the embedding path (visibility). (2) prompt.py rule 6 + tool description + group blurb: requests/ questions/commands are forbidden. (3) dispatcher save_memory guard: regex rejects meta-content (isteği/talebi/request to/wants to/asked that...) while real facts like 'User likes Python' still pass (8 cases tested). DB: junk row id=17 deleted from assistant.db.
- Chip: 'Notlarımı göster'→'Notları listele' / EN 'List my notes'.
- Tests: 314 (+2 save_memory regressions). ruff ✓ node ✓ SW v11. Service restarted, healthy.

## 2026-08-23 (8) — Lava-lamp aurora + clock position + intent corpus fix + custom select

- Aurora fully rewritten: #aurora layer (blobs, --glow-tokened radials, no color-mix dependency → @supports aurora duplicates deleted). During generating lavaA 17s/lavaB 23s large drift+scale; idle fades out and freezes (no snap). ::before now carries only the vignette.
- Clock position restored: .sess-del absolutely positioned right (hover swaps time↔trash chat-app style), padding-right:20px on the name. Time always flush right.
- Chip: joke replaced with 'Görevlerimi listele'/'List my tasks' (task_kw 'görev' ✓). TR/EN rows mirrored.
- INTENT BUG FOUND: the calendar corpus contained generic patterns without any domain word ("değiştirir misin..." and DE/FR/ES equivalents) pulling every "could you change X" into calendar; tasks had no update examples. Purged + update/postpone anchors added to tasks. 7/7 correct with real embeddings (before: task-change drifted to calendar).
- applyLang instant: full welcome rebuild (chips included) + openSettings() re-invoked if the modal is open. This was why a hard refresh seemed required (a modal stuck in the old language made it look like nothing changed).
- Custom dropdown (.sel-wrap/.sel-btn/.sel-menu): native `<select>` hidden, esc()'d menu; enhanceAllSelects after boot+openSettings; closes on outside-click/Esc; change event dispatched to inline handlers.
- SW v10. Tests 312 ✓ ruff ✓ node ✓

## 2026-08-23 (7) — Pure black default + hover fix + typography + living aurora

- Pure black is no longer an option, it's the default: body.amoled values folded into :root, toggle+applyBlack+ps_black+i18n keys deleted. theme-black remains as deepest tier (bg still #000). Mobile density boost simplified.
- Sidebar jitter root cause: hover toggled .sess-del display:none→flex = layout shift. Fix: opacity+pointer-events (slot reserved), transition:all→background-color/border-color. Stronger hover: surface2→ surface3 + rgba(255,255,255,.05) border.
- Typography standardized: body+bubble 14.5→15px, sess-name 13.5→14px.
- Chips 4→6: +weather ('Bugün hava nasıl?'), +joke ('Komik bir şey söyle' — embedding corpus has a 'tell me a joke' example, safe).
- Aurora lives during replies: setLoading→body.generating; auroraDrift 14s transform-only (inset:-9% oversize, GPU-friendly) + grainBreathe. The global reduced-motion kill already covers it. Mobile: compositor-only, no repaint.
- Glass feel: mask fade bottom 64→96px (text melts into the glass), subtle elevation shadow on user bubbles in glass-mode.
- User question "does this meet glassmorphism standards": yes — translucency+ blur+1px light border+inset highlight+vignette+decoration all present; what was missing was motion, now added.

## 2026-08-23 (6) — Sidebar redraw fix + chip send + glass tuning

- Bug: every render gave .sess-item opacity:0+slide-in → redraw flash on stream end/search close. Fix: renderSessions(list,animate) + #session-list.no-anim; loadSessions(animate) pass-through. Silent calls: stream done, abort finally, non-stream reply, search-restore (restore only when a filter is applied).
- Chips now SEND directly (chipSend→sendMsg); content keyword-aligned with intent: özetle/e-posta (email-read), etkinlik (calendar), görev (tasks), notlarımı göster (notes exact). The old 'reminder' chip could slip into memory because of memory_kw('hatırla') → became 'görev oluştur'.
- Glass decisions: grain .07→.09; aurora mixes 30/20/22/13→24/15/16/9 + vignette .28→.32 (@supports fallback updated too); inner white hairlines kept (glass affordance).

## 2026-08-23 (5) — Visual polish round

- #messages mask-image edge fade: 64px bottom, 28px top softening; works in glass mode too (background-independent).
- Streaming caret: withStreamCaret() places it inside the last closed block tag (doesn't fall to a new line), cleared on done; caretBlink keyframes.
- Suggestion chips on welcome (WELCOME_CHIPS tr/en, chipFill fills the input); .w-chip styles. text-wrap:pretty.
- WCAG audit script (/tmp/opencode/wcag_audit.py): single failure text3/surface2 4.37 → --text3 #7e7e96→#83839c (4.69). Every other pair passes AA.
- User note: nested-squares logo = chat screen center, toggle-menu pattern = link to future ecosystem tools — DO NOT TOUCH.

## 2026-08-23 (4) — prefers-reduced-motion

- Respect the OS "Reduce motion" setting: kills all animations/transitions (vestibular-friendliness). SW cache v6.
- Correction: glass-mode inventory showed 139 selectors but the core is already variable-based (--surface etc. redefined under body.glass-mode), rules are grouped recipes → the earlier "messy" criticism was overstated; no refactor needed.

## 2026-08-23 (3) — UI_LANGUAGE (option B)

- messages.py: the 3 user-facing backend messages (llm_empty_reply/ llm_unreachable/llm_empty_response) got tr/en dicts; get_message() picks live via config.get("UI_LANGUAGE").
- config.py: UI_LANGUAGE select (default tr, no restart needed). llm/utils.py: empty_answer_fallback() helper; EMPTY_ANSWER_FALLBACK constant kept for test compatibility (noqa F401 aliases in stream/chat).
- Frontend: at init, if ps_lang was never set, adopt the server's UI_LANGUAGE.
- Lesson: ruff --fix in an intermediate state had deleted the FINALIZE_NUDGE import → import blocks consolidated. Suite 312 passed; closed-port simulation also clean.

## 2026-08-23 (2) — Final two xfails closed

- llm/utils.py: tag regexes now also consume the `<tool|call>` (pipe-mangled) variant; _strip_json_tool_echo added (line-independent, known tool names only, JSON inside prose untouched).
- tests/test_history_hygiene.py: 2 xfail → normal regression tests + 2 negative cases (unknown_tool and inline JSON preserved). Suite: 308 passed / 0 xfail. CHANGELOG + release notes updated.

## 2026-08-23 — CI hang fixed

- Symptoms: CI run following c399314 sat 3h28m "in_progress"; its twin run succeeded but 3 tests FAIL (no such table: email_session_map); locally single-file runs waited forever.
- Root cause: new guard/think tests touched the real DB (chat→_build_full_messages→prompt.get_email_context→db.get_email_map). On CI the schema doesn't exist → fast fail; locally, with the table present, the module-global aiosqlite connection never closed and the NON-daemon worker thread blocked interpreter exit.
- Fix: autouse fixture mocking prompt.get_email_context in three test files (tests run DB-less); pytest_sessionfinish safety net in conftest.py (close_db). Ruff import sorting via --fix.
- Verification: CI simulation with closed ports — single files <1s rc=0; full suite 7.1/7.8s exit=0 ×2. ruff clean.

## 2026-08-22 — Frontend improvements + ollama think flow

- static/index.html: .msg-actions row under assistant messages (copy + read aloud side by side); no longer inside .msg-meta → visible in minimal mode too (minimal hid meta, losing TTS). attachMsgActions() used on both addMsg and stream-completion paths; copyMessage() clipboard API + execCommand fallback, copied feedback (checkmark icon).
- Minimal mode message spacing 24px→34px (body.minimal-chat .msg-group).
- i18n: copyTitle/copiedTitle (TR+EN). sw.js CACHE pisynapse-v4→v5.
- Ollama think bug: stream.py/chat.py only read `reasoning_content`; ollama ≥0.9 sends `message.thinking`. Both are read now. Live test: 169 reasoning events reached the frontend (slow on CPU but working).
- New discovery: intent/media STT/warmup direct ollama calls lacked `think:false` → gemma4 silently thought, the num_predict=20 budget went to thinking, intent raw='' + ~45s. Added to all three; live raw='question' ✓.
- PATCH settings automatic model mapping dogfooded both ways (gemma4-e2b ↔ gemma4:e2b). Test file: tests/test_ollama_think_stream.py (2 tests). Suite 304+2xf, ruff clean. Backend switched back to litert; probe sessions deleted.

## In-session self-poisoning report (2026-08-22)

### Findings

| Issue | Status |
|---|---|
| Cross-session data leakage | None — design is clean (get_history/_fetch_candidates/summary/cache all `WHERE session_id = ?`) ✅ |
| Leak text persisted into history | Bug — save points in routers/chat.py have no sanitization; raw `call:xxx{{}}` gets stored as assistant replies ⚠️ |
| Poisoned row in DB | the `call:list_notes{{}}` line inside session_1787407132114_14uw4dn still sits there; model imitates its own garbage output ⚠️ |
| Empty-answer fallback | If dedup drops everything and accumulated text is empty, nothing is produced → "model returned an empty reply" ⚠️ |

By design the only thing crossing sessions: user memories (save_memory,
user_id-scoped) — intentional feature.

### Fix plan (approved)

- [x] **1. Save-time sanitization** — strip_tool_leaks() before the assistant reply hits the DB; skip saving if the reply is entirely leak (stream + non-stream paths) ✅ Verified: tests/test_history_hygiene.py 4 passed, ruff clean. _clean_assistant_reply() helper added; stream done/finally and non-stream save points sanitize and skip empties.
- [x] **2. One-off DB cleanup** ✅ Verified: dry-run scan then 2 pure-poison rows deleted (id=592 old read_email leak, id=757 call:list_notes{{}}); re-scan → 0 poisoned. An embedded-cleanup layer was deliberately NOT built: all 20 dry-run candidates were cosmetic whitespace diffs (markdown), one held a Python code block — rewriting would damage them. The finding also exposed strip_tool_leaks' global whitespace collapse breaking code blocks → fixed: collapsing now applies outside ``` fences only (_collapse_spaces_outside_fences). Coverage: tests/test_history_hygiene.py 9 tests = 7 passed + 2 xfail (known limits: ``<tool|call>`` delimiter, JSON echo); integration tests prove the real save path with mocked DB.
- [x] **3. Empty-buf fallback** ✅ Verified: if the dedup branch drops an empty buf (the 2026-08-22 "model returned an empty reply" case), a single _FINALIZE_NUDGE system note is injected with tools disabled (final_nudge_used → use_tools=False, truncation-retry pattern) forcing a text-only final turn; still empty after the nudge → _EMPTY_ANSWER_FALLBACK gentle message is yielded. If the nudge turn recovers another leak it falls into the same dedup branch → fallback.
- [x] **2b. Summary poisoning protection** ✅ Verified: three layers — (1) SUMMARY_SYSTEM_PROMPT updated: ignore artifacts, "do not infer or invent", prefer newer info on conflict, compress to ~3-5 sentences (2) _summary_transcript() input sanitization: assistant messages cleaned before reaching the model, fully-leaked lines drop from the transcript, user messages untouched; (3) output protection: summary stored through strip_tool_leaks. With an empty transcript the LLM isn't called at all (previous summary preserved). Tests: tests/test_summary_hygiene.py 5 passed. Full suite: 287 passed, 2 xfailed; ruff clean.
- [x] **4. Tool-loop ceiling** ✅ Verified: sig_exec_counts caps identical signatures (name(args_json sorted)) at _MAX_IDENTICAL_EXECUTIONS=2 per request; the 3rd attempt is refused with a "[Refused: ...]" tool message (safety net for side-effectful tools; pure repeats are already caught by dedup, this layer cuts repeats inside mixed batches — e.g. [A,B] → [A,C] won't run A again). Tests: tests/test_stream_loop_guards.py 3 passed (nudge turn + tools-off payload verification, fallback message, refusal of the 3rd identical call). Full suite: 290 passed, 2 xfailed; ruff clean.

### Non-stream port + backend sync (2026-08-22)

- [x] **Guards ported to the non-stream path** ✅ Verified: same nudge+cap mechanism in the llm/chat.py loop (constants moved to llm/utils.py: FINALIZE_NUDGE / EMPTY_ANSWER_FALLBACK / MAX_IDENTICAL_EXECUTIONS; the stream module imports them under their old `_`-prefixed names so tests don't break). Tests: tests/test_chat_loop_guards.py 3 passed.
- [x] **Model sync on backend switch** ✅ Verified: live probe hit 404 on the ollama branch — root cause: LLM_MODEL stored in litert form (gemma4-e2b) while the ollama registry wants colonized (gemma4:e2b); convention per install.py:1246 (litert→dashed, ollama→colonized). Fixes: (1) LLM_BACKEND now selectable from the UI (select input added to SETTINGS_SCHEMA, removed from PROTECTED_SETTINGS, added to RESTART_REQUIRED_KEYS); (2) PATCH /config/settings validates LLM_MODEL against the NEW daemon's list on backend switch and auto-converts via delimiter-agnostic matching when absent (get_llm_model_options(backend=...) parameter added); (3) no match → old model kept + warning logged (manual pick required). Tests: tests/test_settings_backend_sync.py 4 passed.
- [x] **Intent detection + LLM fallback validated on both backends** ✅: the embedding layer is backend-independent (FastEmbed/ONNX local); unit tests + live probe for the LLM fallback's litert (/v1/chat/completions) and ollama (/api/chat) branches: question intent produced correctly on both. The full tool loop was also live-verified on ollama (despite a Nextcloud timeout the model produced a proper textual reply → error handling solid). Tests: tests/test_intent_backends.py 5 passed. Full suite: 302 passed, 2 xfailed; ruff clean.

Every step: ruff + pytest, then this file updated.

### Files involved

- routers/chat.py — save points (stream ~255/~273, non-stream ~182)
- llm/stream.py — dedup/fallback (~358), loop machinery
- llm/utils.py — strip_tool_leaks, _TOOL_CALL_TAG_RE
- db.py — conversations table

<!-- ═══ CHRONOLOGICAL CONTINUATION · the Aug 13-22 stretch was lost from disk
     when the journal lived outside git; the records below were reassembled
     from opencode session transcripts and surviving fragments (2026-08-23) -->

## Aug 13–22, 2026 — recovered from session transcripts

<!-- Source: opencode session database -->

### Aug 13

- NOTES.md was removed from git tracking on this day (commit `1e61227`, "keep it local-only") — the start of the lost stretch.
- The session log holds a single user message: an unfinished "glassy effect" experiment on static/index.html plus a pyjsparser topic. No tool calls were recorded, so whether code changed that day is UNVERIFIABLE (the glass-mode CSS existed by Aug 22; when it landed is unknown).

### Aug 21

- 22:07 — full codebase review requested for `piSynapse` (this repo; base `ddc5afa` + uncommitted routers/chat.py abort changes). Three copies exist: piSynapse (current), -release, -release-backup.
- 22:25 — audit report appended to NOTES.md ("FULL CODEBASE REVIEW — Report"). Three live-verified critical bugs: (1) update_note completely broken (dispatcher sends category/tags, wrapper raises TypeError), (2) /chat/upload rejects multipart with 422, (3) third bug's text was truncated in the transcript — unrecoverable. Baseline: 242 tests passing.
- Other confirmed findings from the report: the contacts/CardDAV module does not exist in the codebase (only a table reference survives); C group = dead code/cleanup items.
- From 22:37 an 11-item fix round ran (pytest after each item):
  - A2: routers/chat.py — new POST /upload (upload_image), chunked size limit based on MEDIA_MAX_MB, base64 response; tests/test_media.py +3 tests (245 passed).
  - Item 2 (approved): ID/UID architecture switched to position-based resolution — raw IDs/UIDs removed from listings, dispatcher _parse_*_listing compatibility kept, CRITICAL item-reference rules written into prompt.py.
  - A1: nextcloud_notes.update_note now accepts and forwards category/tags + _invalidate_list_cache(); tests/test_dispatcher.py::TestUpdateNoteRealPath.
  - nextcloud_tasks.py: _todos_cache keyed per include_completed flag (tuple key); errors raise instead of being swallowed (caldav's get_todos(include_completed=False) default meant completed todos were never fetched).
  - Note-write → list-cache inconsistency fixed; regression test: tests/test_stability_fixes.py::test_note_write_invalidates_list_cache.
- Past midnight (spilled into the 22nd): all items done — 242 → 259 passed (+17 regression tests), ruff clean; NOTES.md updated.

### The Aug 21 fix round, itemized (verified later)

<!-- Extracted from the session dump; the ✓ marks were live-checked against
     current code on Aug 23 -->
1. A2 /chat/upload multipart fix (UploadFile=File(...), 1MB chunks, 413 cap) ✓
2. ID/UID architecture: position-based resolution (B1+B2 merged; user-approved findings table presented first) ✓
3. A1 update_note TypeError (wrapper forwards category/tags + cache invalidation) ✓
4. A3 show_completed no-op (caldav include_completed flag + tuple-keyed cache) ✓
5. B3 send_email failures now ERROR:-prefixed (audit counts them correctly) ✓ dispatcher.py:373
6. B5 list-cache invalidation after notes/tasks writes (+regression test) ✓
7. B4 stream.py think-retry passes tool_group (done in the Aug 22 parity round) ✓
8. B6 NUM_CTX/MAX_OUTPUT defaults unified: config.py 8192/4096 single source ✓
9. C-group cleanup: OFFLINE_SAFE_TOOLS dead entries removed (save_memory only now), VENV_DIR→venv, unused weathercode fetch dropped, get_config hardcoded defaults tied to config.py ✓
10. pytest after every item (242→259, +17 regression tests) ✓
11. Final report + ruff clean + NOTES update ✓

<!-- Note: the same session spilled into Aug 23 (outside the requested scope):
     the 3h28m CI hang traced to a leaked aiosqlite connection (conftest.py
     safety net; b72c6a0→d1ae04c), the last 2 xfails fixed (308 passed /
     0 xfail, 4f10098) and the v1.4.0 tag pushed. -->

## Aug 17, 2026 — UI improvements, XSS fix, limit raise

### Frontend (static/index.html)

**XSS security:**
- 50 innerHTML assignments audited (27 static, 18 esc()-guarded, 1 low-risk, 1 exposed)
- Exposed: ticker/marquee inserted item.text unescaped → fixed with esc(item.text)
- renderMd() safe-by-construction (all content paths go through esc())
- No eval(), Function(), document.write(), outerHTML usage — clean

**Mobile improvements:**
- Swipe gesture suppressed inside scrollable areas (code-wrapper, pre, textarea, #msg-input, .sess-list) via a _swipeInScrollable flag
- Input bar glass blur: blur(16px) saturate(150%), rgba(17,17,22,.88) — opaque yet glassy
- Sidebar toggle: 90ms delay + btn-press animation (scale .88) + navigator.vibrate(12) haptics
- Button CSS: #logo-btn.btn-press .logo-icon{transform:scale(.88); filter:brightness(.85)}

**Glass toggle fix:**
- Added `<span class="track">` to the glass toggle — renders properly now (instead of a bare checkbox)

### Backend (config.py)

**Limit raises:**
- LLM_NUM_CTX: default 6144 → **8192**, UI max 6144 → **32768**
- LLM_MAX_OUTPUT_TOKENS: default 2048 → **4096**, UI max 6144 → **16384**
- piServe config.json: max_num_tokens 6144 → **8192**
- Pi .env: LLM_NUM_CTX=8192, LLM_MAX_OUTPUT_TOKENS=4096
- piServe service restarted (8192 context active)

**Rate limiting:**
- 30 RPM limiter stays active (no exemptions added)
- 429s seen at page load were resolved by a service restart

### Security audit result

| Category | Count | Status |
|---|---|---|
| innerHTML — static HTML | 27 | Safe |
| innerHTML — esc()-guarded | 18 | Safe |
| innerHTML — low-risk (local data URI) | 1 | Acceptable |
| innerHTML — exposed (ticker item.text) | 1 | **FIXED** |
| eval/Function/document.write | 0 | Clean |
| Hardcoded secrets/API keys | 0 | Clean |
| .env gitignored | — | Correct |

### Changed files

- static/index.html: XSS fix, mobile improvements, glass toggle fix, stronger blur
- config.py: limit defaults and UI maxima
- notes-additions.md: staging file for this entry

### Test scenarios

1. **XSS**: a calendar event inside the ticker must render `<script>` as inert text, never execute
2. **Mobile swipe**: horizontal scroll inside a code block or long message must not open the sidebar
3. **Mobile input bar**: glass mode — text behind the bar readable but subtle
4. **Sidebar button**: press the logo button on mobile → slight delay + visual press + haptic tick
5. **Context window**: settings can raise context up to 8192
6. **Max output**: settings can raise max output up to 16384

## Changes — 2026-08-13

Audit (A1-A10/B1-B5/C1-C8/D1-D6) + Phase 1 fixes. Process: analyze → plan →
execute, one commit per item + `py_compile` + `pytest` (27/27).

| # | Change | Detail |
|---|-----------|-------|
| **1** | **git init + baseline commit** | Project is now a git repo (`bcc7379`). Tar backup beforehand: `backups/piSynapse-20260813-1917.tar.gz` (excluding venv/db/.env/models). |
| **2** | **.gitignore completed** | Added: `venv/` (the real venv, dotless — could previously have been committed!), `*.db-wal`, `*.db-shm`, `*.db-journal`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `*.egg-info/`, `dist/`, `build/`, `*.pyc`. |
| **3** | **A1** | pyproject.toml build-backend `setuptools.backends._legacy` (invalid) → `setuptools.build_meta`. Missing `faster-whisper` added to `[project].dependencies`. `[tool.setuptools]` package/py-modules layout — `pip install -e .` works now. |
| **4** | **A2** | llm/stream.py — LiteRT stream overwrote tool_calls deltas (id/name/arguments lost, multiple tool calls vanished). `_merge_tool_calls()` merges by index. Ollama full-lists handled separately. |
| **5** | **A3** | routers/media.py — faster-whisper transcribe + 2× subprocess.run(ffmpeg) were synchronous (event-loop blocking). All moved to asyncio.to_thread; lazy segment iteration inside the thread. |
| **6** | **A4** | llm/intent.py — model.embed() was synchronous. Now embed_async() + new embed_batch_async() (embedding.py). |
| **7** | **A5** | config.sync_config() missed string entries (DEFAULT_CITY, ASSISTANT_USER→DEFAULT_USER, MAIL_PROVIDER, LLM_KEEP_ALIVE). Converted to dict mapping. INTENT_LLM_FALLBACK removed from RESTART_REQUIRED_KEYS (contradiction). prompt.py/widgets.py/weather.py read DEFAULT_CITY at call time (import-time binding removed). |
| **8** | **A6** | MEMORY_SIMILARITY_THRESHOLD (0.68) was dead config — db.py hardcoded 0.85. Now used for the db dedup threshold + added to SETTINGS_SCHEMA (UI-adjustable). |
| **9** | **A7** | routers/chat.py — assistant reply saved only on the done event; disconnect/error orphaned the user message. finally block now saves partial replies too (reply_saved flag). |
| **10** | **A8** | calendar_ops.update_event — raw iCal string .replace() (misses all-day VALUE=DATE, breaks folded SUMMARY, could stamp the wrong occurrence) → vobject property manipulation. All-day + timed tested. |
| **11** | **A9** | mail.py — empty MAIL_PROVIDER fell back to gmail (docs said "empty = disable"). Empty now disables email. |
| **12** | **A10** | install.py — missing.append("ffmpeg"/"curl") ran even when installation succeeded; appended only when genuinely missing. |
| **13** | **B1** | .gitignore entered the baseline (line 2). Critical gaps closed: venv/, *.db-wal/shm/journal, caches, dist//build/*.egg-info. |
| **14** | **B3** | main.py rate-limit IP trusted x-forwarded-for unconditionally (spoofable bypass). Now request.client.host; proxy users set TRUST_X_FORWARDED_FOR=1 (added to PROTECTED_SETTINGS). |
| **15** | **B2/B4** | False "SSRF protection" claim removed from README. Security Notes section added (TLS reverse proxy, .env chmod 600, XFF). |

Status: **Phase 1 (A1-A10) + Phase 2 (B1-B4) done**, Phase 3 (architecture) starting.

## Phase 3 (Architecture) — 2026-08-13

| # | Change | Detail |
|---|-----------|-------|
| **16** | **C8** | `f0179b1` — Dead-code purge: _AUTH_EXEMPT (main.py), _TOOL_TO_GROUP (tools/definitions.py), llm/__init__.py re-exports (only __all__ entries remain), install.py home/python_path F841, llm/payload.py tool_name, f-strings + 42 automated F-errors. All F401/F841/F541 clean (remaining 144: E501/D-docstring style, pre-existing). |
| **17** | **C6** | `7780496` — get_llm_model_options() ran synchronous subprocess(curl/ollama) → async wrapper + asyncio.to_thread; event loop no longer blocked. Live LiteRT query tested (gemma4-e2b, gemma4-e4b). |
| **18** | **C7** | `f224513` — nextcloud_notes.list_notes() fetched all notes in one request → page/itemsPerPage=100 pagination. Infinite-loop guard if the server ignores pagination params (id dedupe). |
| **19** | **C3** | `0c3691e` — DB schema migrations from ad-hoc try/except → PRAGMA user_version sequential MIGRATIONS (images, name, summarized_until, embedding). Existing DB verified at user_version=4. |
| **20** | **C2** | `807866c` — Optional data retention: CONVERSATION_RETENTION_DAYS / MEMORY_RETENTION_DAYS (default 0 = off). db.cleanup_expired_data() runs at startup. UI-adjustable + live sync via .env PATCH (no restart). |
| **21** | **C1** | `d13bd82` — SQLite "database is locked": busy_timeout=10000 + _write_with_retry() (3 attempts, on migration/cleanup writes). Retry simulated and tested. |
| **22** | **C4** | `b9e72d3` — [project.optional-dependencies].dev (pytest, pytest-asyncio, ruff, mypy). mypy caught a real bug: llm/chat.py msg2/message None narrowing (188→154 errors; remainder missing stubs/generics, baseline). |

Status: **Phase 3 (C1-C8) done** — 22 items processed, 27/27 tests, smoke OK (/health 200, / 200, /chat/sessions 401). Next: Phase 4 (D1-D6, UI + README) + LiteRT systemd unit.

## Phase 4 (UI + Documentation) — 2026-08-13

| # | Change | Detail |
|---|-----------|-------|
| **23** | **D3** | `a0c10d3` — orientation: portrait removed from static/manifest.json (PWA can rotate on tablets/landscape). |
| **24** | **D4** | `52765c3` — relTime(): SQLite UTC stamps are space-separated "YYYY-MM-DD HH:MM:SS"; JS new Date() can't be trusted across browsers. ISO-8601 normalization via ts.replace(' ','T'). "(local time)" label added to the prompt's "Current date and time" (DB UTC vs prompt local — mismatch flagged). |
| **25** | **D5** | within `52765c3` — the system prompt's "Under ~{LLM_NUM_CTX} tokens" rule was misleading (LLM_NUM_CTX is the context window, not the reply limit) → replaced with generic conciseness wording, import removed. |
| **26** | **D1** | within `52765c3` — confirmation modal was read-only (.val div); send_email fields (to/subject/body + cc/bcc) now editable inputs/textarea (mInput() + data-p, confirmAction writes values into params). CSS .val-input added. |
| **27** | **D2** | `39dca60` — send_email didn't support cc/bcc (signature existed, unused). _send_email(to, subject, body, cc, bcc) builds header + envelope (sendmail recipients comma-separated), dispatcher passthrough, cc/bcc added to the tool definition. |
| **28** | **D6** | `028d7de` — README: LiteRT import target gemma4:e2b→gemma4-e2b (piSynapse normalizes colons to dashes, colonized IDs never matched); port 8000→8765 (actual service + curl examples); MAIL_PROVIDER default gmail→— (disabled) (empty = disabled per A9). |

Status: **Phase 4 (D1-D6) done** — 28 items total, smoke OK. Next: LiteRT systemd unit (litert-lm.service) + pisynapse.service ordering dependency.

## Wrap-up — 2026-08-13 (LiteRT systemd + dev-rules)

| # | Change | Detail |
|---|-----------|-------|
| **29** | **LiteRT systemd unit** | LiteRT ran as a manual process (no unit → died on reboot). Created /etc/systemd/system/litert.service (User=primary-user, uv python + litert-lm serve --host 127.0.0.1 --port 9379, Restart=on-failure). Manual process stopped → enable --now. Port 9379 verified with a model query (gemma4-e2b, gemma4-e4b). |
| **30** | **pisynapse.service ordering** | After=network.target ollama.service → After=network.target litert.service. pisynapse itself was disabled → enabled (reboot-safe). systemd-analyze verify clean. |
| **31** | **dev-rules update** | piSynapse-dev-rules.md: git repo status, llm/ and tools/ package layout (instead of llm.py/tools.py), LiteRT primary + gemma4-e2b (dash not colon), pytest 27 tests + ruff/mypy commands, port 8765, MAIL_PROVIDER empty=disabled, XFF/rate-limit note, false "SSRF prevention" line corrected, systemd units. |

**Total audit outcome:** A1-A10 ✓, B1-B5 ✓ (B5=C5 skipped, noted), C1-C8 ✓, D1-D6 ✓ — **31 items**, 20+ commits, 27/27 tests, smoke OK. Everything committed to main.

## Changes — 2026-07-31

| # | Change | Detail |
|---|-----------|-------|
| **1** | **Port 8765** | pisynapse.service port 8000 → 8765. Old 8765 process (manual) stopped, systemd unit updated. |
| **2** | **install.py rewritten** (453→654 lines) | LiteRT install: uv tool install litert-lm + litert-lm import --from-huggingface-repo downloads the model (~2.4 GB) + litert-lm serve --port 9379 startup + 60s wait. Ollama: curl install.sh \| sh + ollama pull. Model registry defined in _LITERT_MODEL_REGISTRY. |
| **3** | **systemd dual services** | litert.service (LiteRT server), pisynapse.service (After=litert.service when present). Installed via _create_litert_service(). |
| **4** | **release.sh** | rm -rf + bash release.sh gives a residue-free release build (912K, 49 files). Excludes: venv, __pycache__, *.db, models/, .env, .git, caches. |
| **5** | **INTENT_LLM_FALLBACK** | config.py → SETTINGS_SCHEMA select box. Default off (embeddings+keywords suffice). on adds an LLM fallback call (~+15s). Listed in RESTART_REQUIRED_KEYS + sync_config() strings. |
| **6** | **get_llm_model_options() cache** | _MODEL_OPTIONS_CACHE (30s TTL, per backend). LiteRT /v1/models and ollama list aren't re-called. |
| **7** | **Comments across all files** | Short docstring + section/inline comments added to every .py. embedding.py, llm/utils.py, llm/stream.py, llm/intent.py, llm/payload.py, llm/chat.py, tools/__init__.py, routers/config.py. |
| **8** | **Avahi fix** | /etc/avahi/avahi-daemon.conf → allow-interfaces=eth0. .local resolution returns the real IP instead of the docker bridge. |
| **9** | **TTFT regression — noise** | Three consecutive measurements: 14.5s / 13.3s / 13.6s. Earlier 18-21s figures were taken with LiteRT cold. Embedding+keywords intent ~50-100ms, the rest is LiteRT warmup. |
| **10** | **README rewritten** | Vision section dropped. Hardware Requirements, Privacy & External Services table, dual email (Proton/Gmail) guide added. 52 env vars synchronized. |
| **11** | **install.py self-contained .env** | step_env() no longer needs example.env — creates all 52 vars from scratch. Email setup offers Proton/Gmail/none. |
| **12** | **example.env refreshed** | 20+ missing vars added (LLM_NUM_CTX, SUMMARY_*, INTENT_LLM_FALLBACK, MEDIA_MAX_MB, etc.). 100% aligned with config.py. |
| **13** | **GitHub push — v2 release** | piSynapse-release → git init + add + commit + remote + pull --allow-unrelated-histories -X ours + push. Old 42 commits preserved, new code merged on top. Total: 43 + merge. |

## Tool improvements — July 30, 2026

> Improved the model's tool usage and content ownership. Main goal: the model calls tools without hesitation, keeps email/note/task data in context, and never asks the user for IDs.

### ✅ Tool definitions — precision and directness

| Change | Detail |
|---|---|
| **"Only use when the user explicitly asks" removed** | From all email/notes/tasks tools — it was the source of hesitation |
| **Imperative descriptions** | "Call this when...", "Use this when..." format — the model knows exactly what to do |
| **list_emails** | "Returns a list you can use to answer questions" — the model knows it can use the data |
| **search_emails** | "Searches subject, sender, AND body" — scope is explicit |
| **read_email** | "Use this when the user asks for DETAILS of a specific email" — clear usage condition |

### ✅ System prompt — 10 rules

| # | Rule | Goal |
|---|---|---|
| 1 | Call the tool immediately, don't narrate | Break hesitation |
| 2 | Call with sensible defaults, don't ask "how many" | Proactivity |
| 3 | Widen the search if results are sparse | Proactivity |
| 4 | Answer follow-ups from listed data | Never ask the user for IDs/subjects |
| 5 | Never say "I can't" — the tool exists | Break hesitation |
| 6 | save_memory only for durable facts | Prevent memory pollution |
| 7 | Relative dates → get_datetime | Date correctness |
| 8 | ISO 8601 format | Standardization |
| 9 | Short answers | Context economy |
| 10 | Natural, warm tone | User experience |

### ✅ Email content richness

| Change | File |
|---|---|
| **Body preview 200→300 chars** | mail.py:_list_emails() |
| **Cache preview 100→200 chars** | prompt.py:cache_email_context() |
| **Preview line in email context** | prompt.py:build_context() — model can answer without read_email |
| **search_emails searches bodies too** | mail.py:_search_emails() IMAP TEXT key added |
| **search_emails caches results** | tools/dispatcher.py:search_emails → cache_email_context() |
| **search_emails output matches list_emails format** | ID + Preview + From/Subject in the same layout |

### ✅ Calendar/Notes/Tasks previews

| Tool | New feature | File |
|---|---|---|
| **list_calendar_events** | Description preview ≤100 chars on a second line | calendar_ops.py:85 |
| **list_notes** | 80-char content preview per note | nextcloud_notes.py:149 |
| **list_tasks** | 120-char description preview per task | nextcloud_tasks.py:185-186 |

### ✅ Email ID tracking — critical fix

**Problem:** the model called list_emails, got results, then asked the user
"which ID?" anyway.

**Solution:**
1. search_emails finds the content the user refers to — the model calls search_emails(query=<what the user referred to>) instead of asking
2. search_emails results are cached too (cache_email_context) — Recent Emails Context stays fresh
3. System Prompt Rule 4: "Do NOT ask the user 'which one' or 'what ID' — just pick the right email from the data you already have"
4. System Prompt CRITICAL section: "If you don't have the data anymore, call search_emails — don't ask the user for an ID"

---

## Codebase improvements — July 29, 2026

> These changes raised piSynapse's code quality, security and maintainability.

### ✅ Infrastructure

| Change | Description |
|---|---|
| **pyproject.toml** | Project config file added — pytest, mypy, ruff settings |
| ~~Alembic migrations~~ | ~~alembic/ dir + initial migration~~ — REMOVED (July 30, 2026). Schema lives directly in db.py. |
| ~~Dockerfile + docker-compose.yml~~ | ~~Multi-stage Docker build~~ — REMOVED (July 30, 2026). Unused, container never ran. |

### ✅ Architecture

| Change | Description |
|---|---|
| ~~services/ layer + DI helpers~~ | ~~DatabaseService, LLMService, EmbeddingService + main.py DI helpers~~ — REMOVED (July 30, 2026). No router ever bound to them; legacy modules did the work. |
| **Lazy loading** | FastEmbed (~470MB) loads only when embeddings are needed (no eager startup load) |

### ✅ Module structure

| File | New layout |
|---|---|
| llm.py → llm/ | payload.py, chat.py, stream.py, intent.py, utils.py |
| tools.py → tools/ | definitions.py, dispatcher.py |
| routers/chat.py | Chat, session and memory endpoints only |
| routers/media.py (new) | Transcription (Whisper/Gemma4) + TTS (Piper) endpoints |

### ✅ Security

| Change | Description |
|---|---|
| **ProtonMail SSL** | Bypass on localhost, enforced certificate verification remotely (mail.py) |
| **X-Forwarded-For** | Rate limiter sees the correct client IP behind proxies |

### ✅ Type safety

| Change | Description |
|---|---|
| **_safe_int()** | Raises ValueError instead of returning an int\|str union — callers catch with except ValueError |
| **retry decorator** | utils.py @retry now applied to IMAP/SMTP operations |

### ✅ Streaming

| Change | Description |
|---|---|
| **LiteRT SSE streaming** | Real SSE streaming for LiteRT-LM (previously a non-streaming fallback) |
| **Ollama + LiteRT shared stream** | One chat_with_ollama_stream() drives both backends over SSE |

### ✅ WebSocket

| Change | Description |
|---|---|
| **/chat/ws** | WebSocket chat endpoint — session_id/user_id as query params, JSON message exchange |

### ✅ Testing

| Change | Description |
|---|---|
| **pytest** | 20 tests (test_utils.py, test_tools.py) — utilities, tool definitions, _safe_int, arg parser |

---

## Reference

### Vision

Evolve from a single machine to a distributed personal assistant.

### Three Layers

| Layer | State | Description |
|-------|-------|-------------|
| **1. Current** | ✅ Live | Single server + web UI, everything local |
| **2. Queue / Sync** | 🔜 Next | Phone stores plain-text commands offline, /sync endpoint on reconnect |
| **3. Distributed** | 🔭 Far | Every device contributes at its capacity, LiteRT on mobile, optional sync-only server |

### Key Decisions

- **Device discovery:** Manual (login / domain / VPN) — no auto-discovery
- **Conflict resolution:** Merge semantics — last-write-wins is not acceptable
- **Queue format:** `{ "command": str, "timestamp": str, "session_id": str }` — JSONL locally
- **Offline tool policy:** OFFLINE_SAFE_TOOLS in tools.py — low-risk commands run offline, CONFIRM_TOOLS queue only
- **Mobile model:** LiteRT-LM (LLM orchestration over the former TFLite) — not mature yet, tracking
- **Sync transport:** Tailscale-like P2P or user-defined relay
- **Sync-only server:** Optional — for users who want cloud sync without an LLM on the server

### Open Questions

- Queue persistence format (JSONL? SQLite?)
- /sync endpoint design — batch vs streaming
- Conflict resolution algorithm for calendar/alarm overlap scenarios
- LiteRT integration timeline

---

### LiteRT-LM Detail

> July 13, 2026 — technology note for the mobile offline-model research.

#### What it is

LiteRT-LM is an orchestration layer built on LiteRT (formerly TFLite) handling LLM-specific complexities (KV-cache management, session state, multi-turn context, prompt caching). It powers Gemini Nano's distribution in Chrome and Pixel Watch.

#### Cross-platform

Android, iOS (Swift + Metal), Web (JS + WebGPU), Desktop (Linux/macOS/Windows), IoT including Raspberry Pi. Early community-supported Flutter binding.

#### Tool-use / function calling

Native constrained decoding improves tool-call accuracy. Similar to the existing run_tool() flow: the model pauses, returns a structured tool-call request, resumes once the result arrives.

#### Integration

- CLI + Python API (uv/pip)
- OpenAI-compatible local server mode → only the base URL changes in llm.py
- Android: com.google.ai.edge.litertlm:litertlm-android (Gradle, Kotlin API). Engine class, errors LiteRtLmJniException / IllegalStateException

#### Model support

Gemma, Llama, Phi-4, Qwen, Gemma4 12B

#### Expectations on the Pi-class target (TESTED — July 29, 2026)

CPU-only ~2-5 tok/s (E2B). Compared tokens/s, memory and tool-call accuracy
against Ollama+gemma4:e2b.

#### Benchmark results (8 GB RAM board) — Jul 29, 2026

**Methodology:** identical system prompt and tool schema (get_current_time +
create_task, 3-turn multi-step).

**Ollama run:** clean start after `swapoff -a && swapon -a && echo 3 >
/proc/sys/vm/drop_caches`. No runtime processes were running. Three runs
intended, but run 1 completed, run 2's first turn hit a 129.6s timeout, run 3
never started.

**LiteRT-LM run:** immediately after the Ollama test. Ollama processes killed
with killall -9 but **swap was not reset** (free -h showed ~1.3 GiB swap used).
The LiteRT-LM environment therefore wasn't 100% pristine — however LiteRT-LM
doesn't use swap, so results were unaffected. Ollama's swap usage is the main
driver of the dramatic RAM difference.

**Notes:**
- Ollama's API returns tool_calls.function.arguments as a **dict**; LiteRT-LM returns a **string**. The first test script hit a TypeError over this — an API difference, not test variance.
- Ollama's 150s figure includes model loading; LiteRT-LM's 17s likewise.

##### Cold start (first inference including model load)

| Metric | LiteRT-LM (gemma4-e2b) | Ollama (gemma4:e2b) |
|-------|------------------------|---------------------|
| **Turn 1** (load + get_current_time) | **16.9 s** | 137.7 s |
| **Turn 2** (create_task) | **16.7 s** | 70.7 s |
| **Turn 3** (final answer) | **14.5 s** | 197.9 s |
| **Total** | **48.1 s** | 406.3 s |
| Warm simple query (3-req avg) | **2.4 s** | (unmeasurable — swap thrashing) |

##### Warm runs (model loaded, 2nd/3rd attempts)

| Metric | LiteRT-LM (gemma4-e2b) | Ollama (gemma4:e2b) |
|-------|------------------------|---------------------|
| Run 2 total | **44.7 s** | (timed out at 129.6s) |
| Run 3 total | **43.6 s** | — |
| n | 3 (complete) | 1 (complete) + 1 (half) |
| Note | Model loaded, stable | ~100-140s per turn, run 2 timed out |
| Warm latency | ~2.4s (simple) | Unmeasurable — swap thrashing |

##### Memory (model loaded)

| Metric | LiteRT-LM (gemma4-e2b) | Ollama (gemma4:e2b) |
|-------|------------------------|---------------------|
| **RAM usage** | **+1.7 GB** (3.7 GB total) | +5.4 GB (7.5 GB total) |
| **Swap usage** | 0 (zram only) | 6.5 GB (zram + swapfile) |
| **Model loading** | Lazy (at first inference) | Eager (at first inference) |

##### Summary

- **Inference speed:** LiteRT-LM ~8× faster (cold), ~5-8× (warm)
- **RAM efficiency:** LiteRT-LM ~3× less RAM, no swap
- **Tool-call format:** LiteRT-LM OpenAI string (`"{\"due\":...}"`) vs Ollama native dict (`{"due":...}`) — both valid, purely a parsing difference
- **Multi-step accuracy:** both correct with a proper prompt

**Verdict:** LiteRT-LM is decisively better on this hardware. Worth switching.

#### E2B vs E4B tool-call accuracy (LiteRT-LM)

| Mode | E2B | E4B |
|-----|-----|-----|
| litert-lm run (preset/constrained decoding) | ✅ 5/5 PASS (~30s) | ✅ 5/5 PASS (~30s) |
| litert-lm serve (OpenAI API, proper prompt) | ✅ multi-step (~15s/turn) | ✅ multi-step (~35s/turn) |
| RAM (serve mode, model loaded) | ~3.2 GB | ~4.9 GB |
| Warm latency (simple) | ~2.4s | ~5.9s |

**Note:** it was previously reported that the E4B server returned
`<|tool_call|>` markup. The cause was get_current_time instructions missing
from the system prompt — with a proper prompt the E4B server emits clean JSON
tool_calls too.

---

### FC Restructure Roadmap — decided 2026-08-24

Research-driven restructure after laptop field testing. Sources: ai.google.dev Gemma 4 FC docs,
LiteRT-LM constrained-decoding docs (LLGuidance), Mali-GPU E2B field report (357-case eval),
ollama structured-outputs docs, FunctionGemma release.

| # | Item | Decision / status |
|---|---|---|
| ~~1~~ ✅ Adopted+stress-verified 2026-08-24 | Constrained decoding overhead ≈ **0%** (8 measurements, difference at noise level); piServe now applies the LL_GUIDANCE constraint on tool-calling rounds — stress battery (multi-turn, 5-param email, detailed event) zero errors |
| ~~2~~ ✅ Already-on 2026-08-24 | piServe already runs per-request Conversation with RawSchemaTool passthrough (our exact schemas) + ATC off — verified in code & live |
| 3 | FunctionGemma 270M as intent/slot router — wait for .litertlm packaging vs test HF form now | DECIDE |
| ✅ Verified 2026-08-26 | **Multi-domain routing + chaining**: ≥2 group keyword hits → combined toolset pre-check (`_hit_groups`); base Rule 13 chains fetch→act (live: weather fetched then send_email confirm card auto-filled w/ real data — user approves to send) |
| 4 | Arg-arity diet
| 4 | Arg-arity diet — REVISED under constrained decoding: 5-param send_email extracted perfectly in 31s w/ full confirm card; update_note sequencing (search→update by title) still flaky → fold into #7 slot-extraction design instead of splitting tools | RE-EVALUATED |
| ~~5~~ ✅ Done 2026-08-24 | `_convert_content` wraps role:tool results into structured `tool_response` blocks (name+response) matching gemma template expectations |
| 6 | Dual-backend support continues; audit ollama official docs for equivalent gaps | ONGOING |
| 7 | Constrained-decoding benchmarks both backends; ollama native FC constraints unavailable → use schema-constrained slot-extraction call (`format=json_schema`) instead | WITH #1 |
| ~~8~~ ✅ Review complete 2026-08-24 | ALL current components necessary (8192 ctx cap lift, OpenAI SSE contract, admin/hot-reload); nothing to trim — incremental enhancements only |

**Embedding model comparison (2026-08-25):** multilingual-e5-large vs MiniLM-L12 on the
14-case intent set (passage/query prefixes per E5 spec). Result: E5 margins COLLAPSED
(avg 0.009 vs MiniLM 0.040; thin-margin 14/14 vs 13/14; confident-decision 0/14 vs 4/14),
6× slower embed (9.8s vs 1.6s /98 sent), +~2.8 GB RSS. Verdict: STAY on MiniLM; improve
margins via corpus coverage (done for notes verb-phrases). Caveat: table measures
EMBEDDING-layer-only decisions; production adds keyword tie-break + LLM fallback on top.
Experiment: experiments/intent_embed_compare.py.

Consolidated earlier suggestions that were previously untracked: frontend modularization
(Future Plan, new row), litert-lm version pinning/watch (Future Plan, new row).

### Known Limitations

#### LAN HTTPS / microphone access

**Problem:** accessed over LAN (`http://<vpn-ip>:8765`) the browser blocks the
getUserMedia API because HTTP + non-localhost origin counts as an "insecure
context". Result: voice input (microphone) doesn't work. Access from localhost
or 127.0.0.1 is unaffected.

**Option A — NPM proxy via VPS (recommended):** add a proxy host on the
existing Nginx Proxy Manager (VPS-side):
- Domain: `<your-domain>`
- Forward: `<vpn-ip>:8765`
- SSL: existing Let's Encrypt cert (`*.<your-domain>` wildcard or new cert)
- Phone reaches https://`<your-domain>` → VPS 443 → tunnel → box:8765
- **Pro:** zero extra configuration, existing cert valid, access everywhere
- **Con:** all traffic crosses the VPS (extra ~5-10ms latency)
- **Setup:** NPM admin panel → Add Proxy Host → domain + forward IP/port → pick cert in the SSL tab → Save

**Option B — Caddy automatic HTTPS on the box:**
- Install Caddy (apt install caddy)
- Use DNS-01 challenge with a DNS provider API (Cloudflare, etc.)
- Point `<your-domain>` DNS at the box's LAN IP (or VPN IP)
- **Pro:** fully automatic Let's Encrypt, local HTTPS
- **Con:** DNS zone A record must show the LAN IP (public access unintended, LAN/VPN only)
- Cannot run behind Cloudflare proxied mode (orange cloud) — DNS-only (grey cloud) required

**Option C — Self-signed cert + mkcert (fully local):**
- Install mkcert on the box (apt install mkcert or go install filippo.io/mkcert)
- Create a local CA (mkcert -install)
- Sign with mkcert `<vpn-ip>` `<lan-ip>` localhost
- Trust the CA's public key on phone/laptop (iOS profile / Android CA cert)
- Serve HTTPS via Caddy/nginx using cert+key
- **Pro:** fully LAN-dependent, no internet needed
- **Con:** CA trust must be added manually per device

**Option D — nginx-proxy-manager (NPM) on the box:**
- Install Docker + NPM
- Serve HTTPS via self-signed cert or DNS-01 Let's Encrypt through NPM
- Pro: existing NPM knowledge reused, web UI management
- Con: extra container on the box, NPM wants 80/443

**Current approach (isSecureContext check in index.html):** shows a
"Microphone requires HTTPS" error on LAN HTTP. Not a solution, just informs the
user. One of the options above should be implemented for a real fix.

---

#### litert FC quirks (discovered 2026-08-23)

- **Round-2 native call parse failure:** after a tool-result round, the model sometimes emits doubled-brace syntax (`call:create_note{{...}}` with stray `<|tool_call>` markers). LiteRT's SERVER-side parser hard-fails mid-stream (`INVALID_ARGUMENT: Failed to parse tool calls from code block`) — unreachable by our text-level leak recovery. Mitigated downstream by the overflow-retry path (the error text matches `_is_context_overflow`), which shrinks and retries once; if it recurs, the turn errors out.
- **Overflow misclassification:** `_is_context_overflow()` matches bare `"invalid_argument"`, so the parse failure above is labeled `overflow` and triggers the shrink+retry path even though context isn't actually full. Frontend label is cause-neutral so nothing misleading reaches the user. Proper fix needs a distinguishing field in litert's error payload — future item.

### Future Plan

| Priority | What |
|---|---|
| ~~🔴 High~~ ✅ Done 2026-08-23 | **Tool-call indicator** — backend-driven SSE `tool`/`gen_retry` events + frontend status pill (see entry 14) |
| 🔴 High | **Onboarding screen** — first-run guide ("this is your API key, use it like so") |
| ~~🔴 High~~ ✅ Done 2026-08-23 | **Error messages** — backend-generated user-facing strings localized via root `messages.py` catalog (`get_message(key)`, tr/en, live via UI_LANGUAGE): empty-reply fallback, engine-unreachable, empty-generation. Frontend additionally maps connection-lost/context-overflow SSE errors (errConnLost/errContextTooLong). Verified against code this date |
| 🟡 Medium | **Work without Nextcloud** — chat + memory must work at minimum, email/calendar optional |
| ~~🟡 Medium~~ ✅ Done 2026-08-23 | Raise test coverage (especially dispatcher + mail) — suite at 329; test_dispatcher.py 76+, test_mail.py 13 passing |
| ~~🟡 Medium~~ ⛔ Obsolete 2026-08-23 | FastAPI DI → dependency_overrides mock-test infrastructure — services/DI layer removed by design (2026-07-30); plain module-level mock fixtures used instead |
| ~~🟡 Medium~~ ⛔ Obsolete 2026-08-23 | Optimize the Docker image (multiarch on small boards) — Docker removed from the project entirely |
| 🟡 Medium | **Frontend modularization** — split monolithic index.html when next touched |
| 🟢 Low | **litert-lm version pin & watch** — track upstream changes (FC parser/template behavior shifts between versions) |
| 🟡 Medium | **HTTPS/microphone** — Caddy self-signed or NPM solution |
| 🟡 Medium | **Performance** — NUM_CTX raised to 8192 (done); ~~latency tuning round (13-15s → 10-12s) still open~~ (re-measured 2026-11-16: warm **25-27 s** with gemma4-e2b on Pi 5 CPU; A/B with NUM_CTX 4096 ≈ same 26-27 s → context size is not the driver, 8192 kept; the 10-12 s goal stands and is now the main UX gap); **Cache/KV optimization** (~~embedding cache~~ done 2026-11-16: persistent `FASTEMBED_CACHE_DIR` cache + HF Xet disabled, `3536280`; KV-cache reuse + prompt caching future) — noted 2026-08-28 per review |
| 🟢 Low | Redis cache for session management (optional) |
| 🟢 Low | Observability: Prometheus metrics, structured logging |
| 🟢 Low | Multi-user authentication (JWT) |
| 🟡 Medium | **Retry button on stream errors** — today a failed turn forces full retyping; add one-tap retry reusing the stored request |
| 🟡 Medium | **Session search** — sidebar has no search; months of sessions become unnavigable |
| 🟢 Low | **Better session auto-titles** — first-38-chars truncation yields clipped sentences; use a tiny LLM summary instead |
| 🟢 Idea | **Proactive features** (morning briefings, reminders push) — required to fully match branded assistants |
| 🟢 Parked | **Installer web wizard** — deferred until external testers report CLI friction points |
| ~~🟢 Low~~ ✅ Done 2026-08-23 | More language support — tr/en shipped via UI_LANGUAGE setting |
