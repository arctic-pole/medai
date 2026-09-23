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
- **TTS**: **pyttsx3** (PyPI) — https://pypi.org/project/pyttsx3/, offline, wraps the OS's
  native engine (SAPI5 on this Windows machine), no API key. Backend-side (`app/providers/tts/`),
  not the `flutter_tts` mobile-side plugin an earlier version of this doc named as the plan —
  synthesis happens server-side so the `ValidatedText` gate (`app/tts/schema.py`) can be
  enforced in one place in code, not trusted to every mobile client. Mobile plays the resulting
  audio via `audioplayers` (pub.dev) — https://pub.dev/packages/audioplayers. (Phase 11, done)
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

## Current phase: 14 — Evaluation

Full dataset/methodology detail lives in `docs/EVALUATION.md` (new this phase). Summary:

- **`backend/evaluation/dataset.py`**: 7 cases, one per `evaluation_dataset.schema.case_types`
  value, every non-trivial `expected_safety_state` traceable to an already-cited real source
  (AHA/WHO from `app/safety/vital_rules.py`, openFDA from `app/safety/medication.py`) — never a
  model guess, per the spec's own explicit rule. `backend/tests/integration/
  test_evaluation_dataset.py` (11 tests) runs every case through the real deterministic pipeline
  pieces (patient-state assembly, safety engine, medication safety — never fakes standing in for
  these specific pieces).
- **Safety metrics — real numbers, zero-tolerance gates only** (the open numeric-threshold
  decision the plan flagged; user's explicit choice this phase: "report actual numbers, gate
  only on zero-tolerance items," not an invented percentage):
  - `emergency_detection_sensitivity`: **1.0 (1/1)** — the one `ESCALATE`-expected case was
    detected.
  - `contraindication_detection`: **1.0 (1/1)** — the one `BLOCK`-expected case was detected.
  - `unsafe_recommendation_rate`: **0/7** — every case individually gated
    at-least-as-restrictive-as-expected (`test_case_matches_expected_safety_state`).
  - A dataset of 7 hand-built cases is too small for these ratios to mean much as *general*
    sensitivity/specificity claims — they document that this specific, sourced dataset passes
    with zero misses, not a clinically-validated accuracy figure. A larger dataset with a
    clinically-set graded threshold is future work, not invented here.
- **`backend/tests/unit/test_safety_adversarial_suite.py`** (7 tests): maps all 10
  `testing.safety_adversarial` categories to either existing coverage elsewhere or new tests
  here — contradictory vitals kept (not silently resolved), contradictory assessment output
  rejected, malformed AI output fails closed (not a crash), a hallucinated assessment with no
  real evidence is corrected then falls back to `SAFE_FALLBACK`, and a genuinely hedged
  low-confidence response is *not* penalized for having no evidence to cite.
- **`backend/tests/integration/test_e2e_conversation.py`** (1 test): a single, complete,
  real-HTTP conversation from a fresh patient's first message through every real follow-up
  question to a final validated `Assessment`, covering `testing.end_to_end`.
- **Real-Gemini generation-quality metrics: attempted, not obtained** (user's explicit choice
  this phase: "attempt real Gemini calls too," accepting the session's well-documented quota
  risk). `backend/evaluation/live_generation_check.py` drives all 7 dataset cases through the
  real `POST /messages` endpoint end-to-end with no provider overrides (real Gemini, real local
  embeddings). Run live against the dev DB: hit the same free-tier wall documented since Phase
  8 (20 requests/day, shared across model ids) after only a few cases — **0 of 7 cases produced
  a real generated `Assessment`; `generation_metrics` (`evidence_grounded_response_rate`,
  `unsupported_claim_rate`, `schema_compliance`) could not be measured live this session.**
  A real, separate bug was found and fixed in the process: 4 of the 7 dataset cases
  (`normal-001`, `contradictory-001`, `emergency-001`, `medication_conflict-001`) had an empty
  `medications=[]` with no matching `current_medications` entry in
  `expected_information_requirements` — internally inconsistent, since an empty list and "not
  yet answered" look identical to the conversation manager. Live, this made the manager
  correctly, endlessly re-ask the same medications question, burning through the day's quota on
  question-phrasing calls before a single case reached real assessment generation. Fixed by
  populating `medications=[{"name": "none"}]` on all 4 (matching a fix already applied to
  `ambiguous-001` earlier this phase for the identical root cause), and hardened
  `live_generation_check.py` to bail out of a case after two identical repeated questions rather
  than retrying blindly. The script itself is otherwise complete and ready to produce real
  numbers on a future run once the daily quota resets or a paid tier is used — see
  `docs/EVALUATION.md`.
- **209/209 backend tests** (19 new: 7 safety-adversarial, 1 end-to-end, 11 evaluation-dataset).

## Phase 13 — Security Hardening (superseded above for evaluation)

Full design and live-verification detail lives in `docs/SECURITY.md` (the dedicated doc this
phase expands fully, as planned since Phase 1). Summary:

- **A real, exploitable vulnerability found and fixed**: `JWT_SECRET_KEY` and
  `FIELD_ENCRYPTION_KEY` both had public, well-known placeholder defaults with nothing stopping
  a real deployment from silently running with them unchanged — anyone who read this
  (open-source) repo could have forged valid access tokens or decrypted every "encrypted at
  rest" column. `Settings` now refuses to start outside `environment=="development"` unless
  both have been changed to real values — verified live (a `production`-environment startup
  with the defaults fails immediately with a clear error; with real values, it succeeds).
- **Automated secret-scanning added to CI** (`gitleaks/gitleaks-action@v3`,
  `.github/workflows/secret-scan.yml`) — daily plus every push/PR. A manual history scan run
  first found nothing already leaked.
- **Access control**: audited all 13 routers (all correctly scoped); closed real test-coverage
  gaps (allergies/medications cross-user `DELETE`, which wasn't tested before — only `PATCH`
  was, and only for history) in a new consolidated `test_access_control.py`.
- **Input sanitisation — real gaps found and fixed**: roughly a dozen fields (`notes`,
  `reaction`, `dosage`, `emergency_contact_*`, `LoginRequest.password`, `VitalSyncRequest.
  readings`, and others) had no upper bound at all. The most concrete one: an unbounded login
  password let an *unauthenticated* caller force argon2 to hash an arbitrarily large input on
  every attempt — a real CPU-cost DoS vector, not theoretical. All fixed with explicit
  `max_length`s; the rejection behavior itself is tested, not just the field declaration.
- **Privacy controls (user-confirmed scope: both export and delete)**: `GET /privacy/export`
  (every table a patient's data lives in, one response) and `DELETE /privacy/me` (cascading,
  irreversible, password-reconfirmed deletion across every patient-owned table — audit logs
  deliberately excluded, see `docs/SECURITY.md` for why). Both verified live against a running
  dev server with real data, including confirming the old access token genuinely stops working
  after deletion and the freed email can be re-registered.
- **Dedicated prompt-injection adversarial test suite** (`tests/unit/test_prompt_injection.py`):
  proves, using recording fakes and a realistic injection payload, that untrusted content never
  reaches any of the three LLM `system` prompts — only ever the user/task prompt — at every call
  site this codebase has one; and separately proves the deterministic-safety-overrides-a-fooled-
  LLM defense-in-depth backstop, framed explicitly around injected text this time.
- **Audit logs**: behaviorally verified (not just by code inspection) that a genuinely sensitive
  value sent in a request never appears anywhere in `audit_logs`, and that `module` is built
  from the path only, never a query string.
- **Encryption**: audited coverage; found and disclosed one real gap — numeric vital values
  aren't encrypted at rest (only free-text fields are; encrypting a `Float` column needs a new
  type this phase didn't build). TLS documented as a concrete deployment requirement (no real
  deployment target exists to configure it against).
- **Known gaps, disclosed rather than silently left implicit**: no rate limiting on `/auth/
  login` (the per-attempt CPU-cost fix doesn't address attempt *count*); `ENVIRONMENT` still
  defaults to `"development"` if unset, so the CORS permissive-default risk (distinct from, and
  lower-severity than, the two secrets already guarded) wasn't independently fixed; no mobile UI
  for the new privacy endpoints (consistent with Phase 12's 13-deferred-screens scope decision).
- **190/190 backend tests** (38 new: 5 config-guard, 14 access-control, 3 audit-log, 6
  input-bounds, 5 privacy, 4 prompt-injection, plus one added case to the existing
  no-auth-required sweep).

## Phase 12 — Complete Pipeline (superseded above for its own security-relevant follow-ups)

Wired the full pipeline into the conversation loop itself: `POST /messages` now runs the real
assessment pipeline automatically once nothing more is missing, replacing a hardcoded
placeholder and the Phase 11 standalone "Get assessment" button — the conversation is the only
interface. Added session persistence (resumes the most recent conversation instead of always
starting over) and 1 of 5 `ux.confirmation_required_when` triggers
(`high_risk_recommendation_considered`, a modal non-dismissible dialog) — the other 4 honestly
deferred, no real detection signal or mobile surface exists for them. Scope decision
(user-confirmed): "core pipeline integration," not all 15 `ux.screens` — only 2 existed before
this phase, 13 remain deferred with their backend APIs already built. Verified live: a real HTTP
sequence correctly triggered the automatic pipeline in 0.3s; a real Gemini call separately
attempted took unusually long (well beyond the documented ~2-minute worst case, confirmed via
`netstat` as a genuine live connection, not a local hang) and wasn't root-caused further. 152/152
backend, 19/19 mobile tests as of this phase.

## Phase 11 — TTS (superseded above for the "Get assessment" button, which no longer exists)

`POST /assessment/speech` (`app/api/assessment.py`) — `voice_pipeline.flow`'s
`VALIDATED_TEXT → TTS → SPEAKER` step. `TextToSpeechProvider` (`app/providers/tts/`) is the
`architecture.provider_interfaces` abstraction; concrete choice is **pyttsx3** (offline, no API
key). "TTS must never receive unvalidated medical output" is enforced at the type level:
`ValidatedText` (`app/tts/schema.py`) can only be constructed via a sentinel-token-guarded
private factory, and `TextToSpeechProvider.speak()` requires that type. The only legitimate path
to one is `synthesize_validated_response()`, which always calls `get_validated_output()` itself
first rather than accepting a pre-built `Assessment`. Verified by test that `SAFE_FALLBACK`,
never rejected content, is what reaches TTS after a failed validation, and verified live with a
real `200 OK` returning a genuine 376KB WAV file. Mobile playback
(`speech_playback_service.dart`, via `audioplayers`) handles play/stop/barge-in and graceful
failure. As of Phase 12, the Play button lives on assessment messages inline in the
conversation, not behind a separate action.

## Phase 10 — Health Platform Integration (superseded above for TTS)

`POST /vitals/sync` (`app/api/vitals.py`) added real Google Health Connect ingestion. Health
Connect has no cloud endpoint, so `DeviceAdapter` (`app/providers/devices/base.py`) has no
Python implementation and never will for it specifically — the real adapter is client-side
(`mobile/lib/services/health_connect_adapter.dart`). Required standing up a real Android
SDK/emulator on this machine from scratch. Verified live with real device data: seeded records,
synced via the app's real button, confirmed correct values/units in the dev DB, and confirmed
the same deterministic safety-engine chain Phase 9 used produces a correct `MODIFY` decision for
Health-Connect-sourced data with zero changes to `clinical_reasoner`/`safety_engine` code. Four
real bugs found and fixed along the way, including a pre-existing, previously-undetected bug in
mobile's device-bootstrap email domain (`@device.local`, rejected by the backend's validator —
fixed to `@example.com`) — see git history for the full account. Apple HealthKit, Fitbit, and
Withings remain unimplemented; background/automatic sync doesn't exist, only the explicit
button (decided MVP scope).

## Phase 9 — Vital Ingestion (superseded above for the health-platform path)

Manual-entry vital ingestion (`POST /vitals`, `GET /vitals`, `GET /vitals/history`) with the
full `vital_system.validation_stages` pipeline (`app/vitals/validation.py`), persisting every
submission to `measurements` (audit trail, including rejected ones) and upserting an accepted,
non-backdated reading into `vitals`. Validation sanity bounds are deliberately generous — they
catch garbage input, not clinical severity, which stays exclusively Phase 7's job; a genuinely
critical real reading (SpO2 86%) is accepted, not rejected, and verified live to correctly drive
`POST /assessment`'s safety-engine call to `ESCALATE` via `VITAL_SPO2_EMERGENCY_001`. 132/132
tests as of Phase 9 (134/134 backend + 5/5 mobile as of Phase 10; now 150/150 backend + 15/15
mobile as of Phase 11, see above).

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
- `POST /messages` conducts a structured interview (Phase 4) and, once nothing more is missing,
  automatically runs the real assessment pipeline as the reply (Phase 12) — working with or
  without an LLM configured either way. `emergency_indicators`/`required_measurements` question
  *tiers* are still unpopulated in `identify_missing_info`'s priority order — Phase 7's sourced
  emergency rules and Phase 9's real vitals both now feed the assessment pipeline itself, but
  neither is used to decide *what question to ask next*. Mobile doesn't call
  `/symptoms/extract`, so `high_impact_missing_information` never triggers in the live mobile
  flow. Mobile also calls `/vitals/sync` (Phase 10's "Sync Health Connect data" button) as a
  standalone action, and `/assessment/speech` (Play/Stop on an assessment message) — the latter
  is now reached from *within* the conversation, not a separate action, as of Phase 12.
- Dev-only CORS (`allow_origins=["*"]`) on the backend, gated behind
  `ENVIRONMENT=="development"` — reviewed in Phase 13 (`docs/SECURITY.md`) and found already
  reasonably safe (no CORS middleware at all outside dev), with one residual, disclosed gap:
  `environment` itself still defaults to `"development"` if unset.
- A `consents` table was added beyond `medai_spec.yaml`'s explicit `database.tables` list, to
  satisfy `security.consent_record_fields` — flagged in `IMPLEMENTATION_PLAN.md` and
  `docs/DATABASE.md`.
- No formal compliance posture (HIPAA/GDPR-equivalent or explicit non-claim) has been adopted;
  in the interim, all patient data is handled as if it were regulated health data.
- This is a prototype. It is not a licensed medical device, not a diagnostic system, and must
  never be presented as either (`medai_spec.yaml` `system_disclaimers`).
