# Known Limitations

> Updated as each phase lands. See `IMPLEMENTATION_PLAN.md` for the full phase plan and its
> consolidated list of open decisions.

## Current phase: 1 — Patient Data (backend done; mobile blocked)

- No AI features exist yet (by design — AI reasoning starts Phase 3+).
- Backend connects to Postgres (pgvector/pgvector:pg16 via docker-compose) — verified via a live
  SQLAlchemy connection. The `pgvector` extension itself is not yet created (`CREATE EXTENSION
  vector;`); that's deferred to Phase 5 when `knowledge_chunks.embedding` is introduced.
- Auth, patient profile, medical history, allergies, and current medications now have working
  CRUD APIs with per-user access control, application-level encryption at rest for sensitive
  columns, and audit logging — see `docs/API.md`, `docs/DATABASE.md`, `docs/SECURITY.md`.
- A `consents` table was added beyond `medai_spec.yaml`'s explicit `database.tables` list, to
  satisfy `security.consent_record_fields` (which names required fields but no table) — flagged
  in `IMPLEMENTATION_PLAN.md` audit notes and `docs/DATABASE.md`.
- Mobile app is now scaffolded (Flutter 3.47.5, installed to `C:\src\flutter`) — `flutter
  analyze`, `flutter test`, and `flutter build web` all pass. Only a Phase 0 placeholder screen
  exists so far; Phase 1's manual-entry screens (consent, onboarding, profile, history,
  allergies, medications) are not built yet. Android SDK and Xcode are not installed, so **web
  (Chrome) is the only verified-working target on this machine** — see `mobile/README.md`.
  Mobile platform scope (Android-only vs Android+iOS) is still an open decision.
- No concrete AI/data provider (LLM, STT, TTS, embeddings, vector store, medical knowledge
  source, medication database) has been chosen. See `IMPLEMENTATION_PLAN.md`'s consolidated
  decisions list.
- No formal compliance posture (HIPAA/GDPR-equivalent or explicit non-claim) has been adopted;
  in the interim, all patient data is handled as if it were regulated health data — see
  `docs/SECURITY.md`.
- This is a prototype. It is not a licensed medical device, not a diagnostic system, and must
  never be presented as either (`medai_spec.yaml` `system_disclaimers`).
