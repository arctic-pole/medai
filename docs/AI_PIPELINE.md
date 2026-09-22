# MEDAI — AI Pipeline

> Filled in incrementally as each AI-related phase lands. This reflects Phase 12 (complete
> pipeline) on top of Phase 11's TTS, Phase 10's health platform integration, Phase 9's vital
> ingestion, and Phase 8's `POST /assessment`.

## Canonical pipeline (medai_spec.yaml architecture.canonical_pipeline)

```
USER → AUDIO → STT → STRUCTURED_PATIENT_STATE → FOLLOW_UP_QUESTIONS
     → VITAL/HEALTH_DATA → EVIDENCE_RETRIEVAL → CLINICAL_REASONING
     → DETERMINISTIC_SAFETY → MEDICATION_SAFETY → OUTPUT_VALIDATION
     → TEXT_RESPONSE → OPTIONAL_TTS
```

Built so far: `STT` (on-device, mobile-side, Phase 2) → `STRUCTURED_PATIENT_STATE` (partial —
symptom extraction only, Phase 3) → `FOLLOW_UP_QUESTIONS` (Phase 4, deterministic) →
`VITAL/HEALTH_DATA` (Phase 9 manual entry + Phase 10 Health Connect sync) →
`EVIDENCE_RETRIEVAL` (Phase 5) → `CLINICAL_REASONING` (Phase 6) → `DETERMINISTIC_SAFETY` +
`MEDICATION_SAFETY` (Phase 7) → `OUTPUT_VALIDATION` (Phase 8) → `TEXT_RESPONSE`, now reachable
via `POST /assessment` (`app/api/assessment.py`) — see "The assessment endpoint" below.
`app/reasoning`, `app/safety`, and `app/validation` remain otherwise unreachable from the API;
this endpoint is the sole caller allowed to treat their output as user-facing. As of Phase 9,
this endpoint's `DETERMINISTIC_SAFETY` step evaluates *real* vitals from the `vitals` table (via
`app/patient_state/assembler.py` → `vitals_from_patient_state()`), not an empty dict — see
"Vital ingestion (Phase 9)" below. As of Phase 10, those real vitals can now originate from a
real health platform (Google Health Connect), not just manual entry — see "Health platform
integration (Phase 10)" below. As of Phase 11, `OPTIONAL_TTS` is also built — a genuinely
optional companion to `TEXT_RESPONSE`, reachable via `POST /assessment/speech`, gated so it can
only ever speak text that has already been through `get_validated_output()` — see "TTS (Phase
11)" below. As of Phase 12, this entire chain — `FOLLOW_UP_QUESTIONS` through `TEXT_RESPONSE`
— is reachable from **a single conversational loop**, `POST /messages`
(`app/api/messages.py`): once nothing more is missing to ask, that same endpoint runs
`EVIDENCE_RETRIEVAL` through `OUTPUT_VALIDATION` automatically and returns the result as the
assistant's reply, rather than requiring a separate action — see "Complete pipeline integration
(Phase 12)" below.

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
  ("LLM may propose an action; application determines whether it is permitted"). As of Phase 12,
  `ASK_QUESTION` and `RUN_ASSESSMENT` are implemented; `GET_VITAL`/`RETRIEVE_EVIDENCE`/`ESCALATE`
  are recognized as valid `permitted_actions` but rejected with `NotImplementedError` — there's
  no manager-level detection ahead of running the assessment itself. `RETRIEVE_HISTORY` isn't a
  separate runtime action here because history is already folded into `PatientState` before this
  module runs.
  **Correction to how this worked before Phase 12**: `select_action` used to return `"RESPOND"`
  once nothing was missing, and `generate_reply` returned a hardcoded placeholder string
  (`NO_FURTHER_QUESTIONS_MESSAGE`, now removed) saying a real assessment "comes in a later
  development phase." That phase has arrived: `select_action` now returns `"RUN_ASSESSMENT"`
  instead, and `generate_reply` returns `None` in that case — signaling its caller
  (`POST /messages`) to actually run the pipeline, since `app/conversation/manager.py`
  deliberately has no DB/evidence/safety access to do that itself (Phase 4's separation of
  concerns, preserved).

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

## Health platform integration (Phase 10)

