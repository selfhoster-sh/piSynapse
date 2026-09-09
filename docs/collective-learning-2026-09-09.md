# Collective learning under multi-user (plan 2026-09-09)

Principle: identity is private, signal is collective. Raw data stays
per-user and invisible; only anonymized, quorum-gated patterns benefit
everyone. Grounded in: federated preference aggregation (FedBis/FedBiscuit,
ICLR 2025 — aggregate selectors, not raw data; cluster contradictory
preferences instead of averaging), adaptive reputation weighting (Srewa et
al. 2025 — weight by historical alignment), truthful-reporting mechanisms
for strategic labelers (Park et al. 2024), Byzantine-robust aggregation
(outliers never decide alone), PII placeholder patterns (Presidio-style).

## Phase 1 — Ownership guard (this commit)
`/tool-correction`, `/tool-confirm`, `/message-feedback` accept raw integer
ids with no owner check (`WHERE id = ?`); ids are sequential and guessable.
Fix: `user_id` (from `auth.current_user`) threaded into
`set_tool_correction` / `set_tool_confirmation` / `get_audit_tool_name` /
`upsert_message_feedback`; writes scope `AND user_id = ?` (message feedback
via owner join on conversations). Miss → 404, identical to not-found (no
oracle). Learning flow unchanged.

## Phase 2 — Signature normalization (lazy, candidates only)
`corpus_feeder` ingests RAW user sentences today — harmless single-user,
PII leak + noise amplifier multi-user. Before a pattern goes global, strip
entities to typed placeholders (`[PERSON]`, `[EMAIL]`, `[DATE]`…):
regex first (email/phone/URL/IBAN — cheap, exact), name rules second,
Presidio-class NER only if ever needed. Run lazily on quorum candidates,
never per message (Pi budget).

## Phase 3 — Quorum + reputation (weights, not bans) [IMPLEMENTED 2026-09-09]
A normalized pattern enters the corpus only after: 2 approved-account
agreements OR 1 agreement + admin approval (single-user fallback: admin
approval alone, else learning stalls). Contradiction (A→calendar, B→tasks)
freezes the pattern into the admin queue — last-writer never wins. A new
pattern contradicting established corpus needs admin regardless (FLTrust
logic). Per-user daily correction cap (flood control). Reputation =
agreement-with-quorum history → signal weight, never a ban; voter identities
live in `feedback_votes(audit_id, user_id)` (UNIQUE, admin-visible only);
`routing_patterns` carries NO user_id.
Sybil note: registration is open, so raw user-count quorum is weak —
quorum counts age/approval-filtered accounts.

Implementation (this commit): `feedback_votes` table (UNIQUE(audit_id,
user_id), re-vote overwrites) mirrored from the two audit-feedback endpoints
(message 👍/👎 is not mined, so it votes nothing); `get_pattern_support`
(distinct-user supports/contradicts); `user_reputation` (agreement rate on
decided patterns, 1.0 neutral); `FEEDBACK_DAILY_CAP=50` enforced at the
endpoints (429); feeder contradiction freeze (reputable contradictors +
supports < 2 → `pending_review`, reason `frozen_contradiction`) — reputation
is consumed as the freeze gate. Single-user flows never freeze (no
contradictors). Residuals: account-age filter not implemented (would freeze
young instances — documented future gate); full adaptive weighting on add
(not just freeze) is future work.

## Phase 4 — Admin review queue UI
Surface frozen/contested patterns (wired to the feeder's pending-review)
in the admin panel: approve/reject, reputation visible to admin only.
