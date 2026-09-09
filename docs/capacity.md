# Capacity guide

piSynapse is a single-user-first home server that now supports multiple
users. This note tells you where the ceilings are and which knobs move them.
Concurrency figures below are engineering estimates, not benchmarks — measure
on your own hardware (watch p95 chat latency under load) before promising
anything.

## The bottleneck is inference, not the database

- One model engine serves all users (`litert_serve`, single process). Chat
  turns queue behind each other; long generations block the queue.
- The SQLite layer (WAL + busy retry + per-loop write serialization) handles
  home-scale concurrency comfortably — writes are millisecond-scale, reads
  never block writers.
- Embeddings run locally per message (one-time cost, cached in vectors);
  background folds/summaries add one extra inference call per few turns.

## Practical ceilings

| Hardware | Model | Concurrent active chatters (est.) |
|---|---|---|
| Raspberry Pi 5, 8 GB | gemma4-e2b (2.5 GB) | 2–3 |
| x86 mini-PC, 16 GB+ | gemma4-e2b / e4b | 4–8 |
| Workstation, 32 GB+ | larger models | 8+ |

Idle users cost nothing (no polling loops hold the model; keep-alive only
holds RAM). "Active" means mid-generation. If p95 latency climbs, lower
concurrency before touching anything else.

## Knobs that move the ceiling

- `RATE_LIMIT_RPM` (30), `RATE_LIMIT_SESSION_RPM` (20),
  `RATE_LIMIT_PUBLIC_RPM` (120) — per-user / per-session / public buckets.
  Raise on bigger hardware; the session bucket is the per-chat fairness lever.
- `HISTORY_LIMIT` (12), `MEMORY_LIMIT` (10) — raw context per turn; smaller
  windows prefill faster on weak hardware.
- `SUMMARY_BATCH_SIZE` (5) + fold caps (30 msgs / 500 chars) — bound the
  summarizer's input regardless of backlog size.
- `conversation_cache_max` (litert side, default 0 = stateless) — reuses live
  conversations per `user:session` key when enabled; trades RAM for TTFT on
  repeat turns of the same session.
- `LLM_NUM_CTX` (8192), `LLM_MAX_OUTPUT_TOKENS` — context/output budgets;
  match them to what your RAM sustains alongside the model weights.

## Multi-user notes

- Every user gets their own API key (`POST /users/register`); never share
  keys between people or devices — per-user rate limits, memories, sessions
  and settings all key off it. One key per device is the recommended pattern.
- Registration is open by default; close it (`REGISTRATION_OPEN=off`) once
  the household is onboarded. First user is admin.
- Disk: conversations + FTS + embeddings grow ~1–2 MB per thousand
  turns; `backups/` keeps 7 daily generations; audit CSVs follow the
  retention window. Conversation/memory retention (`*_RETENTION_DAYS`,
  default 0 = keep forever) is the long-term disk lever.
