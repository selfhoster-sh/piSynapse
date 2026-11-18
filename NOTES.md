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
- **Determinism rule (user, 2026-11-16):** every test that depends on time, money, the filesystem or randomness either freezes the clock (time-machine, now a dev dependency) or generates relative times. Absolute date literals are banned in test code (migration fixtures exempt). At the end of each pack the suite runs once more in a clean checkout. Clock-dependent app paths (calendar_ops list_events_today, prompt injection of now, dispatcher "Current:") are tested with a frozen clock so the output is reproducible.

## Navigation (added 2026-11-16, R7)

- **Rules (READ FIRST):** lines 5-22 above.
- **Recent chronology:** 2026-11-16 → 2026-09-01 (lines 24-1097).
- **Archived chronology:** 2026-08-31 → 2026-08-22 moved to `docs/journal-archive.md` (nothing deleted).
- **Reference material:** FC Restructure Roadmap, Known Limitations, Future Plan (bottom).

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

- **Solution #1 tested (2026-11-16, evening):** counter-based recovery (cap 5) deployed and tested. Result: **full success**. Turkish diacritics multi-fact request (5 facts) → memories_saved: 5, 4 recoveries logged, no errors, no cap exhaustion. Single-fact Turkish requests also succeed. The prompt hint (solution #3) did NOT prevent doubled-brace emission — the model still emits `{{...}}` for every fact — but the counter handles all of them. Recovery is now reliable; the user-facing error message is only shown if 5+ parse failures occur in a single turn (very unlikely).
- **Conclusion:** solution #1 (counter-based recovery) is the **effective fix** for the LiteRT parser issue. Solution #3 (prompt hint) is ineffective but harmless. Solutions #4-#8 remain as future improvements (upgrade, client-side parsing, etc.) but are no longer urgent. The "teach me" experiment now works with Turkish content (slowly — 5 facts ≈ 55 s, but completes successfully).
- **Updated recommendation:** solution #1 is sufficient for now. Deeper fixes (#5 client-side parsing, #4 upgrade) can be deferred to a dedicated session if latency or reliability becomes an issue.

## 2026-11-16 (late) — Reverted non-native parse-recovery counter + prompt hint

- **Decision (user):** the counter-based recovery (cap 3→5) and the TOOL CALL FORMAT prompt hint are non-native workarounds that risk the same long-term fragility as the original Ollama-era custom tool-calling mechanism (which broke constantly). Reverted to the original one-shot recovery (`litert_parse_recovered` bool) and the original "connection error" message. The prompt/description trim (pass 1, `d23a41d`) is kept — cosmetic and test-covered.
- **Rationale:** prefer native errors until a LiteRT-side fix ships. The one-shot `parse_leaked_tool_call` recovery (pre-existing) remains; the counter extension is gone.
- **Data preserved:** the root cause is confirmed (Turkish diacritics in tool args → doubled-brace output → LiteRT LLGuidance parser rejects). Solution #1 (counter) worked (5/5 saved) but is fragile. Solution #3 (prompt hint) was ineffective. Real fix still needs #4 (upgrade) or #5 (client-side parsing) — deferred to a dedicated session.
- **User's question answered:** "toollarda Türkçe olan ne var ki?" → only `find_free_slots` description has Turkish trigger phrases ("boş saat", "uygun saat"). All other tool schemas are English. The Turkish content that triggers the parser comes from USER INPUT (personal facts, calendar titles, note content) passed as tool arguments — not from tool definitions.
- **How the parser currently works (native):** LiteRT's constrained-decoding parser (LLGuidance) parses the model's tool-call output. On parse failure (doubled braces), the error message contains the full call text; `parse_leaked_tool_call` extracts it and routes it through normal execution — one-shot per turn. If it fails again, the turn errors out with "connection error". No client-side parsing bypass.

## 2026-11-18 (pass 4) — GPU backend test (VideoCore VII)

