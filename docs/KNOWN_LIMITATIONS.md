# Known Limitations

> Updated as each phase lands. See `IMPLEMENTATION_PLAN.md` for the full phase plan and its
> consolidated list of open decisions.

## Current phase: 4 — Conversation Manager

- **`POST /messages` now conducts a structured interview** (`app/conversation/manager.py` +
  `missing_info.py`): it asks the highest-priority missing item per
  `conversation_manager.question_priority`, deterministically, working with or without an LLM
  configured (LLM is used only for optional natural phrasing, with a template fallback).
  Verified: 35/35 backend tests, plus a two-turn live smoke test against the running dev
  server showing the interview correctly advance from an allergy question to a medications
  question once the allergy was answered.
  `emergency_indicators` and `required_measurements` question tiers are **not yet populated** —
  no item-generator exists for them (see `docs/AI_PIPELINE.md`): real emergency detection needs
  sourced, authoritative rules (Phase 7's `safety_engine.emergency_triage`), and measurement
  questions need the vital/device subsystem (Phase 9). Neither is invented here.
  `RUN_ASSESSMENT`/`ESCALATE`/`GET_VITAL`/`RETRIEVE_EVIDENCE` are recognized as valid
  `permitted_actions` by the arbiter but explicitly rejected (`NotImplementedError`) until
  Phase 5/6/7/9 exist.
- **LLM provider decided (OpenAI) but still no API key supplied.** Symptom extraction
  (`POST /symptoms/extract`) still fails closed with `LLM_ERROR` as before. The conversation
  manager degrades gracefully to templated questions in the same situation — this is by design,
  not a workaround.
- Phase 2's stub echo reply (`app/conversation/stub_reply.py`) has been removed and replaced by
  the conversation manager, exactly as that module's own docstring said it would be in Phase 4.
- Mobile doesn't call `/symptoms/extract` at all yet, so the `high_impact_missing_information`
  tier (asking about severity/duration/onset of an already-reported symptom) never triggers in
  the current end-to-end mobile flow — only the profile/allergy/history/demographics tiers do.
  Wiring extraction into the live conversation loop is a reasonable Phase 4/5 follow-up, not
  required for this phase's pass criterion ("AI can conduct a structured symptom interview").
- Mobile's auth is still a **device-bootstrapped placeholder** (no real login/consent screen —
  Phase 1 mobile work). See `mobile/README.md`.
- **STT decision made**: on-device/browser-native speech recognition via Flutter's
  `speech_to_text` package, not a cloud vendor.
- Dev-only CORS (`allow_origins=["*"]`) on the backend — must be locked down before any real
  deployment (Phase 13).
- Backend connects to Postgres (pgvector/pgvector:pg16 via docker-compose). The `pgvector`
  extension itself is not yet created; deferred to Phase 5.
- Auth, patient profile, medical history, allergies, current medications, conversations,
  messages, and symptoms all have working CRUD/APIs with per-user access control,
  application-level encryption at rest for sensitive columns, and audit logging.
- A `consents` table was added beyond `medai_spec.yaml`'s explicit `database.tables` list, to
  satisfy `security.consent_record_fields` — flagged in `IMPLEMENTATION_PLAN.md` and
  `docs/DATABASE.md`.
- Mobile app is scaffolded (Flutter 3.47.5). Android SDK and Xcode are not installed, so **web
  (Chrome) is the only verified-working target on this machine**. Mobile platform scope
  (Android-only vs Android+iOS) is still an open decision.
- No concrete provider chosen yet for backend-side STT/TTS/embeddings/vector store/medical
  knowledge source/medication database. See `IMPLEMENTATION_PLAN.md`'s consolidated decisions
  list (LLM is resolved: OpenAI, key pending).
- No formal compliance posture (HIPAA/GDPR-equivalent or explicit non-claim) has been adopted;
  in the interim, all patient data is handled as if it were regulated health data.
- This is a prototype. It is not a licensed medical device, not a diagnostic system, and must
  never be presented as either (`medai_spec.yaml` `system_disclaimers`).
