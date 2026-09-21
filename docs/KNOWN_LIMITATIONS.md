# Known Limitations

> Updated as each phase lands. See `IMPLEMENTATION_PLAN.md` for the full phase plan and its
> consolidated list of open decisions. Older phases' full verification detail lives in git
> history for this file; this doc keeps a condensed summary once a newer phase supersedes it.

## Provider/source decisions (user-supplied, with references)

- **LLM**: **Gemini**, via the official `google-genai` SDK's async Interactions API —
  https://ai.google.dev/gemini-api/docs. Originally OpenAI (kept as a second working
  `LLMProvider` implementation, `app/providers/llm/openai_provider.py`, not selected). Model:
  `gemini-3.6-flash` (`GEMINI_MODEL` env var; changed from `gemini-3.8-flash` after hitting its
  free-tier cap — the quota is tracked per model id, so switching bought a fresh quota, not a
  bigger one; `gemini-3.6-flash` has since also been exhausted). Key supplied and verified live
  (Phases 3, 4, 6, 8).
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

## Current phase: 8+ — Output Validator, then `POST /assessment` wired up

- **`POST /assessment` is now live** (`app/api/assessment.py`) — the first endpoint allowed to
  return clinical-shaped output, chaining Phase 3/5/6/7/8 together for real:
  `build_patient_state` → `build_evidence_package` → `evaluate_safety` (`vitals={}` — Phase 9
  doesn't exist) → `get_validated_output`. Always returns `200` with an `Assessment` body —
  `SAFE_FALLBACK` included, since that's a legitimate response, not an error. 112/112 tests
  (4 new) cover auth, ownership (404), a fakes-driven grounded happy path, and the
  not-configured→`SAFE_FALLBACK` path.
- **Known gap, stated plainly**: the endpoint never cross-checks its own proposed medications
  against medication safety — `Assessment.medication_information` is free text, not a
  structured drug-name list, and no reliable extractor exists yet. `check_medication_validation`
  still runs but has nothing to compare against here. See `docs/AI_PIPELINE.md`.
- **A real operational bug was found and fixed**: `GeminiProvider` had no request timeout, so a
  rate-limited call could hang for minutes instead of failing fast into the already-designed
  retry/fallback path. Fixed with an explicit 30s timeout on every Gemini call. Confirmed the
  SDK accepts it; **not yet re-verified end-to-end live** — today's Gemini quota was already
  exhausted across three model ids (`gemini-3.8-flash`, `gemini-3.6-flash`, plus
  `gemini-2.5-flash` which turned out to be deprecated) by the time this was found. A live
  end-to-end `/assessment` call with a working key is still owed.
- **Output-validator internals** (Phase 8, still accurate): 10 spec-defined checks, a bounded
  correction retry, and a fail-closed safe fallback — verified live in an earlier run with a
  real, unplanned rate-limit failure exercising the fail-closed path for real (full transcript
  in `docs/AI_PIPELINE.md`).
- **Gemini's free-tier quota (20 requests/day) is tracked per model id**, not per key —
  switching model buys a fresh quota, not a bigger one. Expect to hit this again with enough
  live testing on any single free-tier model; a paid tier removes it.

## Phase 7 — Safety Engine & Medication Safety (internal capability only)

Deterministic vital-threshold engine (sourced from AHA/WHO/MedlinePlus) + openFDA-backed
medication safety pipeline, both verified live: real drug lookups correctly blocked an
allergen and flagged a real interaction + boxed warning for review; combined with abnormal
vitals, correctly escalated and logged to `safety_events`. Medication matching is literal
substring text-matching against label prose (not a structured interaction graph) — documented
limitation: misses drug-class allergies and word-form mismatches, always errs toward
blocking/review rather than a silent allow. No `safety_rules` DB table (version-controlled
Python list instead, see `docs/DATABASE.md`). `evaluate_safety()` is reachable via
`POST /assessment` now (see above); `check_candidate_medication()` still isn't called from
there (the known medication-cross-check gap).

## Phase 6 — Clinical Reasoning (internal capability only)

Verified live against real Gemini: a real evidence package produced a schema-valid `Assessment`
grounded in real retrieved evidence, passing both defense-in-depth checks on the first attempt.
Reachable via `POST /assessment` now (see above), always through `get_validated_output()`, never
called standalone. Also fixed a test-hermeticity bug here: once a
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
