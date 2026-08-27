# v1.7.2 — Tool-calling fine-tune (eval-driven)

**Eval:** 24 realistic first-turn cases vs the real service; first-turn accuracy
14/24 → each dominant failure fixed as its own commit. Suite 365→**380**.

## Routing: "reminder + time" → calendar (`913429a`, `098a435`)
- Deterministic `reminder_group()`: reminder word + time/date → **calendar**;
  reminder without time → **memory** ("şunu hatırla" memory stays memory).
- Trumps embedding + keyword substring (`_HATIRLA_NOT_REMIND` kills the
  `hatırla`→`hatırlatıcı` collision that dumped junk `save_memory`).
- tr/en/de/fr/es reminder words + time signals; audit source `reminder_rule`.
- Reminder + a second domain keeps the **combined** toolset.
- `create_calendar_event` description documents "remind me at &lt;time&gt;".

## Continuation: never stop after a lookup (`97640ea`)
Multi-step actions stopped after `list/read/search/get_datetime`. Now a
lookup-only round whose user request clearly asks for a mutation (TR stems +
EN/DE/FR/ES cues) gets one targeted `CONTINUATION_NOTE`; pure reads untouched.
`llm/utils.py` `LOOKUP_TOOLS`/`MUTATION_TOOLS`/`user_requested_action()`.

## Safety / quality
- `b826b66` streaming now rejects hallucinated **confirm-gated** tools
  (allowed_names parity with chat.py).
- `a5f4adc` removed dangling `"Pass "` fragment in the tasks group prompt;
  identical-execution refusal message shows the true per-tool budget.
- `6db92dd` `list_emails` vs `search_emails` explicitly cross-referenced
  (overview vs specific subject/sender/topic).

## Tests / Notes
- 380 passed, `py_compile` clean, health `db ok, llm ok`. Commits local only
  (not pushed until approved). Eval rerun + Nextcloud/DB artifact cleanup pending.