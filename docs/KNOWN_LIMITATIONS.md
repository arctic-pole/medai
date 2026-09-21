# Known Limitations

> Updated as each phase lands. See `IMPLEMENTATION_PLAN.md` for the full phase plan and its
> consolidated list of open decisions. Older phases' full verification detail lives in git
> history for this file; this doc keeps a condensed summary once a newer phase supersedes it.

## Provider/source decisions (user-supplied, with references)

- **LLM**: **Gemini**, via the official `google-genai` SDK's async Interactions API —
  https://ai.google.dev/gemini-api/docs. Originally OpenAI (kept as a second working
  `LLMProvider` implementation, `app/providers/llm/openai_provider.py`, not selected). Model:
  `gemini-3.8-flash` (`GEMINI_MODEL` env var). Key supplied and verified live (Phases 3, 4, 6).
- **STT**: `speech_to_text` (pub.dev) — https://pub.dev/packages/speech_to_text (Phase 2, done)
- **TTS**: `flutter_tts` (pub.dev) — https://pub.dev/packages/flutter_tts (Phase 11, not built)
- **Embeddings**: `BAAI/bge-large-en-v1.5` via `sentence-transformers`, self-hosted —
  https://huggingface.co/BAAI/bge-large-en-v1.5 / https://www.sbert.net/. No API key. (Phase 5)
- **Vector store**: pgvector — https://github.com/pgvector/pgvector, the same Postgres
  instance. (Phase 5)
