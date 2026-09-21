# Known Limitations

> Updated as each phase lands. See `IMPLEMENTATION_PLAN.md` for the full phase plan and its
> consolidated list of open decisions.

## Provider/source decisions (user-supplied, with references)

- **STT** (Phase 2, done): `speech_to_text` (pub.dev) — https://pub.dev/packages/speech_to_text
- **TTS** (Phase 11, not yet built): `flutter_tts` (pub.dev) — https://pub.dev/packages/flutter_tts
- **Embeddings** (Phase 5, done): `BAAI/bge-large-en-v1.5` via `sentence-transformers`,
  self-hosted — https://huggingface.co/BAAI/bge-large-en-v1.5 / https://www.sbert.net/. No API
  key needed.
- **Vector store** (Phase 5, done): pgvector — https://github.com/pgvector/pgvector (the
  Postgres image in `docker-compose.yml`; extension now actually enabled, see `docs/DATABASE.md`)
- **Medical knowledge sources**:
  - MedlinePlus (government_health_guidance) — https://medlineplus.gov/webservices.html —
    **wired in, Phase 5, done** (`app/providers/medical_knowledge/medlineplus_provider.py`)
  - PubMed Central (peer_reviewed_literature) — https://www.ncbi.nlm.nih.gov/books/NBK25501/ —
    approved but **not yet wired in**
  - openFDA (official_drug_labels / medication_safety's MEDICATION_DB) —
    https://open.fda.gov/apis/drug/label/ — approved but **not yet wired in** (natural fit for
    Phase 7's `MEDICATION_DB`, not Phase 5's general knowledge retrieval)
- **Safety threshold references** (for Phase 7/9, not yet built — recorded now so they aren't
  lost before those phases start):
  - AHA heart rate: https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/all-about-heart-rate-pulse
  - AHA blood pressure: https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings
  - WHO pulse oximetry manual: https://www.who.int/publications/i/item/9789241501132
  - NIH/MedlinePlus body temperature: https://medlineplus.gov/ency/article/001982.htm

## Current phase: 5 — Medical Knowledge (RAG)

- **`POST /evidence/ingest` and `GET /evidence` are real, not mocked.** Ingesting "headache"
  pulls real MedlinePlus articles (Headache, Migraine, Concussion); querying against them with
  the real `BAAI/bge-large-en-v1.5` model correctly ranks the most relevant passage first, with
  full source traceability (title, publisher, url, source_type, version, retrieval_date).
  Verified both with 43/43 fast tests (against fakes — no model load, no network) and a full
  live smoke test with real data. See `docs/AI_PIPELINE.md` for the exact query/result.
- **RAG is not yet wired into the conversation loop.** `POST /messages` (Phase 4's conversation
  manager) does not call `/evidence` — `RETRIEVE_EVIDENCE` is still explicitly rejected by
  `app/conversation/manager.py`'s action arbiter (`NotImplementedError`) until Phase 6's
  `clinical_reasoner` exists to actually consume retrieved evidence. Phase 5 only proves the
  retrieval pipeline itself works end-to-end, per its own pass criterion.
  PubMed Central and openFDA are approved sources not yet wired in (MedlinePlus only, so far).
- Reranking is a no-op today (same order pgvector's cosine similarity returns) — no reranker
  model was specified, so none was invented. See `docs/AI_PIPELINE.md`.
- **`POST /messages` conducts a structured interview** (`app/conversation/manager.py` +
  `missing_info.py`, Phase 4): the highest-priority missing item per
  `conversation_manager.question_priority`, deterministically, working with or without an LLM
  configured. `emergency_indicators` and `required_measurements` question tiers are still not
  populated (need Phase 7/9). Mobile doesn't call `/symptoms/extract`, so the
  `high_impact_missing_information` tier never triggers in the live mobile flow yet.
- **LLM provider decided (OpenAI) but still no API key supplied.** Symptom extraction
  (`POST /symptoms/extract`) still fails closed with `LLM_ERROR`.
- Mobile's auth is still a **device-bootstrapped placeholder** (no real login/consent screen —
  Phase 1 mobile work). See `mobile/README.md`.
- Dev-only CORS (`allow_origins=["*"]`) on the backend — must be locked down before any real
  deployment (Phase 13).
- Auth, patient profile, medical history, allergies, current medications, conversations,
  messages, symptoms, and clinical evidence all have working CRUD/APIs with per-user access
  control (where applicable), application-level encryption at rest for sensitive patient
  columns, and audit logging.
- A `consents` table was added beyond `medai_spec.yaml`'s explicit `database.tables` list, to
  satisfy `security.consent_record_fields` — flagged in `IMPLEMENTATION_PLAN.md` and
  `docs/DATABASE.md`.
- Mobile app is scaffolded (Flutter 3.47.5). Android SDK and Xcode are not installed, so **web
  (Chrome) is the only verified-working target on this machine**. Mobile platform scope
  (Android-only vs Android+iOS) is still an open decision.
- No concrete provider chosen yet for backend-side TTS or the medication database (openFDA is
  approved but not yet wired in — natural fit for Phase 7).
- No formal compliance posture (HIPAA/GDPR-equivalent or explicit non-claim) has been adopted;
  in the interim, all patient data is handled as if it were regulated health data.
- This is a prototype. It is not a licensed medical device, not a diagnostic system, and must
  never be presented as either (`medai_spec.yaml` `system_disclaimers`).
