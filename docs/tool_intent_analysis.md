# piSynapse Tool & Intent Mechanism Analysis & Improvement Suggestions
*Research completed 2026-08-28 — no changes made, approval required*

---

## 1. ARCHITECTURE OVERVIEW

### 1.1 Tool System (tools/definitions.py + dispatcher.py)
- **27 tools** across 6 groups: weather(2), email(4), calendar(4), tasks(6), notes(6), memory(1) + get_datetime(1)
- **TOOL_GROUPS** (line 389-396): maps intent group → tool names; `get_datetime` in all groups
- **Schema-driven**: Ollama native function-calling JSON schema; small models get filtered tools (~200-400 tokens vs ~2000)
- **Chip flow guards**: `origin=="chip"` forces CLARIFY_REQUIRED for create/send tools (no detail)
- **Confirmation tools** (line 418): send_email, delete/update_calendar_event, delete_note, complete_task, delete_task
- **Position-based references**: model sees numbered lists (1., 2., ...); dispatcher resolves via session-persisted maps

### 1.2 Intent Classification (llm/intent.py)
**Pipeline (fast → slow, deterministic → probabilistic):**
1. `reminder_group()` — deterministic regex (clock/date) → calendar/memory/None
2. `_hit_groups()` / `_keyword_group()` — substring heuristics (ordered, first hit wins)
3. Multi-domain check: ≥2 keyword groups → combined toolset
4. **Embedding similarity** (FastEmbed paraphrase-multilingual-MiniLM-L12-v2): cosine ≥0.50 + margin ≥0.05
   - Thin margin (<0.10) + conflicting keyword → keyword wins
5. Fallback to keywords → LLM fallback (INTENT_LLM_FALLBACK=on, ~15s delay)

**Key deterministic overrides:**
- Reminder routing fires BEFORE embedding (line 343-356)
- Multi-domain keyword hits → combined tools (line 363-369)
- Thin-margin embedding + keyword conflict → keyword wins (line 399-407)

### 1.3 Context & State (prompt.py + db.py)
- **Session maps** (email/notes/tasks/calendar): list-number → real ID persisted in SQLite
- **TTL caches**: calendar today (5min), find_events (5s), tasks (30s), notes (30s)
- **Core Memories**: embedding-backed (cosine ≥0.35), deduplicated on save
- **Rolling summaries**: FTS5 (unicode61) + semantic search hybrid

---

## 2. TOOL-BY-TOOL ANALYSIS

| Tool | Backend | Key Behaviors | Gaps / Risks |
|------|---------|---------------|--------------|
| **get_weather** | OpenWeatherMap (weather.py) | City optional (DEFAULT_CITY); retry 2x | No forecast, no alerts; single-call |
| **get_datetime** | Local | Instant, no params | — |
| **Calendar (4)** | Nextcloud CalDAV (calendar_ops.py) | All-day via VALUE=DATE; list caches 5min; _match_event: UID exact > summary substring; ambiguous→never auto-pick | No recurring events (RRULE); no attendees; update_event complex duration logic; no time-zone handling |
| **Email (4)** | IMAP/SMTP (mail.py: Gmail + ProtonBridge) | list→cache map; search: IMAP TEXT/SUBJECT/FROM OR; send: fresh SMTP per retry | No multi-folder (only INBOX); no threading/conversation view; no attachments; ProtonBridge req local Bridge; search IMAP OR not full-text |
| **Tasks (6)** | Nextcloud CalDAV VTODO (nextcloud_tasks.py) | 30s cache; priority 1-9; due ISO/date; complete/delete by UID prefix | No recurring; no subtasks; no projects/lists; search client-side (loads all) |
| **Notes (6)** | Nextcloud Notes REST (nextcloud_notes.py) | 30s cache; ETag-based update; category+tags; search client-side | No folders; search scans all notes (O(N)); no rich text/markdown rendering |
| **save_memory** | SQLite + embedding (db.py) | Dedupe: cosine ≥0.35 → update access_count; category enum; importance 1-10 | No memory groups/types; no temporal queries ("what did I say last week?"); no auto-categorization; embedding backfill async but unbounded |

---

## 3. INTENT CLASSIFICATION DEEP DIVE

### 3.1 Current Strengths
- **Deterministic reminder routing** (0 LLM calls, <1ms): clock/date regex + verb list covers 80%+ real cases
- **Multi-domain keyword union**: "hava durumu maille gönder" → email+weather tools
- **Thin-margin keyword override**: prevents embedding drift (e.g., notes→memory at margin 0.06)
- **Audit logging** (intent_audit_log): message, chosen_group, sim, margin, source

