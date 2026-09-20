# Known Limitations

> Updated as each phase lands. See `IMPLEMENTATION_PLAN.md` for the full phase plan and its
> consolidated list of open decisions.

## Current phase: 2 — Conversation

- No medical reasoning exists yet (by design — `phases.2_conversation.constraint`; real
  reasoning starts Phase 3+). The assistant reply is a labeled scaffold
  (`backend/app/conversation/stub_reply.py`) that only echoes the user's text back.
- Users can speak (or type — accessibility's `text_always_available`) to the mobile app via
  `ConversationScreen` and get a text response, round-tripping through real `/conversations` and
  `/messages` APIs. Verified: 18/18 backend tests (incl. cross-patient isolation and
  encryption-at-rest for message content) + a live `curl` smoke test against the dev server;
  2/2 Flutter tests + `flutter analyze` + `flutter build web`. The voice/STT path itself and a
  live browser↔backend click-through were **not** exercised by an automated test — no
  microphone or browser-automation harness in this environment.
- **STT decision made**: on-device/browser-native speech recognition via Flutter's
  `speech_to_text` package (Android `SpeechRecognizer` / iOS `Speech` / Web Speech API), not a
  cloud vendor — avoids an API-key/vendor decision for the prototype. The backend has no
  server-side STT implementation. See `mobile/README.md` for the rationale; flag if a cloud STT
  provider is wanted instead (e.g. for server-side audio processing).
- Mobile's auth is a **device-bootstrapped placeholder** — `ApiClient` auto-registers a random
  per-device account on first use (no real login/consent screen exists yet; that's Phase 1
  mobile work, still not built). See `mobile/README.md`.
- Dev-only CORS (`allow_origins=["*"]`) was added to the backend so the Flutter web client can
  reach it locally — must be locked down before any real deployment (Phase 13).
- Backend connects to Postgres (pgvector/pgvector:pg16 via docker-compose) — verified via a live
  SQLAlchemy connection. The `pgvector` extension itself is not yet created (`CREATE EXTENSION
  vector;`); that's deferred to Phase 5 when `knowledge_chunks.embedding` is introduced.
- Auth, patient profile, medical history, allergies, and current medications have working CRUD
  APIs with per-user access control, application-level encryption at rest for sensitive columns,
  and audit logging — see `docs/API.md`, `docs/DATABASE.md`, `docs/SECURITY.md`.
- A `consents` table was added beyond `medai_spec.yaml`'s explicit `database.tables` list, to
  satisfy `security.consent_record_fields` (which names required fields but no table) — flagged
  in `IMPLEMENTATION_PLAN.md` audit notes and `docs/DATABASE.md`.
- Mobile app is scaffolded (Flutter 3.47.5, installed to `C:\src\flutter`). Android SDK and
  Xcode are not installed, so **web (Chrome) is the only verified-working target on this
  machine** — see `mobile/README.md`. Mobile platform scope (Android-only vs Android+iOS) is
  still an open decision.
- No concrete AI/data provider (LLM, TTS, embeddings, vector store, medical knowledge source,
  medication database) has been chosen. See `IMPLEMENTATION_PLAN.md`'s consolidated decisions
  list.
- No formal compliance posture (HIPAA/GDPR-equivalent or explicit non-claim) has been adopted;
  in the interim, all patient data (including conversation content) is handled as if it were
  regulated health data — see `docs/SECURITY.md`.
- This is a prototype. It is not a licensed medical device, not a diagnostic system, and must
  never be presented as either (`medai_spec.yaml` `system_disclaimers`).
