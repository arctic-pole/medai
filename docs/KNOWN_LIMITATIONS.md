# Known Limitations

> Updated as each phase lands. See `IMPLEMENTATION_PLAN.md` for the full phase plan and its
> consolidated list of open decisions.

## Current phase: 0 — Foundation (backend verified; mobile blocked)

- No AI features exist yet (by design — `medai_spec.yaml` `phases.0_foundation.constraint`).
- Backend connects to Postgres (pgvector/pgvector:pg16 via docker-compose) — verified via a live
  SQLAlchemy connection. The `pgvector` extension itself is not yet created (`CREATE EXTENSION
  vector;`); that's deferred to Phase 5 when `knowledge_chunks.embedding` is introduced.
- Mobile app is not yet scaffolded — the Flutter SDK was not available in the environment used
  to bootstrap this repo. See `mobile/README.md`.
- No concrete AI/data provider (LLM, STT, TTS, embeddings, vector store, medical knowledge
  source, medication database) has been chosen. See `IMPLEMENTATION_PLAN.md`'s consolidated
  decisions list.
- No compliance posture (HIPAA/GDPR-equivalent or explicit non-claim) has been adopted yet.
- This is a prototype. It is not a licensed medical device, not a diagnostic system, and must
  never be presented as either (`medai_spec.yaml` `system_disclaimers`).