### 3.2 Known Weaknesses / Blind Spots
| Issue | Example | Current Result | Root Cause |
|-------|---------|----------------|------------|
| **Spelled-out durations** | "in einer Stunde", "dans 10 minutes" | memory (no clock match) | _CLOCK_SIGNAL_PATTERN only numeric |
| **Ordinal/worded hours (ES/DE)** | "a las nueve", "um acht Uhr" | memory | Pattern expects digits |
| **Half-hour TR** | "yarım saat sonra" | accidental (matches "saat") | Fragile |
| **Relative clock** | "saat 3'te" vs "3 saat sonra" | calendar vs ? | "3 saat sonra" no clock pattern |
| **Location triggers** | "eve dönünce çamaşırları as" | memory (correct) | No geo support — by design |
| **Compound reminders** | "yarın 9'da ve 14'te hatırlat" | single event | No multi-time parsing |
| **Negation** | "hatırlatma, sadece kaydet" | calendar (false positive) | No negation handling |
| **Cross-lingual verb gaps** | Italian/Portuguese/Russian reminder verbs | None | Only TR/EN/DE/FR/ES covered |

### 3.3 Embedding Corpus Gaps (line 179-242)
- **Weather**: 6 langs ✓
- **Email**: 5 langs ✓ (no Arabic example)
- **Calendar**: 5 langs + reminder phrases ✓
- **Tasks**: 5 langs + update verbs ✓
- **Notes**: 5 langs + verb-first TR ("not düş") ✓
- **Memory**: 5 langs ✓
- **Question/Time/Greeting**: 6 langs each ✓
- **MISSING**: "free slot", "boş saat", "available time" → calendar; "move event", "shift meeting" → calendar (have update but not explicit); "cancel event" → delete (have delete but not explicit)

---

## 4. CROSS-CUTTING CONCERNS

### 4.1 Reliability / Error Handling
| Area | Mechanism | Risk |
|------|-----------|------|
| **DB** | WAL + busy_timeout=10s + retry 3x (0.25/0.5/0.75s) | Good |
| **CalDAV/IMAP** | @retry(attempts=2, delay=1-2s) on sync fns | OK; no circuit breaker |
| **Nextcloud Notes/Tasks** | Same retry; 30s cache | Cache staleness on concurrent writers |
| **Embedding** | FastEmbed ONNX; async to_thread; fails→empty vec | Silent degradation (memory search drops vec) |
| **LLM intent fallback** | 15s blocking call; think=False; num_predict=20 | Latency spike; no timeout guard |
| **Tool verification** (tool_verification.py) | Runs on /execute + model loop; validates params | Not in dispatcher for model calls (only /execute) |

### 4.2 Security
- **Input sanitization**: `_ical_escape_text` (calendar), `sanitize_imap_query` (mail), `sanitize_external_text` (prompt context)
- **Confirmation tools**: UI card auto-shown; never ask "are you sure?" in text
- **DB permissions**: umask 077; DB files chmod 600 on startup
- **Audit redaction**: _AUDIT_REDACT_KEYS scrubs secrets/PII from tool_audit_log
- **FTS5**: unicode61 remove_diacritics 2 (Turkish-safe)

### 4.3 Performance / Pi Constraints
- **Model**: litert (gemma4-e2b) — 2-5 tok/s on Pi 5
- **Embedding**: FastEmbed ONNX — CPU, ~50-100ms/batch
- **Tool groups**: Reduce schema from ~2000 → ~200-400 tokens
- **Shared query embedding** (chat.py line 126): single embed for retrieval+intent+memory
- **Caches**: Calendar 5min, tasks/notes 30s, find_events 5s
- **No background workers**: All async; periodic rollup/cleanup 24h loops

---

## 5. IMPROVEMENT SUGGESTIONS (PRIORITIZED)

### P0 — Critical (Correctness / Data Loss Risk)

#### 5.1 Fix save_memory embedding backfill unbounded task leak
**File**: `db.py` lines 1243-1256
```python
if backfill_ids:
    async def _backfill():
        for mid in backfill_ids:  # NO LIMIT — could be thousands
            ...
    asyncio.create_task(_backfill())  # Fire-and-forget, no tracking
```
**Problem**: On a DB with many legacy memories (no embedding), a single search spawns an unbounded background task that embeds ALL missing rows sequentially. Can OOM or stall DB.
**Fix**: Batch (e.g., 10 at a time), add semaphore, track in-flight, or move to periodic maintenance job.

#### 5.2 Calendar update_event duration logic bug for all-day events
**File**: `calendar_ops.py` lines 373-402
```python
if new_duration_minutes and new_duration_minutes > 0:
    new_end = new_dt + timedelta(minutes=new_duration_minutes)
else:
    old_end = d.dtend.value if hasattr(d, "dtend") else old_dt
    try:
        duration = old_end - old_dt
    except TypeError:
        duration = timedelta(hours=1)
    new_end = new_dt + duration
if all_day:
    d.dtend.value = new_end.date()  # BUG: new_end is datetime, .date() loses time
```
**Problem**: When moving an all-day event with `new_start_time` + `new_duration_minutes`, the end date calculation uses datetime arithmetic then truncates — wrong for all-day (should be next day, not +N minutes).
**Fix**: Separate all-day path: if all_day → `new_end = new_date + timedelta(days=1)`; ignore duration_minutes.

