# Known Limitations

> Updated as each phase lands. See `IMPLEMENTATION_PLAN.md` for the full phase plan and its
> consolidated list of open decisions. Older phases' full verification detail lives in git
> history for this file; this doc keeps a condensed summary once a newer phase supersedes it.

## Provider/source decisions (user-supplied, with references)

- **LLM**: **Gemini**, via the official `google-genai` SDK's async Interactions API —
  https://ai.google.dev/gemini-api/docs. Originally OpenAI (kept as a second working
  `LLMProvider` implementation, `app/providers/llm/openai_provider.py`, not selected). Model:
  `gemini-3.7-flash` (`GEMINI_MODEL` env var). Key supplied and verified live across most
  phases. **Correction to an earlier claim in this file**: switching model id does *not*
  reliably grant a fresh 20-request daily quota — `gemini-3.7-flash` hit its own `429` after
  only ~5 requests, having never been used before that. The free tier appears to enforce some
  smaller cap shared across models under the same key/project, not a clean independent bucket
  per model id as previously stated here. Four model ids have now been rate-limited in one day
  (`gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.7-flash`; `gemini-2.5-flash` separately
  turned out to be deprecated, not rate-limited). Switching models is not a reliable way to get
  more real calls — a paid tier or waiting for a reset is.
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
- **Health platform**: **Google Health Connect** (Phase 10). Chosen over Fitbit/Withings (both
  cloud APIs, backend-testable, but need a developer account + real device/sandbox data this
  session didn't have) and Apple HealthKit (no environment on this Windows machine to build
  against). Health Connect has no cloud endpoint at all — it's Android on-device only, readable
  solely by the app installed on that device — so `app/providers/devices/base.py`'s
  `DeviceAdapter` couldn't be implemented for it in Python; the real adapter is
  `mobile/lib/services/health_connect_adapter.dart`, via the `health` package
  (https://pub.dev/packages/health, v13.3.2). See `docs/AI_PIPELINE.md` for the full account,
  including the Android SDK/emulator setup this phase required from scratch.
- **Safety threshold references** (Phase 7, done for vitals; verification method noted per
  source since two of the four pages block automated fetching):
  - AHA heart rate: https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/all-about-heart-rate-pulse — page returns HTTP 403 to automated fetch; standard AHA figures (60-100 bpm normal) corroborated via a direct fetch of Cleveland Clinic's heart-rate page and other reputable sources citing the same guideline.
  - AHA blood pressure: https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings — same 403 situation; standard AHA/ACC categories corroborated the same way.
  - WHO pulse oximetry manual: https://cdn.who.int/media/docs/default-source/patient-safety/pulse-oximetry/who-ps-pulse-oxymetry-training-manual-en.pdf — **direct primary-source fetch succeeded**; exact thresholds quoted in `app/safety/vital_rules.py`.
  - NIH/MedlinePlus body temperature: https://medlineplus.gov/ency/article/001982.htm — **direct fetch succeeded**; exact quote in `app/safety/vital_rules.py`. No dangerous-fever/hypothermia threshold is stated on this page, so none is encoded as a rule.

## Current phase: 10 — Health Platform Integration

- **`POST /vitals/sync` is now live** (`app/api/vitals.py`) — the real ingestion path for
  health-platform data, backed by a genuinely new Android environment stood up specifically for
  this phase (Android SDK, an emulator with Health Connect, Windows Developer Mode for native
  plugin builds — none of this existed on this machine before). See `docs/AI_PIPELINE.md` for
  the full walkthrough, including the platform decision and its testability trade-offs.
- **`DeviceAdapter` (`app/providers/devices/base.py`) still has no Python implementation, and
  never will for Health Connect specifically** — a real architectural finding, not a shortcut:
  Health Connect has no cloud endpoint, so a backend-callable `read()` adapter can't reach it at
  all. The real adapter is client-side (`mobile/lib/services/health_connect_adapter.dart`); the
  Python ABC remains what a future cloud-platform adapter (Fitbit, Withings) would implement.
- **Four real bugs found and fixed while wiring this together** (all detailed in
  `docs/AI_PIPELINE.md`): the `health` plugin needs `FlutterFragmentActivity`, not
  `FlutterActivity`; Kotlin's incremental compiler crashes across a `C:`/`E:` drive boundary on
  Windows; Health Connect requires blood pressure as one combined write, not two; and — the most
  consequential one — mobile's device-bootstrap email domain (`@device.local`) was silently
  rejected by the backend's email validator the whole time, blocking any real mobile-to-backend
  call before this phase (fixed to `@example.com`).
- **Verified live, real device data the whole way through**: seeded real Health Connect records,
  synced them via the app's real "Sync Health Connect data" button, confirmed `200 OK` with all
  7 readings accepted, confirmed the exact values (including a correct Celsius→Fahrenheit
  conversion) in the dev DB, and confirmed the same deterministic safety-engine chain Phase 9
  proved for manual entry now also produces a correct `MODIFY` decision
  (`VITAL_BP_STAGE1_001` + `VITAL_SPO2_LOW_001`) for Health Connect-sourced data, using Phase 7's
  rules completely unmodified — the "clinical engine must not depend on a specific wearable"
  requirement, demonstrated rather than assumed.
- **Known gaps, stated plainly**: no automated integration test for the Health Connect
  unavailable/permission-denied path yet (exercised manually, not in CI); Apple HealthKit,
  Fitbit, and Withings remain unimplemented (see "Provider/source decisions" above for why);
  background/automatic sync doesn't exist — only the explicit button — matching this phase's
  decided MVP scope, not an oversight; the medication cross-check gap from Phase 8 is unchanged.

## Phase 9 — Vital Ingestion (superseded above for the health-platform path)

Manual-entry vital ingestion (`POST /vitals`, `GET /vitals`, `GET /vitals/history`) with the
full `vital_system.validation_stages` pipeline (`app/vitals/validation.py`), persisting every
submission to `measurements` (audit trail, including rejected ones) and upserting an accepted,
non-backdated reading into `vitals`. Validation sanity bounds are deliberately generous — they
catch garbage input, not clinical severity, which stays exclusively Phase 7's job; a genuinely
critical real reading (SpO2 86%) is accepted, not rejected, and verified live to correctly drive
`POST /assessment`'s safety-engine call to `ESCALATE` via `VITAL_SPO2_EMERGENCY_001`. 132/132
tests as of Phase 9 (more added in Phase 10, now 134/134 backend + 5/5 mobile, see above).

## Phase 8 — Output Validator, `POST /assessment` wired up (superseded above for vitals)

- **`POST /assessment` chains Phase 3/5/6/7/8 together**: `build_patient_state` →
  `build_evidence_package` → `evaluate_safety` → `get_validated_output`. Always returns `200`
  with an `Assessment` body — `SAFE_FALLBACK` included, since that's a legitimate response, not
  an error. 112/112 tests as of Phase 8 (auth, ownership 404, a fakes-driven grounded happy
  path, and the not-configured→`SAFE_FALLBACK` path); more added in Phase 9 (now 132/132, see
  below).
- **Known gap, stated plainly, still open**: the endpoint never cross-checks its own proposed
  medications against medication safety — `Assessment.medication_information` is free text, not
  a structured drug-name list, and no reliable extractor exists yet.
  `check_medication_validation` still runs but has nothing to compare against here. See
  `docs/AI_PIPELINE.md`.
- **The request-timeout fix has been verified live.** `GeminiProvider`'s 30s-per-call timeout
  works: a real rate-limited request correctly failed both `generate_assessment` retry attempts
  within the expected bound and `get_validated_output` correctly logged "failing closed with
  safe fallback." Worst-case total latency for this endpoint (2 reasoning attempts × up to 2
  `generate_assessment` calls in the correction path, each up to 30s) can legitimately approach
  2 minutes when every attempt fails — easy to exceed with a shorter client-side timeout. Any
  client of `POST /assessment` (including the mobile app, eventually) should use a generous
  timeout (2+ minutes) or expect to reduce `max_attempts`/`max_correction_attempts` if lower
  worst-case latency is wanted.