- **GPU backend (WebGPU):** engine created in 5.6s, but inference took **63.6s** for "Merhaba" (vs ~13-18s on CPU). VideoCore VII GPU is NOT suitable for Gemma 4 E2B. WebGPU backend is not optimized for Pi's GPU. **Abandoned.**
- **Conclusion:** CPU (XNNPACK) remains the best backend on Pi 5. No further backend options available (NPU = Hailo-10H, not yet supported in LiteRT-LM).
- **Latency pass summary (passes 1-4):** cold TTFB ~32s → ~13-18s (1.8-2.5x improvement). Main wins: max_num_tokens 8192→4096, MTP activation, ringbuffers, prompt trim. Remaining: deeper prompt compression, num_ctx tuning.

## 2026-11-18 (pass 3) — Prompt trim + embedding model assessment

- **Prompt trim:** system prompt 16 rules → 14 condensed rules (18082 → 15273 chars, ~4520 → ~3818 tok, -15%). Tool descriptions trimmed (21745 → 21028 chars, -3%). Total prefill reduction ~880 tokens.
- **Benchmark (pass 3):** cold TTFB ~13-18s (was ~20s, further improvement from prompt trim + cache warming). Warm follow-up ~13s (cache eviction from 3 sequential sessions; max=2).
- **YNNPACK:** confirmed NOT compatible with Gemma 4 E2B (IsTensorSupported errors on tensor types). No model variant fixes this — it's a LiteRT framework limitation. Documented and abandoned.
- **Embedding model assessment:** `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` (278M, 768-dim). Retrieval latency on Pi: 5-9ms (fast once loaded). NOT a significant bottleneck. User requested no changes — just detection. Noted for future reference.
- **Remaining latency work:** GPU backend test (VideoCore VII), num_ctx A/B with cache, deeper prompt compression.

## 2026-11-18 (later still) — Latency pass 2: max_num_tokens 4096 + MTP + warmup (1.6x speedup)

- **Root cause found:** Gemma 4 E2B's native max context is 4096 tokens, but we set `max_num_tokens=8192`. This forced the MTP drafter to be re-targeted from magic number 32003 → 8192, adding overhead. Reducing to 4096 gave **1.6x speedup**: cold TTFB 32s → 20s, warm 13s → 8s.
- **MTP activated:** switched from deprecated `enable_speculative_decoding` bool to new `speculative_decoding_config=SpeculativeDecodingConfig(mode=ON)`. Model file confirmed to contain MTP drafter weights (mtp_drafter signature, 275 tensors).
- **Config knobs enabled:** `use_ringbuffers_local_attention=True`, `thread_count=4`, `cache_dir=None` (default). `enable_ynnpack=True` tested but failed (IsTensorSupported errors on Gemma 4 tensors) → reverted to False.
- **Engine warmup added:** dummy inference on startup (~3s) pre-compiles XNNPACK kernels → first real request ~2s faster.
- **piserve assessment:** still essential (litert-lm serve CLI lacks max_num_tokens, conversation caching, tool calling, thinking config). No replacement viable. Improvements made: warmup, new MTP API, 4096 context.
- **Final numbers:** cold TTFB ~20s, warm ~8s (was 32s/13s). Google's official: 99 tok/s prefill / 9 tok/s decode (we're closer now but still behind on decode).
- **Remaining latency work:** prompt trim (system 1526→1000 tok, tools 3007→2000 tok), num_ctx A/B with cache, GPU backend test.

## 2026-11-18 (later) — Conversation cache fixed + enabled by default (~2.5x follow-up speedup)

- **Root cause found:** piserve's conversation cache (`conversation_cache_max`) was broken — newly-created conversations were closed in the `finally` block even when cached (`if reused is None: conv.close()`), so the next request failed with "Conversation is closed." Fix: `if reused is None and not can_reuse: conv.close()` (commit `37d2877`).
- **Result:** follow-up TTFB dropped from ~32 s to ~13 s (2.5x). Turn 1 (cold) still ~32 s (full prefill). Tool-calling works with caching (tested: action + follow-up, both correct).
- **Enabled by default:** `conversation_cache_max: 2` in `litert_serve/server.py` DEFAULT_CONFIG and install.py `_write_piserve_config`. Trade-off: cached conversation holds system prompt + history from turn 1; session switching or retries can desync. Disable (set to 0) if stale-context answers appear.
- **Latency pass 2 (prompt trim):** trimmed system prompt + 5 tool descriptions (~400 tokens) showed no measurable improvement (24.75→25.73 s). Prefill remains the driver (62 tok/s on Pi 5 CPU). Deeper cuts (system prompt rules, full tool-schema compression) need live A/B with tool-calling accuracy validation — deferred to a dedicated session.