#### 5.3 Email search IMAP injection via sanitize_imap_query
**File**: `utils.py` (not read but referenced in mail.py line 107)
**Risk**: If `sanitize_imap_query` doesn't escape double-quotes/backslashes, a query like `test" OR "1"="1` could bypass folder limits.
**Verify**: Check `utils.sanitize_imap_query` implementation; ensure it escapes `"` and `\`.

### P1 — High (User Experience / Functional Gaps)

#### 5.4 Spelled-out duration parsing → clock signal
**File**: `llm/intent.py` `_CLOCK_SIGNAL_PATTERN`
Add patterns for: `in einer Stunde`, `dans 10 minutes`, `en 10 minutos`, `übermorgen um 10`, `demain à 10h`.
**Impact**: "bana bir saat sonra su içmeyi hatırlat" → calendar (currently memory).

#### 5.5 Ordinal/worded hour support (ES/DE/FR/TR)
**File**: `llm/intent.py` — add to `_CLOCK_SIGNAL_PATTERN`
- DE: `um (ein|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|elf|zwölf) Uhr`
- ES: `a las (una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)`
- FR: `à (une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze) heures?`
- TR: already has spelled cardinals (bir, iki, üç...); add ordinal forms (`birinci`, `ikinci` — rare but possible)

#### 5.6 Negation handling in reminder_group
**File**: `llm/intent.py` `reminder_group()`
```python
if _NEGATION_PATTERN.search(ml):  # "hatırlatma", "don't remind", "nicht erinnern"
    return "memory"  # or None