- **Two clean live successes were also confirmed**: a patient with no data → a real,
  appropriately-hedged "insufficient information" `Assessment` (not the fallback — genuine
  model output), fast, first try; a patient with real extracted symptoms and real ingested
  evidence → a real `200 OK` (confirmed via the server's access log).
- **Output-validator internals**: 10 spec-defined checks, a bounded correction retry, and a
  fail-closed safe fallback — verified live in an earlier run with a real, unplanned rate-limit
  failure exercising the fail-closed path for real (full transcript in `docs/AI_PIPELINE.md`).
- **Gemini's free-tier quota (20 requests/day) is not reliably tracked per model id** — a
  correction to what this file previously said here. Four model ids have now been rate-limited
  in one day; switching models is not a reliable way to get more real calls. See "Provider/source
  decisions" above for the up-to-date version of this claim — this entry is kept only as a
  historical record of what Phase 8's live testing first suggested, before Phase 9's further
  testing contradicted it.

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
- Mobile app is scaffolded (Flutter 3.47.5). As of Phase 10, an Android SDK + emulator (API 34)
  were installed specifically to build and live-verify the Health Connect integration — **Android
  is now a verified-working target** (real APK built, installed, and run on a real Android
  runtime), alongside web (Chrome). Xcode/macOS still don't exist on this machine, so iOS remains
  unverified. Mobile platform scope (Android-only vs Android+iOS) is still an open decision.
- `POST /messages` conducts a structured interview (Phase 4) working with or without an LLM
  configured. `emergency_indicators`/`required_measurements` question tiers are still
  unpopulated — Phase 7's sourced emergency rules and Phase 9's real vitals both now exist, but
  neither is wired into `app/conversation/` yet, only into `/assessment`. Mobile doesn't call
  `/symptoms/extract`, so `high_impact_missing_information` never triggers in the live mobile
  flow. Mobile *does* now call `/vitals/sync` (Phase 10's "Sync Health Connect data" button), but
  that's a standalone action, not wired into the conversation loop either.
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