- **Medical knowledge sources**:
  - MedlinePlus (government_health_guidance) — https://medlineplus.gov/webservices.html —
    wired in, Phase 5 (`app/providers/medical_knowledge/medlineplus_provider.py`)
  - openFDA (official_drug_labels / medication_safety's MEDICATION_DB) —
    https://open.fda.gov/apis/drug/label/ — wired in, Phase 7
    (`app/providers/medication_db/openfda_provider.py`)
  - PubMed Central (peer_reviewed_literature) — https://www.ncbi.nlm.nih.gov/books/NBK25501/ —
    approved but **not yet wired in**
- **Safety threshold references** (Phase 7, done for vitals; verification method noted per
  source since two of the four pages block automated fetching):
  - AHA heart rate: https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/all-about-heart-rate-pulse — page returns HTTP 403 to automated fetch; standard AHA figures (60-100 bpm normal) corroborated via a direct fetch of Cleveland Clinic's heart-rate page and other reputable sources citing the same guideline.
  - AHA blood pressure: https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings — same 403 situation; standard AHA/ACC categories corroborated the same way.
  - WHO pulse oximetry manual: https://cdn.who.int/media/docs/default-source/patient-safety/pulse-oximetry/who-ps-pulse-oxymetry-training-manual-en.pdf — **direct primary-source fetch succeeded**; exact thresholds quoted in `app/safety/vital_rules.py`.
  - NIH/MedlinePlus body temperature: https://medlineplus.gov/ency/article/001982.htm — **direct fetch succeeded**; exact quote in `app/safety/vital_rules.py`. No dangerous-fever/hypothermia threshold is stated on this page, so none is encoded as a rule.

## Current phase: 7 — Safety Engine & Medication Safety (internal capability only)

- **Same scoping as Phase 6, same reason**: no API endpoint. `architecture.bypass_forbidden`
  names `safety_engine` explicitly; `output_validator` (Phase 8) doesn't exist yet for an
  endpoint to hand a decision to. `evaluate_safety()`/`check_candidate_medication()` are called
  directly by tests and a live-verification script.
- **Verified live, not just against fakes**: three real openFDA lookups against a real
  patient — `penicillin` (recorded allergy) → `BLOCKED`; `warfarin` (patient takes aspirin) →
  `REQUIRES_REVIEW`, correctly citing both the real drug-interactions text and warfarin's real
  FDA boxed warning; `acetaminophen` → `ALLOWED`. Then `evaluate_safety()` with real vitals
  (SpO2 86%, HR 118) plus those findings correctly triggered the SpO2-emergency and
  tachycardia rules, decided `ESCALATE`, and logged 4 rows to `safety_events` (confirmed by
  querying the dev DB); normal vitals + no findings correctly gave `PASS` and logged nothing.
  Full output in `docs/AI_PIPELINE.md`.
- **Medication-matching is literal-substring text matching**, not a structured interaction
  engine (openFDA doesn't expose one) — a real limitation found while writing tests: it
  correctly blocks "penicillin" for a "penicillin" allergy but does *not* catch a drug-class
  allergy ("amoxicillin" vs. a "penicillin" allergy) or a word-form mismatch ("pregnancy" vs.
  "pregnant"). Always errs toward `BLOCKED`/`REQUIRES_REVIEW`, never a silent `ALLOWED`, but a
  false negative is still possible. `dosage_validity` isn't implemented (no proposed dose in
  the input). See `docs/AI_PIPELINE.md`.
- **No `safety_rules` DB table** — rules live as a version-controlled Python list
  (`app/safety/vital_rules.py`), not admin-editable data. See `docs/DATABASE.md`.
- Vital-threshold rules exist but nothing feeds them real vitals yet (Phase 9 doesn't exist);
  they're exercised today via explicit `vitals` dict arguments in tests/the demo script.
- Not persisted to `recommendations`/`recommendation_evidence` (same reasoning as Phase 6: an
  unvalidated result isn't a vetted recommendation yet).

## Phase 6 — Clinical Reasoning (internal capability only)

Verified live against real Gemini: a real evidence package (headache symptom + 5 retrieved
MedlinePlus passages) produced a schema-valid `Assessment` — accurate known/unknown info,
appropriate hedged red-flag warning, `confidence: "low"`, two evidence citations whose
`source_id`s were genuinely in the evidence given — passing both defense-in-depth checks
(grounding + forbidden-language) on the first attempt. No API endpoint (see Phase 7 above for
why); not persisted to `recommendations` tables. Also fixed a test-hermeticity bug here: once a
real `GEMINI_API_KEY` existed, tests that didn't explicitly mock the LLM started making live
API calls — `backend/tests/conftest.py` now force-blanks LLM API keys for the test process
regardless of `.env` content.

## Phase 5 — Medical Knowledge (RAG)

`POST /evidence/ingest`/`GET /evidence` are real: ingesting "headache" pulls real MedlinePlus
articles; querying with the real embedding model correctly ranks the most relevant passage
first, with full source traceability. Not yet wired into the conversation loop
(`RETRIEVE_EVIDENCE` stays rejected until Phase 6's reasoner is actually wired in end-to-end).
Reranking is a no-op (plain cosine-similarity order) — no reranker model was specified.

## Standing items (all phases)

- Mobile's auth is a **device-bootstrapped placeholder** (no real login/consent screen — Phase
  1 mobile work, still not built). See `mobile/README.md`.
- Mobile app is scaffolded (Flutter 3.47.5). Android SDK and Xcode are not installed, so **web
  (Chrome) is the only verified-working target on this machine**. Mobile platform scope
  (Android-only vs Android+iOS) is still an open decision.
- `POST /messages` conducts a structured interview (Phase 4) working with or without an LLM
  configured. `emergency_indicators`/`required_measurements` question tiers are still
  unpopulated (need real vitals/sourced emergency rules wired in, not just existing in
  isolation). Mobile doesn't call `/symptoms/extract`, so `high_impact_missing_information`
  never triggers in the live mobile flow.
- Dev-only CORS (`allow_origins=["*"]`) on the backend — must be locked down before any real
  deployment (Phase 13).
- A `consents` table was added beyond `medai_spec.yaml`'s explicit `database.tables` list, to
  satisfy `security.consent_record_fields` — flagged in `IMPLEMENTATION_PLAN.md` and
  `docs/DATABASE.md`.
- No concrete provider chosen yet for backend-side TTS.
- No formal compliance posture (HIPAA/GDPR-equivalent or explicit non-claim) has been adopted;
  in the interim, all patient data is handled as if it were regulated health data.
- This is a prototype. It is not a licensed medical device, not a diagnostic system, and must
  never be presented as either (`medai_spec.yaml` `system_disclaimers`).
