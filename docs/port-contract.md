# Port Contract — piServe behavior frozen for the Kotlin port (Faz 8)

Source of truth for re-implementing the server in another runtime. Every item
below is covered by an acceptance test (last section); a port is done when
those tests — ported alongside — pass against it. Standing directives: default
language EN; the tr/en catalog stays first-class (no hardcoded user strings).

## 1. Sessions & identity

- `session_id`: 12-hex uuid (`routers/chat.py` create_session), `user_id` resolved
  server-side from the API key (`config.get_user_id_for_key`) — never trusted
  from the client.
- All session reads/writes scope `(session_id, user_id)`: `get_history`,
  `get_messages_to_summarize`, `update_session_summary`, `search_sessions`
  (both FTS and semantic paths), `retrieval._fetch_candidates`,
  `save/clear/delete` paths. Cross-user same-`session_id` must neither leak
  nor clobber (`tests/test_user_isolation.py`).
- Session upserts use `ON CONFLICT(id) DO UPDATE ... WHERE sessions.user_id =
  excluded.user_id` (no PK change by design).

## 2. Rolling summary (fold)

- `db.get_messages_to_summarize(session_id, history_limit, summarized_until,
  batch_size, early_trigger=0, user_id)`: ids ASC for the session; no-op when
  `total <= history_limit`; `boundary = ids[total - history_limit - 1]`;
  pending = `(summarized_until, boundary]`; `effective_batch` = early_trigger
  iff first fold and pending suffices, else batch_size; skip when below it.
- Fold cap: at most `FOLD_MAX_MESSAGES` (30), oldest-first, each truncated to
  `FOLD_MAX_CHARS_PER_MESSAGE` (500) + "…"; the returned boundary is the last
  folded message id (progressive drain); all-blank spans advance past.
- Fold prompt: `SUMMARY_SYSTEM_PROMPT` (`llm/chat.py:98`) +
  `"Existing summary:\n…\n\nNew messages:\n…\n\nUpdated summary:"`, max 500
  output tokens; failures keep the previous summary (never raise).
- Write: `update_session_summary(..., expected_until)` applies only if the
  stored boundary still equals it (loser refolds next turn); always bumps
  `last_active`.
- Delete/retention paths clamp `summarized_until` to the surviving MAX(id),
  clear summary+until when empty, cascade `message_feedback` + `tool_audit_log`
  rows of removed messages (`db._repair_summary_boundaries`).
- Injection text (verbatim): `"\n\nSummary of earlier parts of this conversation
  (not repeated below):\n{summary}"` inside a 40%-of-context soft budget
  (`prompt.build_context`).
- Background title enrichment: first chance (≤4 messages), only while the name
  is unset/`New Chat`/RAKE-matching; RAKE = first words with `[e-posta]`/`[link]`
  PII masks.

## 3. Chat loop (both paths identical)

- Pure-chat gate (`intent == "question"`, no group): tools off; inject
  `_TOOL_ASK_HINT` (`llm/utils.py`) only when `should_arm_tool_hint(user_text)`
  (keyword domain touch); on `TOOL_NEEDED`/leak/bare-name, exactly one redo
  with the smallest sufficient toolset (`_escalation_tools`: leaked-name group
  → single keyword group → combined), stale hint stripped.
- Chip fast-path: `origin == "chip"`, non-think, create/send group + create
  verb in the message → deterministic localized clarify question, LLM skipped.
- Tool-call dedup signature: `name(json-sorted-args)`; repeat limit
  `MAX_IDENTICAL_EXECUTIONS`, but `create_*`/`send_email` max 1.
- Broken argument JSON → `{"_parse_error": raw}` (distinct failures, distinct
  sigs); handlers ignore unknown keys.
- Confirm tools (`CONFIRM_TOOLS` + `validate_confirm_params`) return
  `pending_action: {tool, params, preview?}` instead of executing.
- Abort: `abort_event` checked per round and per tool; terminal
  `{done: true, aborted: true, session_id}`; aborted turns are never saved as
  full replies (partial text via the existing path).
- Context: LiteRT normalize keeps `tool_name` (+`name` mapping); trim keeps
  tool triples atomic (assistant+tool_calls immediately followed by its tool
  results; orphans dropped); retrieval merges top-k older relevant messages
  with the verbatim recent window (deduped, drops logged).

## 4. Intent routing

- Order: deterministic reminder regex → keyword groups (`_hit_groups`;
  multi-domain → combined) → embedding similarity (margin rules) → LLM
  fallback gated by verbatim-evidence check (hallucinated evidence rejected).
- Resume Layer-0: anaphoric follow-ups route to the last *successfully
  executed* tool group (`verified`/`verified_by_fallback`/out-of-scope only;
  `unverified`/`verification_failed`/`verification_error` never anchor).

## 5. Memory & retrieval

- `save_memory` dedups by cosine ≥ `MEMORY_SIMILARITY_THRESHOLD` (0.68);
  retrieval keeps the recent window verbatim + top-k older above 0.35 within
  a hard 1500ms budget (timeout → empty, never raise).
- Canonical embedding model: `paraphrase-multilingual-mpnet-base-v2`
  (768-dim); single source `config.EMBED_MODEL`; startup warns on stored-dim
  drift; `reembed_all.py` is the migration path.

## 6. SSE event shapes

- `{token}`, `{reasoning}`, `{tool: {name, phase: start|end, ok, audit_id,
  verification_status, clarify, noop}}`, `{confirm: {tool, params, preview?}}`,
  `{gen_retry: {reason}}`, `{error}`, terminal `{done: true, session_id,
  memories_saved, ...}` or `{done: true, aborted: true, session_id}`.
- System prompt starts with `LANGUAGE_RULE` (verbatim, `prompt.py:13-17`):
  reply in the user's language, detected from their words, no language-name
  examples. Backend user strings come from the `messages` catalog by
  `UI_LANGUAGE` (default `en`); model-facing prompts stay English.

## 7. Inference adapter seam

- The port keeps ONE seam: OpenAI-compatible `POST /v1/chat/completions`
  (stream + non-stream) with `session_id` passthrough for server-side
  conversation reuse (`conversation_cache_max`, default 0 = stateless; LRU
  with eviction-close, cleared on engine reload). Everything above it is
  runtime-agnostic.

## 8. Acceptance tests (must pass on the port)

- `tests/test_user_isolation.py` (9) — cross-user negative tests.
- `tests/test_summary_bounds.py` (10) — cap/order/convergence/repair/cascade/race.
- `tests/test_write_integrity.py` (5) — concurrency, atomicity, import-once.
- `tests/test_chat_parity.py` (4) + `tests/test_stream_abort.py` (2).
- `tests/test_tool_escalation.py`, `test_chat/stream_loop_guards`,
  `test_retry`, `test_intent_*`, `test_tool_events`, `test_verification`,
  `test_title`, `test_history_hygiene`, `test_messages_i18n`,
  `test_install_template`, `test_dispatcher`, `test_tools`,
  `test_audit`, `test_security`, `test_health`, `test_media`,
  `test_calendar`, `test_mail`, `test_llm`, `test_utils`,
  `test_prompt_quality`, `test_retrieval`, `test_resume_context`,
  `test_settings_backend_sync`, `test_faz4/5`, `test_corpus_feeder`,
  `test_litert_serve`, `test_stability_fixes`.
- Plus: migration-step, old-DB, concurrency and FTS-failure tests inside the
  files above. Full suite green is the gate (648 passed at freeze time).