## 2026-11-18 — Determinism window-edge tests + overflow misclassification fix

- **Determinism edge tests added** (tests/test_audit_flywheel.py): `test_failure_digest_window_edge_inside` (6d → inside 7d window) and `test_failure_digest_window_edge_outside` (8d → outside). Both use relative timestamps (SQL-side `datetime('now')` clock). 16 flywheel tests pass.
- **Overflow misclassification fixed:** `_is_context_overflow()` no longer matches bare "invalid_argument" (which caught LiteRT parse failures). Now explicitly excludes "failed to parse tool calls" and matches only overflow-specific phrases ("too long", "context length", "context window", "exceeding the maximum", "token ids are"). New test case pins the parse-failure exclusion. Suite 1026 passed.

## 2026-11-17 — LiteRT 0.19.2 upgrade tested: parser NOT fixed; counter-based recovery is the effective workaround

- **Upgrade (2026-11-17):** litert-lm 0.16.1 → 0.19.2 via `uv tool upgrade`. piserve restarted, health 200, model loaded. No API breakage (imports OK, py_compile OK).
- **Test result (0.19.2):** single-fact Turkish diacritics → success (memories_saved: 1, no parse errors). But multi-fact Turkish request (5 facts) → **still fails** on the 2nd recovery. Upgrade did NOT fix the parser. The doubled-brace `{{...}}` issue persists on non-ASCII content in 0.19.2.
- **Counter re-applied (cap 5):** reverted (6069e9c) then re-applied (dc8c18b) after confirming the upgrade didn't fix it. Tested with Turkish multi-fact (5 facts) → **memories_saved: 5, 4 recoveries logged, no errors**. Full success.
- **Final state:** counter-based recovery (cap=5) is the effective workaround. Solution #3 (prompt hint) is ineffective (doubled braces persist). Solutions #4-#8 deferred. Native fix requires solution #5 (client-side parsing) or a future LiteRT-LM version.
- **Decision (user):** "native olmayan yapı daha kırılgan olabilir" — user initially wanted revert, but after seeing the upgrade (native attempt) also failed, accepted the counter as the pragmatic workaround. The counter is stateless per-turn (no chase-fix cycle risk). Native errors still surface when cap (5) is exhausted.
- **Retrieval verified:** memory system works — 9 'default' memories, retrieval returns results (sim 0.46+). "Beni tanı" test successful.

## 2026-11-16 (evening) — LiteRT tool-call parser fails on non-ASCII (Turkish) content; data + plan

