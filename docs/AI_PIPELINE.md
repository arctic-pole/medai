# MEDAI — AI Pipeline

> Filled in incrementally as each AI-related phase lands. This is the Phase 7 state.

## Canonical pipeline (medai_spec.yaml architecture.canonical_pipeline)

```
USER → AUDIO → STT → STRUCTURED_PATIENT_STATE → FOLLOW_UP_QUESTIONS
     → VITAL/HEALTH_DATA → EVIDENCE_RETRIEVAL → CLINICAL_REASONING
     → DETERMINISTIC_SAFETY → MEDICATION_SAFETY → OUTPUT_VALIDATION
     → TEXT_RESPONSE → OPTIONAL_TTS
```

Built so far: `STT` (on-device, mobile-side, Phase 2) → `STRUCTURED_PATIENT_STATE` (partial —
symptom extraction only, Phase 3) → `FOLLOW_UP_QUESTIONS` (Phase 4, deterministic) ...
`EVIDENCE_RETRIEVAL` (Phase 5) → `CLINICAL_REASONING` (Phase 6) → `DETERMINISTIC_SAFETY` +
`MEDICATION_SAFETY` (Phase 7, this doc). All of Phase 6/7 are internal capabilities only — not
wired into the conversation loop or exposed via any endpoint, see below. `VITAL/HEALTH_DATA`
(Phase 9) and `OUTPUT_VALIDATION` (Phase 8) onward are still later phases.

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

Model: `gemini-3.8-flash` by default (`GEMINI_MODEL` env var) — the current model at the time
this was wired in; change it any time via `.env`, no code change needed.

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

- **Internal capability only — no API endpoint, by deliberate scoping decision.**
  `architecture.bypass_forbidden` requires output to pass through `safety_engine` (Phase 7) and
  `output_validator` (Phase 8) before reaching a user; neither exists yet, so exposing this via
  `/assessment` now would create exactly the bypass the spec prohibits. `generate_assessment()`
  is called directly by tests and the live-verification script referenced below — Phase 12
  ("complete pipeline") is where this gets chained together with the gates that don't exist yet.
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

- **Internal capability only — same scoping as Phase 6, and for the same reason.** No API
  endpoint. `architecture.bypass_forbidden` lists `safety_engine` explicitly as never to be
  bypassed; there's nothing yet downstream of it (`output_validator`, Phase 8) for an endpoint
  to safely hand a decision to. `evaluate_safety()` and `check_candidate_medication()` are
  called directly (tests, and the live-verification script referenced below).
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

## Not yet implemented

`output_validator` (Phase 8); the conversation manager's `emergency_indicators` question tier
is still unpopulated (see the conversation manager section above) — Phase 7's vital-threshold
rules exist now, but nothing feeds them real vitals yet, and wiring safety_engine/medication
safety into the live conversation loop is separate work Phase 6/7 deliberately didn't do (see
"internal capability only" above); and everything from Phase 9 (vitals/devices) onward.
