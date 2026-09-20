# Known Limitations

> Updated as each phase lands. See `IMPLEMENTATION_PLAN.md` for the full phase plan and its
> consolidated list of open decisions.

## Current phase: 3 — Patient State (symptom extraction)

- **LLM provider decided (OpenAI) but no API key supplied yet.** `app/providers/llm/
  openai_provider.py` fails closed with a clear `LLM_ERROR` (HTTP 503) rather than fabricating a
  response — verified both in tests and live against the running dev server. The extraction
  pipeline itself is fully implemented and tested against a `FakeLLMProvider`
  (`backend/tests/fakes.py`), but **a real call to the OpenAI API has never been made** — that
  can only be verified once `OPENAI_API_KEY` is set in `.env`. See `docs/AI_PIPELINE.md`.
- Symptom extraction (`POST /symptoms/extract`) is a separate, explicit call — not triggered
  automatically by sending a message — so Phase 2's conversation flow keeps working with no LLM
  configured, per "preserve existing functionality when implementing later phases."
  `app/patient_state/assembler.py` assembles the canonical `patient_state.schema` from the DB on
  demand (never stored as one blob); `vitals` stays `{}` (Phase 9), `recent_events`/
  `risk_factors` stay `[]` (that's clinical inference, out of scope until Phase 4/6).
- No medical reasoning exists yet (by design — real reasoning starts Phase 4/6). The Phase 2
  assistant reply is still just a labeled echo scaffold (`backend/app/conversation/
  stub_reply.py`); Phase 3 only adds structured extraction alongside it, not a smarter reply.
- Mobile doesn't call `/symptoms/extract` yet — that's Phase 4 (conversation_manager) work,
  wiring extraction into the live conversation loop and using the result to drive follow-up
  questions.
- Mobile's auth is a **device-bootstrapped placeholder** — `ApiClient` auto-registers a random
  per-device account on first use (no real login/consent screen exists yet; that's Phase 1
  mobile work, still not built). See `mobile/README.md`.
- **STT decision made**: on-device/browser-native speech recognition via Flutter's
  `speech_to_text` package, not a cloud vendor. The backend has no server-side STT
  implementation. See `mobile/README.md`.
- Dev-only CORS (`allow_origins=["*"]`) on the backend — must be locked down before any real
  deployment (Phase 13).
- Backend connects to Postgres (pgvector/pgvector:pg16 via docker-compose). The `pgvector`
  extension itself is not yet created; deferred to Phase 5.
- Auth, patient profile, medical history, allergies, and current medications have working CRUD
  APIs with per-user access control, application-level encryption at rest for sensitive columns
  (now including conversation and symptom content), and audit logging — see `docs/API.md`,
  `docs/DATABASE.md`, `docs/SECURITY.md`.
- A `consents` table was added beyond `medai_spec.yaml`'s explicit `database.tables` list, to
  satisfy `security.consent_record_fields` — flagged in `IMPLEMENTATION_PLAN.md` and
  `docs/DATABASE.md`.
- Mobile app is scaffolded (Flutter 3.47.5). Android SDK and Xcode are not installed, so **web
  (Chrome) is the only verified-working target on this machine** — see `mobile/README.md`.
  Mobile platform scope (Android-only vs Android+iOS) is still an open decision.
- No concrete provider chosen yet for STT (backend-side)/TTS/embeddings/vector store/medical
  knowledge source/medication database. See `IMPLEMENTATION_PLAN.md`'s consolidated decisions
  list (LLM is now resolved: OpenAI).
- No formal compliance posture (HIPAA/GDPR-equivalent or explicit non-claim) has been adopted;
  in the interim, all patient data (including conversation and symptom content) is handled as if
  it were regulated health data — see `docs/SECURITY.md`.
- This is a prototype. It is not a licensed medical device, not a diagnostic system, and must
  never be presented as either (`medai_spec.yaml` `system_disclaimers`).