```
**Impact**: "hatırlatma, sadece not al" → memory (not calendar).

#### 5.7 Multi-time reminder parsing
**File**: `tools/dispatcher.py` `create_calendar_event` handler
Add detection: if message contains multiple clock signals → ask user to pick one, or create multiple events.
**Current**: Single event with first/last time.

#### 5.8 Free-slot auto-scheduling (user's original idea)
**File**: `tools/dispatcher.py` + `prompt.py` rule 16
Implement: `list_calendar_events(days_ahead=1)` → find gaps ≥duration → suggest/create.
**API**: Add optional `auto_slot=true` to `create_calendar_event` or new tool `find_free_slot`.

### P2 — Medium (Quality / Maintainability)

#### 5.9 Intent embedding corpus expansion
**File**: `llm/intent.py` `_TOOL_EMBED_CORPUS`
Add seed phrases for:
- Free-slot: "boş saatte", "free slot", "available time", "wann passt es", "horaire libre"
- Move/reschedule: "etkinliği taşı", "move event", "verschieben", "déplacer", "mover"
- Cancel: "iptal et", "cancel event", "absagen", "annuler", "cancelar"
- Recurring: "tekrarlayan", "recurring", "wiederkehrend", "récurrent", "recurrente"
- Multi-time: "iki kez hatırlat", "remind twice", "zweimal erinnern"

#### 5.10 Tool group for "question+action" hybrid
**File**: `tools/definitions.py` `TOOL_GROUPS`
Currently `question` has no tools. Some queries need `get_datetime` + answer: "what time is it in Tokyo?" → needs timezone conversion (not available). Consider `utility` group: `get_datetime`, `get_weather` (for "should I bring an umbrella?").

#### 5.11 Task/Note search: server-side vs client-side
**File**: `nextcloud_tasks.py` `_search_tasks_sync` line 308-315; `nextcloud_notes.py` `search_notes` line 311-316
Both fetch ALL then filter in Python. For large collections (>500), this is slow.
**Fix**: Nextcloud Tasks/Notes APIs support search? If not, add pagination + early termination; or add `limit` param to search tools.

#### 5.12 Calendar: recurring events (RRULE) support
**File**: `calendar_ops.py` — `create_event`, `update_event`, `list_events`
Currently no RRULE handling. Industry standard: `DTSTART` + `RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR`.
**Scope**: Large — affects create, list, update, delete (delete instance vs series).

#### 5.13 Email: multi-folder / threading / attachments
**File**: `mail.py` — `_list_emails` hardcoded `INBOX`; no thread view; no attachment metadata.
**Quick win**: Add `mailbox` param to `list_emails` (default INBOX); expose `search_emails` mailbox filter.

### P3 — Low (Nice to Have / Technical Debt)

#### 5.14 Embedding model upgrade path
**File**: `embedding.py` line 13-16
`paraphrase-multilingual-MiniLM-L12-v2` (384-dim, 2020). Newer: `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` (768-dim, better), or `intfloat/multilingual-e5-small` (384-dim, 2022, better retrieval).
**Migration**: Re-embed all memories (backfill task in 5.1 can do this).

#### 5.15 Intent LLM fallback timeout guard
**File**: `llm/intent.py` line 449-467
Add `asyncio.wait_for(..., timeout=10.0)` around client.post; fallback to keyword on timeout.

#### 5.16 Tool verification coverage
**File**: `tool_verification.py` (not read) — runs on `/execute` + model loop. Verify it covers:
- Param validation (types, ranges)
- Idempotency checks (double-create)
- Cross-tool consistency (event UID exists before update)

#### 5.17 Unified "find by reference" helper
**Pattern**: `_resolve_position` (dispatcher.py line 62) duplicated logic for email/notes/tasks/calendar.
**Refactor**: Single `resolve_ref(session_id, ref, context_fn, id_field)` used by all.

#### 5.18 Intent audit dashboard / alerting
**File**: `db.py` `intent_audit_log` — logs source, sim, margin. No automated review.
**Add**: Daily job: flag `margin < 0.08` + `source in (embedding, llm)` → review queue.

#### 5.19 Language-specific prompt variants
**File**: `prompt.py` `LANGUAGE_RULE` (line 13-17): "mirror language from words alone". Small models fail on code-switching ("hava nasıl weather?").
**Add**: Explicit few-shot examples per language in group prompts (especially TR/DE where models confuse).

---

## 6. REFACTORING OPPORTUNITIES

| Area | Current | Proposed |
|------|---------|----------|
| **Tool registry** | Hardcoded list in definitions.py | Plugin/entrypoint system; auto-discover `tools/*_ops.py` |
| **Intent corpus** | Single flat list | YAML/JSON per domain; versioned; testable |
| **Regex patterns** | Inlined in intent.py | Compiled constants with tests; regex debugger |
| **Session maps** | 4 separate tables (email/notes/tasks/calendar) | Single `session_refs` table: `(session_id, domain, seq, ref_id, meta_json)` |
| **Cache invalidation** | Manual `_invalidate_*_cache()` calls | Event-driven: write → pub/sub → cache drop |
| **Error taxonomy** | String prefixes ("ERROR:", "CLARIFY_REQUIRED:") | Enum/Exception hierarchy; structured error codes |

---

## 7. TESTING GAPS

| Module | Coverage | Missing |
|--------|----------|---------|
| `reminder_group` | 17 probe cases + unit tests | No ES/DE/FR/IT/PT verb tests; no negation tests |
| `calendar_ops` | All-day + timed serialization | No RRULE; no ambiguous match (multiple UIDs); no timezone |
| `dispatcher` | All tools | No chip-origin integration test; no concurrent position resolution |
| `embedding` | cosine_similarity | No batch consistency; no model swap test |
| `intent` | Embedding uncertain path | No thin-margin + keyword conflict integration test |
| `mail` | Gmail/Proton mock | No IMAP injection test; no attachment test |

---

## 8. RECOMMENDED NEXT STEPS (User Approval Required)

**Immediate (P0)**:
1. Fix `save_memory` backfill task leak (batch + semaphore)
2. Fix `update_event` all-day duration bug
3. Verify `sanitize_imap_query` escape completeness

**Short-term (P1)**:
4. Add spelled-out duration patterns to `_CLOCK_SIGNAL_PATTERN`
5. Add ordinal hour patterns (DE/ES/FR)
6. Add negation guard to `reminder_group`
7. Implement free-slot helper (list → gap find → create)

**Medium-term (P2)**:
8. Expand embedding corpus with missing action verbs
9. Move task/note search to server-side or paginated
10. Add recurring event (RRULE) support to calendar

**Long-term (P3)**:
11. Upgrade embedding model + re-embed migration
12. Add intent LLM fallback timeout
13. Unified session ref table + event-driven cache invalidation

---

## 9. FILES TO MODIFY (Summary)

| Priority | Files |
|----------|-------|
| P0 | `db.py` (backfill), `calendar_ops.py` (update_event), `utils.py` (sanitize_imap_query) |
| P1 | `llm/intent.py` (patterns, negation), `tools/dispatcher.py` (free-slot), `prompt.py` (rule) |
| P2 | `llm/intent.py` (corpus), `nextcloud_tasks.py`/`nextcloud_notes.py` (search), `calendar_ops.py` (RRULE), `mail.py` (multi-folder) |
| P3 | `embedding.py` (model), `llm/intent.py` (timeout), `tool_verification.py`, `db.py` (schema), `dispatcher.py` (unified resolve) |

---

**No changes made. Awaiting your approval on specific items before implementation.**
