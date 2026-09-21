# MEDAI — AI Pipeline

> Filled in incrementally as each AI-related phase lands. This reflects Phase 9 (vital
> ingestion) on top of Phase 8's `POST /assessment` — the first user-facing clinical-output
> endpoint.

## Canonical pipeline (medai_spec.yaml architecture.canonical_pipeline)

```
USER → AUDIO → STT → STRUCTURED_PATIENT_STATE → FOLLOW_UP_QUESTIONS
     → VITAL/HEALTH_DATA → EVIDENCE_RETRIEVAL → CLINICAL_REASONING
     → DETERMINISTIC_SAFETY → MEDICATION_SAFETY → OUTPUT_VALIDATION
     → TEXT_RESPONSE → OPTIONAL_TTS
```

Built so far: `STT` (on-device, mobile-side, Phase 2) → `STRUCTURED_PATIENT_STATE` (partial —
symptom extraction only, Phase 3) → `FOLLOW_UP_QUESTIONS` (Phase 4, deterministic) →
`VITAL/HEALTH_DATA` (Phase 9, manual entry only) → `EVIDENCE_RETRIEVAL` (Phase 5) →
`CLINICAL_REASONING` (Phase 6) → `DETERMINISTIC_SAFETY` + `MEDICATION_SAFETY` (Phase 7) →
`OUTPUT_VALIDATION` (Phase 8) → `TEXT_RESPONSE`, now reachable via `POST /assessment`
(`app/api/assessment.py`) — see "The assessment endpoint" below. `app/reasoning`, `app/safety`,
and `app/validation` remain otherwise unreachable from the API; this endpoint is the sole caller
allowed to treat their output as user-facing. As of Phase 9, this endpoint's `DETERMINISTIC_SAFETY`
step evaluates *real* vitals from the `vitals` table (via `app/patient_state/assembler.py` →
`vitals_from_patient_state()`), not an empty dict — see "Vital ingestion (Phase 9)" below.
`VITAL/HEALTH_DATA` today means manual entry only; automatic device/health-platform retrieval
(`vital_system.automatic_retrieval_preference`'s DEVICE/HEALTH_PLATFORM tiers) is Phase 10.

## Provider abstraction

`app/providers/llm/base.py` defines `LLMProvider` (`generate`, `structured_generate`, `stream`)
per `architecture.provider_interfaces`. **Active concrete implementation:**
`app/providers/llm/gemini_provider.py` (`GeminiProvider`), via the official `google-genai` SDK's
async Interactions API (`client.aio.interactions.create`) — **decided by the user**, originally
OpenAI in Phase 3, switched to Gemini afterward. The SDK's actual method/field names
(`system_instruction`, `response_format={"type": "text", "mime_type": "application/json",
"schema_": ...}`, `interaction.output_text`, streaming via `event_type == "step.delta"`) were
verified against the live docs and the installed package's own type definitions before writing
the provider, not assumed from training data.

`app/providers/llm/openai_provider.py` (`OpenAIProvider`) is kept as a second, still-working
`LLMProvider` implementation — unused, but proof the provider is genuinely swappable. Exactly
one place selects the active one: `get_llm_provider()` in `app/providers/llm/__init__.py`;
swapping providers means writing a new `LLMProvider` subclass and changing that one function.

`GeminiProvider` fails closed: with no `GEMINI_API_KEY` configured, every method raises
`LLMNotConfiguredError` rather than returning a fabricated response
(`error_handling.fail_closed_principle`) — verified live. A real key is now configured and has
been exercised against the live API: a real message produced a correct structured extraction
(right symptom, severity, onset, location, trigger, with unmentioned fields left `null` rather
than guessed) and a naturally LLM-phrased follow-up question — see `docs/KNOWN_LIMITATIONS.md`
for the exact example. Extraction is also still tested against a `FakeLLMProvider` (see
`backend/tests/fakes.py`) so tests don't depend on a live key or network call.

Model: `gemini-3.7-flash` by default (`GEMINI_MODEL` env var) — the third model id tried after
the first two (`gemini-3.8-flash`, `gemini-3.6-flash`) hit `429`s. **Correction**: an earlier
version of this doc claimed the free-tier's 20-requests/day quota resets per model id — that
turned out to be wrong or at least incomplete. `gemini-3.7-flash` hit its own `429` after only
~5 requests despite never having been used before. The free tier appears to enforce some
smaller cap shared across models under the same key/project. Switching `GEMINI_MODEL` is not a
reliable way to get significantly more real calls; a paid tier or waiting for a daily reset is.

## Symptom extraction (Phase 3)

- **Input**: the user-role messages of one conversation (`app/api/symptoms.py:extract_symptoms`).
- **Prompting**: `app/patient_state/extraction.py` — a system prompt instructing the model to
  extract only what the patient actually stated, leave unmentioned fields null, and never
  suggest a cause, condition, or treatment (this endpoint performs *extraction*, not reasoning,
  per `phases.2_conversation.constraint` carrying into Phase 3).
- **Output**: `SymptomExtractionResult` (a Pydantic model wrapping `list[ExtractedSymptom]`),
  requested via `structured_generate` — `GeminiProvider` asks for a JSON-schema-constrained
  response (`response_format`) and validates the returned JSON against the Pydantic schema
  before it's ever used — satisfies `clinical_reasoner.prompting.rule`: "use structured output
  wherever supported."
- **Storage**: one `Symptom` row per extracted item (`backend/app/db/models.py`), linked to the
  source `conversation_id`, free-text fields encrypted at rest.
- **Assembly**: `app/patient_state/assembler.py:build_patient_state()` composes the full
  `patient_state.schema` object (patient identity, symptoms, medical_history, allergies,
  medications, vitals, unknowns, data_quality) from the DB on demand — never stored as one
  mutable blob. Fields it can't find are listed in `unknowns`, never guessed
  (`patient_state.rules`).

## Prompt safety

User message content is untrusted text (`prompt_safety.untrusted_inputs`) — it is only ever
placed in the *user* turn of the chat completion, never concatenated into the system prompt or
otherwise given instruction-level trust. `LLMProvider.structured_generate`'s `system` parameter
is fully controlled by the calling code (`extraction.py`'s `_SYSTEM_PROMPT`), never derived from
user input.

## Conversation manager (Phase 4)

`app/conversation/manager.py` + `app/conversation/missing_info.py` implement
`conversation_manager.flow`: on each `POST /messages`, the canonical patient state is
re-assembled (`build_patient_state`), compared against a fixed set of clinically-relevant
fields, and the single highest-priority missing one becomes a follow-up question — replacing
Phase 2's echo scaffold, exactly as that scaffold's own docstring said it would.

- **Deterministic by design, not LLM-driven.** `identify_missing_info` and `select_action` never
  call an LLM — they inspect `PatientState` (itself built only from DB rows) and apply
  `conversation_manager.question_priority` in a fixed order. This means the interview works
  fully even with `GEMINI_API_KEY` unset — a deliberate design choice, not a spec requirement.
  The LLM is used, when configured, only for *phrasing* the chosen question more naturally
  (`manager.py:_phrase_question`) — a best-effort NLG step with a deterministic template
  fallback on any failure, never the decision itself. Both paths are now verified live: the
  deterministic decision logic, and (once a real key was configured) the LLM phrasing path
  producing a natural question instead of the fallback template — see
  `docs/KNOWN_LIMITATIONS.md`.
- **`conversation_manager.question_priority` coverage today**: `medication_allergy_safety`
  (missing allergies/medications), `relevant_history` (missing medical history),
  `lower_priority_context` (missing age/sex/height/weight), and `high_impact_missing_information`
  for symptoms already in the `symptoms` table with an incomplete severity/duration/onset.
  `emergency_indicators` and `required_measurements` are structurally present in the priority
  order (so nothing needs reordering later) but have no item-generator yet: emergency detection
  needs sourced, authoritative rules (`safety_engine.emergency_triage`, Phase 7) and
  measurements need the vital/device subsystem (Phase 9) — this module must not invent either.
- **`conversation_manager.permitted_actions` arbiter**: `app/conversation/manager.py:
  validate_action` is the single application-side gate — per `conversation_manager.rule`
  ("LLM may propose an action; application determines whether it is permitted"). Today only
  `ASK_QUESTION`/`RESPOND` are implemented; `GET_VITAL`/`RETRIEVE_EVIDENCE`/`RUN_ASSESSMENT`/
  `ESCALATE` are recognized as valid `permitted_actions` but rejected with
  `NotImplementedError` until their backing subsystem (Phase 9/5/6/7 respectively) exists.
  `RETRIEVE_HISTORY` isn't a separate runtime action here because history is already folded
  into `PatientState` before this module runs.

## Medical knowledge / RAG (Phase 5)

`rag_pipeline`: `SOURCE_INGESTION → CLEANING → METADATA → CHUNKING → EMBEDDINGS → VECTOR_DB →
RETRIEVAL → RERANKING → EVIDENCE_PACKAGE`. All user-decided, with references recorded in
`docs/KNOWN_LIMITATIONS.md`:

- **`MedicalKnowledgeProvider`**: `app/providers/medical_knowledge/medlineplus_provider.py` —
  real calls to MedlinePlus's health-topics web service (no API key). PubMed Central and openFDA
  are also user-approved sources but not yet wired in (see that file's module docstring for how
  to add one). `knowledge_base.approved_sources` category: `government_health_guidance`.
- **`EmbeddingProvider`**: `app/providers/embeddings/sentence_transformers_provider.py` —
  self-hosted `BAAI/bge-large-en-v1.5` (1024-dim, normalized), no API key, loaded lazily
  (~1.3GB, cached by Hugging Face after first use). Per the model card, queries get a
  `"Represent this sentence for searching relevant passages: "` instruction prefix; indexed
  passages get none — `EmbeddingProvider` has separate `embed_query`/`embed_documents` methods
  specifically so this asymmetry isn't lost.
- **`VectorStore`**: `app/providers/vector_store/pgvector_store.py` — pgvector, the same
  Postgres instance as everything else (no separate vector DB service). Cosine distance via an
  HNSW index (`knowledge_chunks_embedding_hnsw_idx`).
- **Chunking**: `app/rag/chunking.py` — fixed-size word windows (180 words, 30-word overlap),
  source-agnostic.
- **Versioning**: `app/rag/ingest.py:_supersede_existing` — re-ingesting a previously-seen `url`
  marks the prior `ClinicalSource` row `superseded_status='superseded'` (new `version`, new row)
  rather than overwriting it or its chunks (`knowledge_base.versioning`). Retrieval only ever
  searches `superseded_status='current'` chunks.
- **Reranking**: not implemented as a separate step — `retrieve_evidence` returns results in the
  order pgvector's cosine-similarity search gives them. No reranker model was specified by the
  user, so none was invented; `app/rag/retrieval.py` has a comment marking where a cross-encoder
  reranker would slot in if one is added later.
- **Traceability**: every `EvidenceItem` carries its source's title, publisher, url,
  source_type, version, and retrieval_date (`evidence_package.rule`) — never just raw text.

**Verified live**, not just against fakes: `POST /evidence/ingest {"topic": "headache"}` pulled
three real MedlinePlus articles (Headache, Migraine, Concussion); `GET /evidence?query=what
causes tension headaches and how long do they last` correctly ranked the Headache article's
relevant passage first (similarity 0.75), with full source attribution. This directly
demonstrates the Phase 5 pass criterion: "Given a clinical topic, relevant evidence can be
retrieved and traced to its source."

## Clinical reasoning (Phase 6)

`app/reasoning/`: `evidence_package.py` assembles `evidence_package.schema` (patient_state +
`relevant_history` + `retrieved_evidence`, scoped to the patient's own symptoms — `relevant_vitals`
and `safety_flags` stay empty until Phase 9/7 exist); `reasoner.py:generate_assessment()` sends
it to the LLM and returns a validated `Assessment` (`output_schema`, verbatim field set).

- **Not directly reachable from the API — `POST /assessment` is the only caller allowed to
  treat its output as user-facing, and only via `get_validated_output()` (Phase 8), never this
  function alone.** At the time this was written, `safety_engine` (Phase 7) and
  `output_validator` (Phase 8) didn't exist yet, so `architecture.bypass_forbidden` meant no
  endpoint could safely call this; both now exist, and `POST /assessment` (`app/api/
  assessment.py`) chains them together — see "The assessment endpoint" below.
- **Prompting** (`clinical_reasoner.prompting.receives`): `system_policy` (`reasoner.py`'s
  `_SYSTEM_POLICY` — role, `must`/`must_not` list from the spec, uncertainty-language
  requirements, and an explicit instruction that `patient_state` content — including anything
  originally said by the patient — is data, not instructions); `task` + `patient_state` +
  `evidence` + `safety_flags` (serialized into the prompt by `_serialize_task`); `output_schema`
  (enforced by requesting `structured_generate` against the `Assessment` schema directly, rather
  than restating it as prompt text). Nothing here comes from raw request/session objects
  (`must_not_receive: uncontrolled_application_state`).
- **Defense-in-depth checks** (`app/reasoning/checks.py`) — ahead of Phase 8's real
  `output_validator`, not a replacement for it:
  - `check_grounding`: every `EvidenceReference.source_id` the model cites must actually be one
    of the `retrieved_evidence` items it was given — catches invented evidence in code, not by
    trusting the model's own citation text (`clinical_reasoner.must_not:
    invent_evidence_or_medication_info`).
  - `check_uncertainty_language`: rejects a short list of unqualified absolute-certainty phrases
    (`uncertainty_language.forbidden`).
  - A failed check — or a malformed/schema-invalid response — triggers one retry
    (`generate_assessment`'s `max_attempts`, default 2) before raising; nothing that fails both
    attempts is ever returned.
- **Not persisted.** `medai_spec.yaml database.tables` lists `recommendations` and
  `recommendation_evidence`, but Phase 6 doesn't write to them: an `Assessment` here hasn't been
  through `safety_engine`/`output_validator` yet, so persisting it to a table named
  "recommendations" would misrepresent it as a vetted output. Deferred to whichever phase first
  produces a validated, releasable result.

**Verified live**, not just against fakes: a real evidence package (1 symptom — a throbbing,
right-sided headache, severity 7, triggered by bright light, onset "yesterday afternoon" — plus
5 retrieved MedlinePlus passages) sent to the real Gemini API produced a schema-valid
`Assessment` — `status: "caution"`, hedged summary ("Based on the available information..."),
accurate `known_information`, a thorough `unknown_information` list (age, sex, vitals, red-flag
symptoms, history, medications, allergies), an appropriate general red-flag `warnings` entry,
`confidence: "low"`, and two `evidence` citations whose `source_id`s were real, retrieved
MedlinePlus articles — passing both defense-in-depth checks on the first attempt. This directly
demonstrates the Phase 6 pass criterion: "Model produces schema-valid reasoning grounded in
retrieved evidence."

## Deterministic safety engine & medication safety (Phase 7)

`app/safety/`: `vital_rules.py` (sourced vital-sign thresholds), `medication.py`
(`medication_safety.pipeline`, openFDA-backed), `engine.py` (`evaluate_safety` — aggregates
both into one `PASS`/`MODIFY`/`BLOCK`/`ESCALATE` decision and logs to `safety_events`).

- **Not directly reachable from the API.** `POST /assessment` calls `evaluate_safety()` (with
  `vitals={}` — Phase 9 doesn't exist yet) as part of its pipeline; `check_candidate_medication()`
  specifically is still only called from tests and the live-verification script — the endpoint
  doesn't cross-check its own proposed medications yet, see "The assessment endpoint" below.
- **`runs_independently_of_llm` (safety_engine.rule), literally**: `evaluate_safety()` never
  reads an `Assessment`'s own `status` field — every input is plain data (a `vitals` dict,
  a list of `MedicationCheckResult`s). An LLM that claims "normal" while `SpO2` is 86% still
  gets `ESCALATE`, because the LLM's opinion is never consulted.
- **Vital thresholds — every one sourced, none invented** (`app/safety/vital_rules.py`):
  heart rate and blood pressure from the AHA pages the user supplied (those pages block
  automated fetches — HTTP 403 — so the standard AHA/ACC figures were corroborated via a
  direct fetch of Cleveland Clinic's heart-rate page and cross-checked against other reputable
  clinical sources citing the same AHA/ACC guideline; disclosed, not glossed over); SpO2 and
  body temperature from direct primary-source fetches (the WHO pulse-oximetry manual PDF and
  the MedlinePlus body-temperature page), with the exact quoted thresholds in the module's
  docstring. Where a source gave no explicit number (e.g. no stated heart-rate "emergency"
  cutoff distinct from tachycardia itself; MedlinePlus states no dangerous-fever or
  hypothermia threshold), **no rule exists for it** — nothing was invented to fill the gap.
- **No `safety_rules` DB table** — see `docs/DATABASE.md` for why; rules are a version-controlled
  Python list, not admin-editable data.
- **Medication safety** (`app/safety/medication.py`): implements
  `medication_safety.pipeline`'s exact step order, backed by real openFDA drug-label lookups
  (`app/providers/medication_db/openfda_provider.py`, user decision). Allergy and
  contraindication matches → `BLOCKED`; drug-interaction text matches, duplicate therapy,
  boxed warnings, and (heuristically) pediatric-use concerns → `REQUIRES_REVIEW`; nothing
  found → `ALLOWED`. This is **literal substring text-matching against label prose**, not a
  structured interaction graph (openFDA's label endpoint doesn't expose one) — documented
  limitation, found empirically while writing tests: it correctly blocks "penicillin" for a
  "penicillin" allergy, but does **not** catch a drug-class allergy (e.g. "amoxicillin" against
  a "penicillin" allergy — the words share no substring) or a word-form mismatch (a condition
  recorded as "pregnancy" won't match label text saying "pregnant"). A match is always
  `BLOCKED`/`REQUIRES_REVIEW`, never a silently-reassuring `ALLOWED`, but a false negative from
  this limitation is still possible. `dosage_validity` (`medication_safety.checks`) is not
  implemented — a candidate here is a drug name only, no proposed dose to validate against.

**Verified live**, not just against fakes: three real openFDA lookups against a real patient —
`penicillin` (patient has a recorded penicillin allergy) → `BLOCKED`; `warfarin` (patient takes
aspirin) → `REQUIRES_REVIEW`, correctly citing both the real drug-interactions text mentioning
aspirin *and* warfarin's real FDA boxed warning; `acetaminophen` → `ALLOWED`. Then
`evaluate_safety()` with real vitals (SpO2 86%, heart rate 118 bpm) plus those three findings
correctly triggered both `VITAL_SPO2_EMERGENCY_001` and `VITAL_HR_HIGH_001`, decided
`ESCALATE` (the emergency-tier vital rule outranks the blocked medication), and logged 4 rows
to `safety_events` (verified by querying the dev DB directly) — while a second call with normal
vitals and no medication findings correctly returned `PASS` and logged nothing.

## Output validator (Phase 8)

`app/validation/`: `checks.py` (the 10 `output_validator.checks`, each a standalone function),
`validator.py` (`get_validated_output` — the correction pipeline and fail-closed fallback).

- **`get_validated_output()` is the only function in this codebase intended to return an
  Assessment fit for release** — `reasoner.generate_assessment()` (Phase 6) returns unvalidated
  output and must never be treated as user-facing on its own. `POST /assessment`
  (`app/api/assessment.py`) is now the only endpoint that calls it — see "The assessment
  endpoint" below.
- **The 10 checks**, mapped 1:1 to the spec's own list: `schema_compliance` (belt-and-braces
  beyond what pydantic already enforces at construction); `unsupported_claims` and
  `uncertainty_requirements` (reuse Phase 6's `check_grounding`/`check_uncertainty_language` as
  the *official* gate, not just defense-in-depth); `evidence_availability` (substantive claims
  need at least one citation); `dangerous_language` (false-reassurance phrases, distinct from
  false-certainty ones); `prescription_like_directives` (dosage-shaped text, prescriptive
  phrasing); `contradictions` (status/escalation consistency); `safety_engine_result` (an
  `ESCALATE` from Phase 7 must be reflected in the assessment's own `status`, regardless of what
  the LLM itself concluded — `safety_engine.rule`: hard rules take precedence); `medication_
  validation` (a medication Phase 7 `BLOCKED` can't appear as a recommended option);
  `escalation_requirements` (`emergency` status needs real escalation text).
- **Correction pipeline**: on any failed check, `reasoner.generate_assessment()` is called again
  with the failure reasons fed back into the prompt (one bounded retry by default,
  `max_correction_attempts`) — `output_validator.on_failure`'s "return to correction pipeline".
  If that still fails, or if anything in this whole path raises unexpectedly (a bug in the
  checks themselves, a provider outage, a rate limit), `get_validated_output` **fails closed**
  and returns `SAFE_FALLBACK` (`safe_fallback`, verbatim) rather than propagating an exception
  or releasing unvalidated content — `output_validator.on_validator_failure`: "Fail closed — do
  not release output."

**Verified live**, not just against fakes — and this run ended up demonstrating more than
originally planned, because a real failure occurred mid-run:
- **Case A** (normal vitals): the first generation attempt hit a transient `503` from Gemini;
  the built-in retry succeeded on attempt 2, and the resulting assessment passed all 10 checks
  on the first validation pass — a real end-to-end success.
- **Case B** (SpO2 86%, `safety_engine` decision `ESCALATE`): the LLM's first assessment said
  `status: "caution"` — genuinely ignoring the deterministic safety decision, exactly the
  failure `check_safety_engine_result` exists to catch. The validator correctly rejected it and
  triggered the correction pipeline. The retry then hit a real `429` rate limit (Gemini's
  free-tier cap — see "Provider abstraction" above) on both of `generate_assessment`'s own
  internal attempts, so the exception propagated up as designed — and `get_validated_output`
  correctly caught it and returned `SAFE_FALLBACK` verbatim, rather than releasing the
  ESCALATE-violating assessment or crashing. This is a stronger proof of "no final clinical
  response reaches the user without validation" than a clean run would have been: a real,
  unplanned external failure hit the system mid-pipeline, and the fail-closed design held.

## Vital ingestion (Phase 9)

`app/vitals/`: `schema.py` (`NormalizedMeasurement`, `ValidationOutcome`), `validation.py`
(`validate_measurement()` — `vital_system.validation_stages`), `service.py`
(`ingest_measurement()` — persistence + snapshot-upsert logic). `app/api/vitals.py` and
`app/api/devices.py` expose `POST/GET /vitals`, `GET /vitals/history`, `POST/GET /devices` (see
`docs/API.md`). `app/providers/devices/base.py` defines the `DeviceAdapter` ABC per
`architecture.provider_interfaces`, with no concrete implementation — manual entry is
deliberately *not* modeled as a `DeviceAdapter` (it isn't a device), so `/vitals` calls
`ingest_measurement` directly rather than through the provider abstraction.

- **Validation stages are sanity checks, not clinical judgment — a critical distinction called
  out explicitly in `validation.py`'s module docstring.** `_SANITY_BOUNDS` (e.g. `heart_rate:
  (0, 400)`, `oxygen_saturation: (0, 100)`, `body_temperature: (70, 115)`°F) exist only to catch
  garbage input (wrong unit, transposed digits, an obviously impossible reading) — they are
  deliberately far wider than Phase 7's sourced clinical thresholds
  (`app/safety/vital_rules.py`). A genuinely critical real reading (e.g. SpO2 82%) must be
  *accepted* here and left for the safety engine to act on, not rejected at ingestion — the two
  layers have different jobs, and conflating them would let ingestion silently discard exactly
  the readings the safety engine most needs to see. Enforced by a dedicated test
  (`test_spo2_genuinely_low_is_still_accepted_not_rejected`) and verified live below.
  `EXPECTED_UNITS` catches unit mismatches (e.g. `"beats"` for `heart_rate`, expected `"bpm"`)
  separately from range sanity.
- **Two-table persistence, deliberately not one.** Every submission — accepted or rejected —
  is written to `measurements` (the full, append-only audit trail, per "never silently drop a
  suspicious measurement"). Only an *accepted* measurement whose `timestamp` is not older than
  the existing snapshot row's updates `vitals` (one row per `(patient_id, type)`, what
  `PatientState.vitals` actually reads). This means a backdated accepted reading is logged but
  never regresses the current snapshot — verified by
  `test_newer_reading_updates_snapshot_older_backdated_one_does_not`.
- **Reaches the canonical pipeline for real now.** `app/patient_state/assembler.py` queries
  `Vital` rows and populates `PatientState.vitals` (previously always `{}`);
  `app/reasoning/evidence_package.py`'s `relevant_vitals` is populated from that dict (previously
  always `[]`); `app/safety/engine.py:vitals_from_patient_state()` translates
  `vital_system`-named keys (`heart_rate`, `blood_pressure_systolic`, `blood_pressure_diastolic`,
  `oxygen_saturation`, `body_temperature`) into the key names Phase 7's pre-existing
  `vital_rules.py` already uses (`heart_rate`, `systolic_bp`, `diastolic_bp`, `spo2`,
  `body_temp_f`) — a deliberate translation layer rather than renaming either side, since
  `vital_rules.py`'s keys were already load-bearing in live-verified Phase 7/8 demos.
  `respiratory_rate` and `weight` have no corresponding Phase 7 rule and are left untranslated
  (no rule exists to trigger, per Phase 7's "no rule invented where no source gives one").

**Verified live**, not just against fakes — two separate checks, deliberately split because the
first needs no LLM call and the second is pure deterministic logic:

- **The vitals API itself**, against a running dev server with real Postgres: registered a user;
  `POST /vitals {heart_rate, 72, bpm}` → `201 accepted:true`; `POST /vitals {oxygen_saturation,
  86, %}` → `201 accepted:true` (a real dangerously-low reading correctly preserved, not
  rejected); `POST /vitals {heart_rate, 72, beats}` (wrong unit) → `422
  MEASUREMENT_UNRELIABLE: unexpected unit 'beats' for heart_rate (expected 'bpm')`; `GET
  /vitals` → correct 2-item current snapshot; `GET /vitals/history` → correct 3-item history
  including the rejected entry with its `rejection_reason`; `POST /devices {manual, "Home BP
  cuff"}` → `201` with the created device. This directly demonstrates the Phase 9 pass
  criterion: "Vitals can enter the canonical patient state" (at the ingestion layer).
- **The full deterministic chain**, run as a script against the same patient/data: called
  `build_patient_state()` directly and confirmed `state.vitals` contained both real readings
  with correct values/units/timestamps; called `vitals_from_patient_state(state.vitals)` and
  confirmed the translated dict (`{"heart_rate": 72.0, "spo2": 86.0}`); called `evaluate_safety()`
  with that dict and got `decision: "ESCALATE"`, correctly triggering
  `VITAL_SPO2_EMERGENCY_001` ("SpO2 86.0% is below 90%") — the same rule and threshold verified
  live in Phase 7, now driven by a real ingested reading instead of a hand-constructed dict.
  This is also covered by fakes-based integration tests
  (`test_vitals_safety_integration.py`) and a new `/assessment` integration test
  (`test_assessment_rejects_llm_output_that_ignores_a_real_escalating_vital`), but this script
  run is the first time it was exercised against the real live server/DB path rather than the
  test client. **Not yet re-verified**: a real live Gemini call, fed this real escalating vital
  through the full `/assessment` HTTP path, actually producing a model-generated
  safety-corrected `Assessment` — blocked on today's exhausted free-tier quota (see "Provider
  abstraction" above); the fakes-based test covers the same logical path.

## The assessment endpoint

`POST /assessment` (`app/api/assessment.py`) chains everything above together for the first
time: `build_patient_state` (Phase 3) → `build_evidence_package` (Phase 6, itself calling Phase
5's `retrieve_evidence`) → `evaluate_safety` (Phase 7, now with real vitals as of Phase 9) →
`get_validated_output` (Phase 8). It requires an owned `conversation_id` (404 otherwise) and
always returns `200` with an `Assessment` body — `SAFE_FALLBACK` included, since that's a
legitimate `output_schema` response, not an error.

- **Known gap, stated plainly**: this endpoint's safety-engine call now uses real vitals but
  still never populates `medication_findings` — there is no reliable way yet to turn
  `Assessment.medication_information`'s free text (e.g. "consider acetaminophen") into a
  `MedicationDBProvider.lookup()` call without guessing at a drug name.
  `check_medication_validation` (Phase 8) still runs on every request, but with nothing to
  compare against it is currently a no-op here specifically. Building a real extractor is
  future work.
- **The request-timeout fix (30s per `client.aio.interactions.create` call,
  `app/providers/llm/gemini_provider.py`) has since been verified live**: the original
  indefinite-hang bug is genuinely fixed — a real rate-limited request correctly failed both of
  `generate_assessment`'s retry attempts within the expected bound and `get_validated_output`
  correctly logged its fail-closed message. A related, smaller issue surfaced in the same test:
  worst-case total latency for this endpoint (2 reasoning attempts × up to 2
  `generate_assessment` calls across the correction path, each up to 30s) can approach 2
  minutes when every attempt fails — easy to exceed with a client-side timeout under that.
  Separately, it's not confirmed whether FastAPI/uvicorn cleanly handles writing a response to
  an already-disconnected client in that scenario. Any caller of this endpoint should use a
  generous timeout (2+ minutes) or expect lower worst-case latency only if `max_attempts`/
  `max_correction_attempts` are reduced.
- **Verified**: 112/112 tests (4 new, covering auth, ownership, a full fakes-driven happy path
  with a real grounded citation, and the not-configured→`SAFE_FALLBACK` path). **Live, cleanly**:
  a patient with no data → a real (not fallback) appropriately-hedged "insufficient information"
  `Assessment`, fast, first try; a patient with real extracted symptoms (sore throat + fever)
  and real ingested MedlinePlus evidence → a real `200 OK` (confirmed via the server's access
  log; the response body wasn't captured due to a client-side scripting mistake). **Live, via
  the fail-closed path**: a third call hit a real rate limit and correctly resolved to
  `SAFE_FALLBACK` internally, per the paragraph above. Also discovered while doing this: an
  earlier claim in this doc that Gemini's quota resets per model id was wrong or incomplete —
  see `docs/KNOWN_LIMITATIONS.md` for the correction.

## Not yet implemented

The conversation manager's `emergency_indicators` and `required_measurements` question tiers are
still unpopulated (see the conversation manager section above) — Phase 7's vital-threshold rules
and Phase 9's vitals now both exist, but this module hasn't been wired to either yet. Wiring
safety_engine/medication safety into the *live conversation loop* itself (as opposed to the
dedicated `/assessment` endpoint) is still separate, undone work. No concrete `DeviceAdapter`
exists (Phase 9 built the ABC only) — automatic device/health-platform retrieval is Phase 10.
