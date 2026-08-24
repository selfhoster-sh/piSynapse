# piSynapse — Development Journal

> **About this file** (developer's test-environment notes): created to carry every test, rule, and piece of essential knowledge accumulated since day one. It is used while coding with AI to keep the project structure intact, capture required knowledge, and hand it over correctly. **Never trust a statement here unconditionally** — if you are unsure of its currency, VERIFY first; after verification, EDIT the relevant spot: do not delete the old text, strike it through (`~~...~~`) and note why it is now invalid/unnecessary/done/fixed, with the date.

**Reverse chronological: newest entries live at the TOP**, oldest at the bottom — keep it that way with every new entry. Timeless reference sections sit at the very bottom.

## READ FIRST — AFTER EVERY SESSION/COMPACTION

- The project IS a git repo (since Aug 13, 2026). Commit changes one by one (rule: one item = one commit + py_compile + pytest). Before risky architectural work, take a backup: `backups/piSynapse-*.tar.gz` (gitignored). ASK THE USER whether a backup should be taken — never assume "I took a backup" on your own.
- No architectural changes without user approval (new folders/packages, new infrastructure like Docker/WebSocket, framework swaps). Don't widen scope on your own initiative.
- Before writing "the user approved/accepted" ANYTHING, make sure that approval was really, explicitly given in this conversation. If unsure, write honestly "the user did not approve, I assumed" — never fabricate an approval.
- The services/ layer was REMOVED (July 30, 2026) — legacy modules (db.py, llm/, tools/, embedding.py) do all the work. Don't propose a DI/service layer again unless the user explicitly asks.
- Docker and WebSocket (/chat/ws) were removed — the frontend uses SSE only (/chat/stream); do not reintroduce them.
- The Ollama service is stopped/disabled — LLM_BACKEND=litert is active. Don't restart Ollama or add dependencies on it unless the user asks.
- Journal policy: entries are strictly reverse chronological (newest first), record project-relevant facts only — no meta/authority commentary ("full authority", "while user slept", approval statuses). Applies to every future edit.
- Currency rule: before relying on a statement in this file, verify it against the code. Found-stale statements get struck through with a dated reason (invalid/unnecessary/done/fixed) — never silently deleted.
- Test coverage used to be ~7% (calendar_ops.py, mail.py, llm/, tools/ dispatcher untested). A dedicated hardening pass has been running since August; suite size is tracked in the entries below.

## 2026-08-24 (21) — Laptop field report + language anchoring + clarify guards

First external-hardware install (ollama + GPU laptop): **one-shot success**, no installer steps failed. Issues found & fixed:

- **Language mirror failure (recency bias proven live):** chip text "Yeni etkinlik oluştur" got an ENGLISH clarifying question even though the LANGUAGE RULE sat at the very top of the system prompt. Root cause: the LAST text in context was the English `CLARIFY_REQUIRED` tool result — small models mirror the most recent language seen, overriding top-of-prompt rules ("türkçe konuş" mid-chat fixed it, confirming the mechanism). Fix: every guard string now embeds the user's original message as a language anchor (`_user_text` threaded through dispatcher helpers). Verified live: TR chip → TR question, EN chip → EN question, zero junk writes.
- **Clarify guards are backend-enforced:** gemma called `create_note(title='Yeni Not')` with empty content DESPITE prompt instructions — prompt hope is not enforcement. Dispatcher now returns `CLARIFY_REQUIRED` (with the anchored user text) instead of executing empty creates for note/task/event/email; calendar's hidden `"New Event"` default summary removed.
- **New welcome chips:** 'Yeni etkinlik oluştur' / 'E-posta gönder' (+EN); all four phrasings verified routing to calendar/email through the live classifier.
- **Prompt:** Rule 1 exception (missing essentials → ONE short clarifying question, never invent placeholders); new Rule 12 honesty clause; per-group one-line ask-first rules.
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
| Open | Chip-origin create requests may still execute with placeholder titles ('yeni görev') when a model supplies one — proposed fix: frontend sends origin=chip flag, dispatcher then forces clarify | awaiting decision |

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
- **i18n:** toolAttempt/toolCap/genRetryLabel (tr/en); TOOL_LABELS map covers all 22 tools with graceful fallback to the raw name.
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
- Clock position restored: .sess-del absolutely positioned right (hover swaps time↔trash Discord-style), padding-right:20px on the name. Time always flush right.
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

- 22:07 — full codebase review requested for `/home/salih/piSynapse` (base `ddc5afa` + uncommitted routers/chat.py abort changes). Three copies exist: piSynapse (current), -release, -release-backup.
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
| **29** | **LiteRT systemd unit** | LiteRT ran as a manual process (PID 3482251, no unit → died on reboot). Created /etc/systemd/system/litert.service (User=salih, uv python + litert-lm serve --host 127.0.0.1 --port 9379, Restart=on-failure). Manual process stopped → enable --now. Port 9379 verified with a model query (gemma4-e2b, gemma4-e4b). |
| **30** | **pisynapse.service ordering** | After=network.target ollama.service → After=network.target litert.service. pisynapse itself was disabled → enabled (reboot-safe). systemd-analyze verify clean. |
| **31** | **dev-rules update** | piSynapse-dev-rules.md: git repo status, llm/ and tools/ package layout (instead of llm.py/tools.py), LiteRT primary + gemma4-e2b (dash not colon), pytest 27 tests + ruff/mypy commands, port 8765, MAIL_PROVIDER empty=disabled, XFF/rate-limit note, false "SSRF prevention" line corrected, systemd units. |

**Total audit outcome:** A1-A10 ✓, B1-B5 ✓ (B5=C5 skipped, noted), C1-C8 ✓, D1-D6 ✓ — **31 items**, 20+ commits, 27/27 tests, smoke OK. Everything committed to main.

## Changes — 2026-07-31

| # | Change | Detail |
|---|-----------|-------|
| **1** | **Port 8765** | pisynapse.service port 8000 → 8765. Old 8765 process (PID 314732, manual) stopped, systemd unit updated. |
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
1. search_emails finds the content the user refers to — the model calls search_emails(query="Netdata") instead of asking
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
| 🟡 Medium | **HTTPS/microphone** — Caddy self-signed or NPM solution |
| 🟡 Medium | **Performance** — NUM_CTX raised to 8192 (done); latency tuning round (13-15s → 10-12s) still open |
| 🟢 Low | Redis cache for session management (optional) |
| 🟢 Low | Observability: Prometheus metrics, structured logging |
| 🟢 Low | Multi-user authentication (JWT) |
| ~~🟢 Low~~ ✅ Done 2026-08-23 | More language support — tr/en shipped via UI_LANGUAGE setting |