- **Symptom:** long messages + tool use → "⚠️ Sunucuyla bağlantı kurulamadı" (errConnLost). Server log: `litert stream error: INVALID_ARGUMENT: Failed to parse tool calls from code block: call:save_memory{{"category": "general", "content": "<Turkish text with diacritics>", "importance": 6.0}}` — doubled braces `{{...}}` rejected by LiteRT's LLGuidance parser mid-stream.
- **Confirmed (2026-11-16):** ASCII-only content in the same tool succeeds (`memories_saved: 1`, no parse errors). Turkish diacritics (İ, Ö, ğ, ü, …) in tool arguments are the trigger.
- **Scope:** not save_memory-only. Audit log shows failures across `create_calendar_event` (1 fail), `list_calendar_events` (3), `list_notes` (1), `read_note` (3) — the common factor is non-ASCII content in arguments. `save_memory` shows 17 successes (recovered or ASCII), 0 recorded failures (failures never reach the audit row because the tool is not executed).
- **Recovery path (existing):** `llm/stream.py` extracts the call from the error message and routes it through normal execution (`parse_leaked_tool_call`), one-shot per turn (`litert_parse_recovered`). If a SECOND parse failure occurs in the same turn, recovery is exhausted → stream error → "connection error" in the UI. This matches the log: "Recovered … save_memory()" then a later "Stream error … INVALID_ARGUMENT".
- **Round:** the failure is NOT round-2-only. Both round-1 and round-2 parse failures are observed; the one-shot flag is the bottleneck.
- **Environment:** piserve wraps LiteRT-LM (`RawSchemaTool`, constrained decoding via LLGuidance, `automatic_tool_calling=False`); model `gemma4-e2b`. litert-lm installed via uv tool (version not determined).
- **Workarounds (no code change):** (a) send facts in ASCII (transliterate), (b) use the UI memory panel (bypasses the LLM entirely — no tool calls, no parser), (c) small batches + retry (sometimes passes).
- **Professional solution plan (prioritized, ready for next session):**
  1. **Quick fix (low risk, ~30 min):** change `litert_parse_recovered` from one-shot bool to a counter with cap (e.g. 3) — each recovery extracts the call and continues; cap prevents infinite loops. Directly fixes "second failure errors out".
  2. **User-facing mitigation (low risk, ~30 min):** clear error message in UI on parse failure ("tool call could not be parsed — retry or use the memory panel"); document the ASCII workaround in the teach-me template.
  3. **Prompt engineering (low risk, ~1 h):** add format hint to system prompt / tool descriptions: "emit tool calls as `call:name{...}` with single braces and valid JSON; escape non-ASCII as \\uXXXX." May reduce doubled-brace emission.
  4. **Upgrade LiteRT-LM (medium risk, ~1 h):** check for a newer version with a fixed parser (`pip index versions litert-lm` / GitHub releases). Risk: piserve compatibility.
  5. **Client-side tool-call parsing (medium risk, ~2 h):** if LiteRT's parser fails, parse the raw text ourselves (regex for `call:name{...}`, normalize doubled braces). Bypasses LiteRT's parser. Risk: handle all tool-call formats.
  6. **Pre-normalize tool arguments (low risk, ~30 min):** detect parse failure and retry with a hint appended to the system prompt.
  7. **Switch to Ollama for tool-heavy turns (medium risk, ~2 h):** Ollama's parser may handle non-ASCII better; app already supports both backends. Trade-off: speed.
  8. **Disable constrained decoding (high risk, ~2 h):** set `automatic_tool_calling` differently or don't pass tools as `Tool` objects. Risk: model may emit malformed calls more often without constraints.
- **Recommended order:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 (quick wins first, then deeper fixes).
- **Note on the LLM's role:** this is a LiteRT *constrained-decoding parser* limitation, not an LLM capability gap. The model produces the right intent and arguments; the parser rejects the serialization. The LLM remains useful for retrieval, chat, and reasoning — the parser bug is a specific, fixable infra limitation.

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

## Archived entries (pre-2026-09-01)

Moved to `docs/journal-archive.md` on 2026-11-16 (R7 split). Nothing was deleted; cross-references like "see entry 14" resolve in that file. Recent entries (2026-09-01 onward) stay here.


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
| ~~🟢 Low~~ ✅ Done 2026-11-16 | **Better session auto-titles** — first-38-chars truncation yields clipped sentences; use a tiny LLM summary instead | Already shipped: instant title = first 4 words (capped 40 chars) + background LLM enrichment (2-5 words) in `routers/chat.py::_enrich_title` (runs up to 4 messages, never overwrites a renamed session). The "first-38-chars truncation" no longer exists in the code.
| 🟢 Idea | **Proactive features** (morning briefings, reminders push) — required to fully match branded assistants |
| 🟢 Parked | **Installer web wizard** — deferred until external testers report CLI friction points |
| ~~🟢 Low~~ ✅ Done 2026-08-23 | More language support — tr/en shipped via UI_LANGUAGE setting |