**Decision (user-confirmed, with the testability trade-off flagged up front)**: Google Health
Connect. Of the four candidate platforms considered (Fitbit Web API, Withings API, Google
Health Connect, Apple HealthKit), Health Connect is the only one with no cloud REST endpoint at
all — it is an Android on-device data store, readable only by an app installed on that specific
device, gated by that device's own runtime permission grants. This has a real architectural
consequence: `architecture.provider_interfaces`' `DeviceAdapter` (`app/providers/devices/
base.py`), defined as a backend-callable `read(vital_type) -> NormalizedMeasurement`, **cannot
be implemented in Python for Health Connect** — there is nothing server-reachable to call. The
real concrete adapter necessarily runs client-side, in the Flutter app.

- **`mobile/lib/services/health_connect_adapter.dart`** (`HealthConnectAdapter`) — the real
  `DEVICE -> DEVICE_ADAPTER` step, using the `health` package (pub.dev, v13.3.2, verified
  against its own installed source — not assumed from a summary) to read Health Connect samples
  for every `vital_system.initial_measurements` type it supports (heart rate, oxygen
  saturation, blood pressure systolic/diastolic, body temperature, respiratory rate, weight).
  Converts each into the backend's exact vocabulary/units (`app/vitals/schema.py`'s `VitalType`,
  `app/vitals/validation.py`'s `EXPECTED_UNITS`) before it ever leaves the device — notably
  Celsius→Fahrenheit for body temperature (`convertHealthConnectValue`, unit-tested in
  `test/health_connect_adapter_test.dart`); every other type Health Connect already reports in
  the unit the backend expects, verified against the installed package's own default-unit table.
  Raises `HealthConnectUnavailable` (never fabricates data) per `vital_system.rules`'
  `{status: unavailable, reason: DEVICE_ERROR}` when Health Connect itself can't be reached.
- **`mobile/lib/services/health_sync_service.dart`** (`HealthSyncService`) — orchestrates the
  adapter + `ApiClient`: requests Health Connect permissions, registers a `health_connect`
  device once (id cached in secure storage, reused thereafter), and POSTs read readings to the
  new backend endpoint below.
- **`POST /vitals/sync`** (`app/api/vitals.py`) — the `VITAL_SERVICE` entry point for this data,
  since `DeviceAdapter.read()` can't be. Validates the given `device_id` belongs to the calling
  patient, forces `source="health_platform"` server-side regardless of client input (same
  never-fabricate-provenance rule as manual entry) — Health Connect aggregates across apps and
  devices rather than being one physical DEVICE, so `automatic_retrieval_preference`'s
  HEALTH_PLATFORM tier, not DEVICE, is the correct label. Every reading runs through the same
  `ingest_measurement`/`validate_measurement` path as Phase 9's manual entry — accepted or
  rejected, never silently dropped — and the response reports one outcome per reading.
- **Home screen**: a "Sync Health Connect data" button (Android-only; hidden on web/desktop),
  wired to `HealthSyncService.sync()`, surfacing accepted/rejected counts or a clear
  "Health Connect unavailable — enter vitals manually" message on failure.
- **Zero changes to `clinical_reasoner`/`safety_engine`** (`vital_system.rules`: "Clinical
  engine must not depend on a specific wearable") — confirmed by construction, not just
  inspection: Health Connect-sourced vitals reach `evaluate_safety()` through the exact same
  `PatientState.vitals` → `vitals_from_patient_state()` path Phase 9's manual entries already
  used, and the live test below exercises that live code unmodified.

**Real environment stood up for this, not simulated**: the Android SDK, an emulator (Android
14/API 34, Google Play system image, which ships Health Connect as a built-in OS component),
and Windows Developer Mode (required for the `health` plugin's native Kotlin build) were all
installed and configured specifically for this phase, since none existed on this machine before
— see `docs/KNOWN_LIMITATIONS.md` for what this changes about mobile's "web-only" status.

**Real bugs found and fixed while wiring this together**, not glossed over:
- The `health` plugin requires the host `Activity` to be a `FlutterFragmentActivity`, not plain
  `FlutterActivity` — a `ClassCastException` on first launch, root-caused against the plugin's
  own example app and fixed in `MainActivity.kt`.
- Kotlin's incremental compiler cannot compute a relative path between the pub-cache (drive `C:`
  on this machine) and the project (drive `E:`) on Windows, crashing `compileReleaseKotlin` for
  any plugin with native Kotlin code — fixed by disabling incremental compilation
  (`kotlin.incremental=false` in `android/gradle.properties`).
- Health Connect requires blood pressure written as one combined systolic+diastolic record
  (`writeBloodPressure`), not two separate `writeHealthData` calls — surfaced as a real API
  error (`"You must use the [writeBloodPressure] API"`) while seeding live test data.
- **A real, pre-existing bug in `mobile/lib/services/api_client.dart`, unrelated to Health
  Connect**: the device-bootstrap flow's placeholder email domain, `@device.local`, is rejected
  outright by the backend's `EmailStr` validator ("special-use or reserved name") — `.local` is
  a reserved mDNS TLD. This silently broke *any* live mobile-to-backend registration and had
  gone undetected because no prior phase had actually exercised a real Android build against a
  real backend (Chrome/web testing, and Phase 2's own widget tests, never triggered it the same
  way). Fixed by switching to `@example.com` (IANA-reserved for documentation/testing use).

**Verified live end-to-end**, real device data the whole way through — not fakes, not a
hand-constructed dict: seeded real Health Connect records (heart rate 76 bpm, oxygen saturation
91%, blood pressure 128/82, body temperature 37.2°C, respiratory rate 16, weight 70 kg) via a
temporary debug harness (removed before commit; production code is read-only) using the
package's real write API; tapped the app's real "Sync Health Connect data" button; confirmed
`POST /vitals/sync` returned `200 OK` and all 7 readings were `accepted`; queried the dev DB
directly and confirmed the `vitals` snapshot held the exact values, correctly attributed
`source="health_platform"`, with body temperature correctly converted to 98.96°F; then ran the
same deterministic chain as Phase 9's live check
(`build_patient_state` → `vitals_from_patient_state` → `evaluate_safety`) against this real
synced data and got `decision: "MODIFY"`, correctly triggering `VITAL_BP_STAGE1_001` (128/82 is
Stage 1) and `VITAL_SPO2_LOW_001` (91% is in the 90-94% range) — a real `MODIFY` case,
complementing Phase 9's `ESCALATE` case, using Phase 7's pre-existing rules completely
unmodified. This directly demonstrates the Phase 10 pass criterion: a real (non-simulated)
health-platform adapter integrated end-to-end with no change to `clinical_reasoner`/
`safety_engine` code.

**Not yet verified**: the adapter-swap regression as a standalone automated test (verified here
by inspection/construction — the safety-engine code path is provably unmodified — rather than a
dedicated CI-enforced test); Health Connect's `unavailable`/permission-denied path was exercised
manually during setup (a `ClassCastException` and a cross-drive compiler crash both had to be
fixed before the real flow could run at all) but doesn't yet have an automated integration test
the way `test_vitals.py` covers manual entry's failure paths.

## TTS (Phase 11)

`voice_pipeline.flow`: `... → VALIDATED_TEXT → TTS → SPEAKER`. `voice_pipeline.rules`: "TTS
must never receive unvalidated medical output" and "User must be able to interrupt TTS and
continue speaking." Both are enforced at the code level, not left as conventions.

**Provider abstraction** (`app/providers/tts/`): `TextToSpeechProvider` (`base.py`) is the
`architecture.provider_interfaces` abstraction. Its **only public method, `speak()`, is not
abstract** — it's implemented once on the base class and requires a `ValidatedText`
(`app/tts/schema.py`), re-checked at runtime via `isinstance` even though the type hint already
says so (defense in depth: a caller that ignores static typing, e.g. Python's own dynamic
typing, still can't get through). Concrete providers implement only `_synthesize(text: str) ->
bytes`, which never sees anything the base class hasn't already validated is a `ValidatedText`.
This keeps provider-specific logic entirely inside `app/providers/tts/` — nothing in
`app/conversation/`, `app/reasoning/`, `app/safety/`, or `app/validation/` needs to know or care
which TTS vendor is active.

**Concrete choice: pyttsx3** — offline, wraps the OS's native TTS engine (SAPI5 on this Windows
dev machine; NSSpeechSynthesizer on macOS; espeak on Linux). No API key, no network call, and
therefore structurally incapable of touching Gemini's quota — mirrors Phase 2's on-device STT
choice (`speech_to_text`) for the same reasons. Verified to actually produce audio before being
wired in (`pyttsx3.init().save_to_file(...)` run standalone, produced a real non-empty WAV) —
see `app/providers/tts/pyttsx3_provider.py`.

**The `ValidatedText` gate** (`app/tts/schema.py`): a type-level guarantee, not just a
convention. `ValidatedText` can only be constructed via a private, sentinel-token-guarded
factory (`_mint_validated_text`) — calling `ValidatedText("...")` directly raises `TypeError`
(`test_tts_gate.py`). The only legitimate caller of that factory is
`app/tts/speech.py:synthesize_validated_response()`, which:

- Does **not** accept a pre-built `Assessment` as an argument — only the same pre-validation
  pipeline inputs `POST /assessment` itself receives (`llm`, `evidence_package`,
  `safety_evaluation`). This closes a loophole a simpler `speak(assessment)`-shaped function
  would leave open: constructing an `Assessment` directly with fabricated text
  (`Assessment(summary="...")`) is trivial and already done throughout this codebase's own test
  suite, so accepting one as an argument would let a caller smuggle unvalidated text through.
- Always calls `get_validated_output()` itself, internally, before any text is minted into a
  `ValidatedText` — so there is no argument-shaped path around the validation step. This
  function is the *only* place in the codebase permitted to call `TextToSpeechProvider.speak()`.
- Speaks `Assessment.summary`, plus `Assessment.escalation` if present — spoken emergency
  guidance matters as much as the written form.
- Returns `(Assessment, bytes)` — the validated text alongside the audio — so a caller is never
  tempted to treat the audio as the only output; the text is not optional, structurally.

**Endpoint**: `POST /assessment/speech` (`app/api/assessment.py`) runs the identical pipeline
setup as `POST /assessment` (patient state → evidence → safety evaluation), then calls
`synthesize_validated_response()` instead of `get_validated_output()` directly. A TTS-specific
failure (engine unavailable, empty synthesis) returns `503 TTS_ERROR`
(`error_handling.error_categories`) rather than silent/fake audio — deliberately a *separate*
endpoint from `POST /assessment`, not a field added to its response, so a TTS failure can never
affect the text endpoint's own availability or behavior. The mobile app is expected to already
have (or separately fetch) the text and simply not play audio on this failure.

**Mobile playback** (`mobile/lib/services/speech_playback_service.dart`): synthesis happens
server-side, so this is a playback wrapper, not a TTS engine — `SpeechPlaybackService` (backed
by the `audioplayers` package, seam-injected via a small `AudioBackend` interface for
testability without a platform audio channel) exposes `play()`, `stop()`, and an `onComplete`
stream. `play()` always calls `stop()` first, so a second `play()` call — or the mic being
activated — interrupts whatever was playing rather than overlapping it
(`voice_pipeline.rules`'s barge-in requirement). Wired into `ConversationScreen`: a "Get
assessment" app-bar action fetches and shows the validated summary as text immediately (never
gated on TTS); a Play/Stop icon next to that specific message fetches and plays its audio only
on explicit tap, never automatically (no always-listening-adjacent auto-play); tapping the mic
button unconditionally stops any current playback first, before even checking whether STT
itself is available, so barge-in works on the very first tap. A playback or fetch failure shows
an inline error without touching the already-rendered text.

**Tests** (16 new backend, 11 new mobile):
- `test_tts_gate.py` — `ValidatedText` cannot be constructed directly; `speak()` rejects a
  plain `str` and empty/whitespace-only text.
- `test_tts_speech.py` — successful synthesis speaks the real summary (and escalation text);
  **the core safety property**: when validation exhausts its correction attempts and resolves
  to `SAFE_FALLBACK`, that fallback — never either rejected/dangerous attempt's text — is what
  reaches TTS; a TTS-specific failure propagates without corrupting or consuming the
  already-validated `Assessment` (text stays independently available).
- `test_pyttsx3_provider.py` — a real (not faked) synthesis call, asserting genuine non-empty
  WAV output. Safe to run in every suite run: no API key, no network, no Gemini interaction.
- `test_assessment_speech.py` (integration) — auth, ownership (404), a fakes-driven happy path
  returning real WAV bytes over HTTP, a TTS-engine-failure case asserting `503 TTS_ERROR` *and*
  that `POST /assessment` independently still succeeds for the same conversation, and the
  SAFE_FALLBACK-is-spoken case when no LLM is configured.
- `speech_playback_service_test.dart` — barge-in ordering (`stop()` always precedes `play()`),
  a second `play()` interrupting rather than overlapping the first, playback failure raising
  `TtsPlaybackException` rather than failing silently, `stop()` never throwing, and `onComplete`
  forwarding.
- `conversation_screen_test.dart` (4 new) — the validated summary is shown as text before any
  audio is ever requested; Play fetches and plays audio and Stop/a second Play interrupts it;
  a speech-fetch failure is shown inline without removing the already-shown text; activating the
  microphone interrupts audio that's currently playing.

**Verified live, not just against fakes**: a real HTTP call to a running dev server —
`POST /assessment/speech` against a conversation with no extracted symptoms. The real Gemini
call inside `get_validated_output()` hit its documented 30s client-side timeout (expected —
today's free-tier quota was already exhausted by earlier live testing this session), correctly
resolving to `SAFE_FALLBACK` per Phase 8's fail-closed design; `synthesize_validated_response()`
then ran real `pyttsx3` synthesis on that fallback text and the endpoint returned a genuine
`200 OK` with a real 376KB WAV file (verified via `file`: `RIFF ... WAVE audio, Microsoft PCM,
16 bit, mono 22050 Hz`) — real audio bytes over a real HTTP response, not a mocked one.

**Not yet implemented**: streaming synthesis (`voice_pipeline.rules`: "Use streaming where
supported" — pyttsx3 has no streaming API; a future streaming-capable provider could add it
without changing `TextToSpeechProvider`'s public contract beyond adding a new method); no
automated test exercises the mobile Play button against a *real* platform audio backend (only
against the `AudioBackend` fake — a real device/emulator audio smoke test, like Phase 10's, was
not performed for TTS specifically, given Phase 10 already established Android build/run works
on this machine).

## Complete pipeline integration (Phase 12)

**Scope decision (user-confirmed)**: "core pipeline integration" rather than attempting all 15
`ux.screens` in one pass. Only 2 of 15 (`home`, `conversation`) existed before this phase; this
phase wires the *pipeline* completely — the spec's own pass criterion ("Complete end-to-end
demonstration works") — without building the remaining screens (onboarding, consent,
patient_profile, medical_history, medications, allergies, measurements, evidence,
safety_warnings, measurement_history, settings), which stay explicitly deferred, not silently
skipped.

- **`POST /messages` now runs the real pipeline automatically** (`app/api/messages.py`) —
  the single biggest change this phase makes. Previously, once `identify_missing_info` found
  nothing left to ask, `app/conversation/manager.py` returned a hardcoded placeholder message
  saying a real assessment "comes in a later development phase." That phase is this one:
  `generate_reply()` now returns `None` in that case, and the endpoint itself runs
  `build_evidence_package` → `evaluate_safety` → `get_validated_output` — the exact same
  pipeline `POST /assessment` runs — and returns the resulting `Assessment.summary` (plus
  `escalation`, if present) as the assistant's reply. `select_action` was also updated to
  return `"RUN_ASSESSMENT"` instead of `"RESPOND"` once nothing is missing, matching the spec's
  own action name rather than a generic placeholder. `MessageExchangeResponse` gained
  `is_assessment`/`assessment_status`/`escalation` fields so the mobile client can tell the two
  reply kinds apart without guessing from text content.
- **There is no longer a separate "get assessment" action anywhere in the mobile app.** Phase
  11's standalone app-bar button and `ApiClient.getAssessment()` are both removed — the
  conversation itself is the only interface a patient interacts with
  (`ux.paradigm`: "CHAT + VOICE, not FORM + DASHBOARD"; `ux.user_must_not_be_required_to`:
  `manually_construct_a_report`). `POST /assessment` and `POST /assessment/speech` still exist
  as the endpoints backing this (and remain independently testable/callable), but the mobile UI
  now reaches the assessment pipeline only through `POST /messages`.
- **Session persistence** (`ux.session_auto_preserved`, `resume_previous_consultation`):
  `ConversationScreen._init()` calls the (already-existing) `GET /conversations`, which orders
  results newest-first, and resumes `.first` — loading its history via `GET /messages` — instead
  of always creating a new conversation. Only creates a new one when the patient truly has none
  yet. **Documented limitation**: whether a historical assistant message was itself a validated
  Assessment isn't persisted on the `Message` row (recomputed fresh per turn, not stored), so a
  resumed conversation's past assessment replies render as plain text — the Play button and
  high-risk confirmation are only offered for a message received in the current live session.
- **`automatic_profile_memory`**: already true by construction since Phase 3 —
  `identify_missing_info` only asks about fields genuinely absent from the DB
  (`app/patient_state/assembler.py` assembles profile/history/allergies/medications
  automatically on every turn) — confirmed still holding, not new work this phase.
- **Confirmation prompts** (`ux.confirmation_required_when`, 5 triggers) — **1 of 5 has real
  backend signal and a real mobile surface today; the other 4 are honestly deferred, not
  fabricated**:
  - `high_risk_recommendation_considered` — **built**. When `assessment_status` is `"urgent"`
    or `"emergency"` (`SendMessageResult.isHighRisk`), `ConversationScreen` shows a modal,
    non-dismissible `AlertDialog` with the escalation text and a required "I understand"
    acknowledgment before the user can continue — real signal (`Assessment.status`, gated by
    `get_validated_output`) driving a real UI element.
  - `measurement_appears_incorrect` — **deferred**. Real backend signal exists
    (`MEASUREMENT_UNRELIABLE`, `POST /vitals`'s 422 path, Phase 9), but there is no mobile
    manual-vital-entry screen to attach a confirmation to (the `measurements` screen is one of
    the 13 deferred per this phase's scope decision) — Health Connect sync bypasses this path
    entirely (readings are accepted/rejected silently, no user prompt in that flow).
  - `medication_or_allergy_uncertain`, `critical_medical_fact_is_ambiguous` — **deferred, no
    real signal exists**. Detecting *ambiguity* in what a patient said (as opposed to detecting
    that a fact is simply missing, which `identify_missing_info` already does) needs new
    backend logic nothing in this codebase implements yet. Building a confirmation dialog with
    no real detection behind it would fabricate a capability, not defer one — not done.
  - `consent_sensitive_action_required` — **deferred**. No consent flow/screen exists yet
    (Phase 1's `consent` screen is one of the deferred 13).
- **Zero DB schema changes.** Everything above is response-shape and application-logic only —
  no migration this phase.

**Verified live**, not just against fakes: against a running dev server, a full real HTTP
sequence — register, fill profile/history/allergies/medications, create a conversation, send
one message — correctly triggered `RUN_ASSESSMENT` on the very first message (since nothing was
missing) and returned `is_assessment: true`, `assessment_status: "caution"`,
`escalation: null`, with the real `SAFE_FALLBACK` text, in 0.3 seconds (LLM deliberately
unconfigured for this run — see below). `GET /conversations` and `GET /messages` against that
same account confirmed exactly the data `ConversationScreen`'s resume path depends on: the
conversation listed newest-first, and its two messages in the correct order. This is a genuine,
fast, real round trip through the new endpoint logic, DB writes included.

**A real Gemini call was also attempted and is worth documenting honestly**: the same sequence,
run first with a real `GEMINI_API_KEY` configured, triggered a real clinical-reasoning call that
hit its documented 30s timeout on attempt 1 and then did not resolve within several minutes —
well beyond the ~2-minute worst case documented in Phase 8/9 for the *failure* path. `netstat`
confirmed the server process held a live TLS connection to a Google IP the entire time (not a
local deadlock), so this reads as unusually slow/degraded real API behavior on the day this was
tested, not a bug introduced by Phase 12's own changes — but it was not root-caused further, and
is flagged here rather than quietly worked around. The fast, LLM-unconfigured run above verifies
the same endpoint logic and response shape without depending on Gemini's response time.
`test_send_message_runs_real_assessment_when_nothing_left_to_ask` (fakes-based) is what actually
proves a real Gemini-shaped success response flows through correctly.

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
and Phase 9's vitals now both exist, but this module hasn't been wired to either yet (they'd
extend `identify_missing_info`'s priority tiers, not the RUN_ASSESSMENT wiring Phase 12 added,
which is a separate concern). Health Connect is Android-only (Phase 10); Apple HealthKit and
other platforms (Fitbit, Withings) remain unimplemented — no iOS/Mac environment exists on this
machine to build HealthKit against, and no cloud-platform developer account was set up for the
others. Background/automatic Health Connect sync (as opposed to the explicit button) is not
built — matches the MVP scope decided for that phase, not a gap. TTS has no streaming synthesis,
and — unchanged by Phase 12 — audio playback is still explicit-tap-only, never automatic; only
the *text* reply became automatic this phase. 13 of the 15 `ux.screens` (onboarding, consent,
patient_profile, medical_history, medications, allergies, measurements, evidence,
safety_warnings, measurement_history, settings) remain unbuilt on mobile — a deliberate Phase 12
scope decision (see "Complete pipeline integration (Phase 12)" above), not an oversight; their
backend APIs already exist from Phase 1 onward. 4 of 5 `ux.confirmation_required_when` triggers
have no real detection signal or mobile surface yet (only `high_risk_recommendation_considered`
is built) — see the same section for exactly why each is deferred rather than faked.
