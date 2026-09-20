# MEDAI — Spec Audit & Phase-Wise Implementation Plan

This document audits `medai_spec.yaml` (the authoritative project specification) and expands its
`phases:` block into a concrete, actionable build plan. Nothing here overrides the spec — per
`agent_rules.change_control`, any actual change to the spec requires the phrase
**"CHANGE SPECIFICATION"** from the user. Findings below are reported, not silently resolved.

---

## Part 1 — Audit Findings

| # | Finding | Location | Severity |
|---|---------|----------|----------|
| 1 | `architecture.bypass_forbidden` lists `[patient_state, safety_engine, output_validator]` but omits `medication_safety`, even though `medication_safety.rule` separately states "System must not bypass this pipeline." The canonical list of non-bypassable components is inconsistent. | `architecture.bypass_forbidden` (~line 87) vs `medication_safety.rule` (~line 380) | Medium — recommend either adding `medication_safety` to `bypass_forbidden` or confirming the separate rule is intentionally equally binding. |
| 2 | `prompt_safety` has two rule-like keys, `rule` and `rule2`, apparently because YAML forbids duplicate keys in one mapping. Functionally fine, but confusing to read/maintain. | `prompt_safety.rule` / `prompt_safety.rule2` (~lines 460–469) | Low — cosmetic. Recommend renaming to `rule_untrusted_data_handling` / `rule_trust_precedence`, or converting to a `rules: []` list. |
| 3 | Five phases have no explicit `pass` exit criterion, unlike the other ten: `0_foundation`, `10_health_platform_integration`, `11_TTS`, `13_security_hardening`, `14_evaluation`. Without a pass gate, "done" is ambiguous for these phases. | `phases.*` | Medium — concrete pass criteria are proposed for each in Part 2 below, for the user to adopt or amend. |
| 4 | No named data-handling/compliance posture (e.g., a HIPAA- or GDPR-equivalent stance, or an explicit non-claim) despite the system handling structured health data — `security` covers technical controls (TLS, encryption, access control, audit logs) but not a stated regulatory posture. This affects encryption-at-rest design and retention/consent handling as early as Phase 1. | `security` (whole section) | Medium — recommend the user state a posture before Phase 1 locks in DB design. |
| 5 | No concrete vendor is named anywhere for `LLMProvider`, `SpeechToTextProvider`, `TextToSpeechProvider`, `EmbeddingProvider`, `VectorStore`, `MedicalKnowledgeProvider`, or the medication database. This is very likely intentional (the whole architecture is provider-abstracted), but each is a real decision that will block a specific phase unless resolved in advance. | `architecture.provider_interfaces`, `knowledge_base`, `medication_safety` | Informational — not a defect, but tracked as open decisions per phase in Part 2. |
| 6 | No authoritative source is named for emergency/safety thresholds (`safety_engine.emergency_triage`) or physiological-plausibility bounds (`vital_system.validation_stages`). The spec correctly forbids inventing these ("Never fabricate... doses, contraindications..."; "Never hard-code arbitrary medical thresholds without an authoritative source"), so this is a required input, not a gap in the spec itself. | `safety_engine`, `vital_system.validation_stages` | Informational — flagged as a hard blocker for Phase 7/9, tracked below. |
| 7 | YAML syntax itself parses cleanly — manually verified line-by-line; no true duplicate mapping keys exist at any nesting level (finding #2 above is a naming smell, not a parse error). Python/`pyyaml` tooling was not available in this environment to cross-check programmatically; recommend running a `yaml.safe_load` + duplicate-key check in CI once the repo exists (Phase 0). | whole file | Informational |

---

## Part 2 — Phase-Wise Build Plan

### Guiding technical decisions (apply to all phases)

**Minimal Postgres-only stack**, per the spec's "never introduce unnecessary microservices" rule:
- Backend: Python 3.12 + FastAPI + SQLAlchemy 2.x (async) + Alembic migrations
- Database: PostgreSQL only — use the **pgvector** extension for `knowledge_chunks` embeddings instead of standing up a separate vector DB service, unless the user overrides this
- Background jobs (RAG ingestion, retries): a Postgres-backed job table + worker rather than adding Redis/Celery/RabbitMQ, unless load later proves this insufficient
- Mobile: Flutter (Dart), single app, no React Native (per spec: "React Native only if explicitly authorised")
- Auth: FastAPI + JWT (short-lived access + refresh), password hashing via argon2/passlib
- Every AI-facing integration sits behind the spec's named provider interfaces (`LLMProvider`, `SpeechToTextProvider`, `TextToSpeechProvider`, `EmbeddingProvider`, `VectorStore`, `MedicalKnowledgeProvider`, `DeviceAdapter`) — no vendor is chosen here; each is called out as a decision point below, at the phase where it first becomes load-bearing.

**Proposed repo layout (established in Phase 0):**
```
medai/
  medai_spec.yaml
  IMPLEMENTATION_PLAN.md
  backend/
    app/
      api/              # routers per spec's /auth,/patient,/profile,... groups
      core/              # config/settings (env-driven), security
      db/                 # SQLAlchemy models, session, alembic/
      providers/           # abstract interfaces + concrete adapters
        llm/ stt/ tts/ embeddings/ vector_store/ medical_knowledge/ devices/
      patient_state/        # canonical state schema/builder/updater
      conversation/          # conversation manager, question prioritisation
      rag/                    # ingestion, chunking, retrieval, reranking
      reasoning/               # clinical reasoner orchestration
      safety/                   # deterministic safety engine, medication safety
      validation/                # output validator, safe fallback
      schemas/                    # pydantic request/response + output_schema
      audit/                        # audit logging
    tests/
      unit/ integration/ e2e/ safety_adversarial/
    alembic/
    pyproject.toml
  mobile/
    lib/
      screens/    # per spec's `ux.screens` list
      services/    # API client, audio capture, playback
      state/        # app state management
    test/
  docs/
    README.md ARCHITECTURE.md API.md DATABASE.md AI_PIPELINE.md
    SAFETY.md SECURITY.md TESTING.md DEPLOYMENT.md KNOWN_LIMITATIONS.md
    diagrams/
  .github/workflows/   # or equivalent CI
  .env.example
```

---

### Phase 0 — Foundation
*Constraint (spec): "No AI features."*

- `git init`; branch model (`main`, `develop`, `feature/*`); commit-prefix convention (`feat|fix|test|docs|refactor|chore`) documented in `CONTRIBUTING.md`
- Backend skeleton: FastAPI app factory, `/healthz` endpoint, settings via `pydantic-settings` reading only from environment variables (`.env.example` committed, `.env` gitignored)
- Frontend skeleton: Flutter app boots to a placeholder screen; confirm target platforms (see decision below)
- DB connection: local Postgres (docker-compose), Alembic initialized with an empty baseline migration, connection verified on FastAPI startup
- CI: pytest (backend) and `flutter test` (mobile) wired to run on push/PR, even with placeholder tests initially
- `README.md` stating the project's purpose and explicit non-goals verbatim in spirit from `meta.not_a` (not an autonomous doctor / prescription service / diagnostic system / emergency service)
- `ARCHITECTURE.md` stub with a placeholder pipeline diagram

**Proposed pass criteria:** Backend and mobile skeletons both build/run locally and in CI; FastAPI connects to Postgres and serves a health endpoint; CI is green on a trivial test in each; README/ARCHITECTURE stubs exist; zero AI/provider code present.

**Open decisions:** target mobile platforms (Android only vs Android+iOS).

---

### Phase 1 — Patient Data

- DB models: `users`, `patients`, `patient_profiles`, `medical_history`, `allergies`, `current_medications` — fields/relations designed now (spec defines only the table names). `patient_profiles` covers all of `patient_profile.required_fields` (patient_uuid, age, sex, height_cm, weight_kg, known_conditions, allergies, current_medications, relevant_history, emergency_contact, consent_status) plus `security.consent_record_fields` (user, consent_type, timestamp, version, status)
- Auth: registration/login, JWT issuance, session handling
- CRUD APIs for `/auth`, `/patient`, `/profile`, `/history`, `/allergies`, `/medications` — each with request/response schema, auth requirement, validation, documented error responses (`api_endpoints.every_endpoint_requires`)
- UUIDs as primary identifiers throughout (`security.minimum_requirements`)
- Only collect fields a shipped feature actually needs (`patient_profile.rule`)
- Audit log skeleton: `audit_logs` table + a write-through helper on mutating endpoints, restricted to `security.logging.allowed` fields, explicitly excluding `security.logging.avoid` fields from day one
- Mobile: consent, onboarding, patient_profile, medical_history, allergies, medications screens (manual entry — this is one of the `ux.manual_interaction_permitted_for` cases)

**Pass (spec-given):** "Patient data can be created, read, updated, and securely stored."

**Open decisions:** encryption-at-rest approach for sensitive columns; the data-handling/compliance posture flagged in audit finding #4.

---

### Phase 2 — Conversation
*Constraint (spec): "No medical reasoning yet."*

- `conversations`, `messages` tables
- Mobile: microphone capture UI (push-to-talk or VAD-triggered), text-response playback (no TTS yet)
- STT integration behind `SpeechToTextProvider` (first real provider decision — consider a mock/local provider first to unblock plumbing work without vendor lock-in)
- `/conversations`, `/messages` endpoints storing the raw transcript, explicitly tagged `user_reported`/untrusted, not yet structured state
- A stub "AI" response (e.g. literal echo of the transcript) purely to prove the mic→STT→API→UI loop end-to-end — clearly labeled scaffolding, replaced in Phase 3+, not real reasoning

**Pass (spec-given):** "User can speak and receive a text response."

**Open decisions:** concrete `SpeechToTextProvider`.

---

### Phase 3 — Patient State

- Canonical `PatientState` pydantic schema exactly per `patient_state.schema`: `patient{id,age,sex,height_cm,weight_kg}`, `symptoms[]`, `medical_history[]`, `allergies[]`, `medications[]`, `vitals{}`, `recent_events[]`, `risk_factors[]`, `unknowns[]`, `conversation_context{}`, `data_quality{}`
- Symptom extraction module (first real use of `LLMProvider`): transcript → structured `symptom_extraction.fields` (symptom, onset, duration, severity 0–10, frequency, location, progression, triggers, relieving_factors, associated_symptoms, certainty)
- `missing_value_states` (known/unknown/not_provided/uncertain/stale) and `data_source_distinction` (user_reported/device_measured/database_derived/model_inferred/clinician_entered) are first-class fields, never collapsed into an assumed default
- State updates versioned per conversation (`patient_state_version`, per `traceability.per_assessment_record`)
- Unit tests for extraction accuracy against hand-built fixtures — never derive "expected" answers from model guesses (applies from here through Phase 14)

**Pass (spec-given):** "A conversation can be transformed into the canonical patient state."

**Open decisions:** concrete `LLMProvider` for extraction; must support structured/function-calling output where available.

---

### Phase 4 — Conversation Manager

- Flow exactly per spec: `receive_input → update_state → identify_missing_info → check_if_changes_next_action → ask_highest_priority_question → repeat`
- Question priority order exactly per spec: emergency_indicators > high_impact_missing_info > medication_allergy_safety > relevant_history > required_measurements > lower_priority_context
- `pre_question_checks` gate every question: already_in_state, available_from_health_source, obtainable_from_measurement, actually_necessary
- Action-proposal/decision split: LLM proposes one of `ASK_QUESTION, GET_VITAL, RETRIEVE_HISTORY, RETRIEVE_EVIDENCE, RUN_ASSESSMENT, ESCALATE, RESPOND`; an application-layer arbiter checks the proposal is permitted before executing it — the LLM never triggers a side effect directly
- Mobile: natural conversational turn-taking, no internal state/JSON ever surfaced (`ux` rule)

**Pass (spec-given):** "AI can conduct a structured symptom interview."

**Open decisions:** none new. Confirm the source for `emergency_indicators` conditions before Phase 7 needs authoritative thresholds — don't invent them here either.

---

### Phase 5 — Medical Knowledge (RAG ingestion + retrieval)

- `clinical_sources`, `knowledge_chunks` tables; `knowledge_chunks.embedding` as a `pgvector` column
- Source metadata schema exactly per `knowledge_base.source_metadata` (title, publisher, url_or_reference, publication_date, update_date, source_type, version); versioning enforced — never overwrite, always a new row with `retrieval_date`/`effective_date`/`superseded_status`
- Ingestion pipeline (admin/offline job, not user-facing): `SOURCE_INGESTION → CLEANING → METADATA → CHUNKING → EMBEDDINGS → VECTOR_DB`
- `EmbeddingProvider` and `MedicalKnowledgeProvider` implemented against chosen concrete sources
- Retrieval: `RETRIEVAL → RERANKING → EVIDENCE_PACKAGE`, scoped strictly to `rag_pipeline.retrieval_scope` (symptoms, patient_context, medications, vitals, identified_risks) — never arbitrary documents to the LLM
- `/evidence` endpoint for retrieval-by-topic testing

**Pass (spec-given):** "Given a clinical topic, relevant evidence can be retrieved and traced to its source."

**Open decisions (high stakes):**
- Concrete source(s) for each `knowledge_base.approved_sources` category, including licensing/usage rights for ingestion
- Concrete `EmbeddingProvider`
- Reranking approach (cross-encoder model vs similarity threshold)

---

### Phase 6 — Clinical Reasoning

- Assemble `evidence_package` exactly per its schema: patient_state, relevant_vitals, relevant_history, retrieved_evidence, known_unknowns, safety_flags
- Clinical reasoner calls `LLMProvider` with exactly the six allowed prompt inputs (`clinical_reasoner.prompting.receives`): system_policy, task, patient_state, evidence, safety_flags, output_schema — never uncontrolled application state
- Defense-in-depth at the parsing layer against `clinical_reasoner.must_not` behaviors (invented evidence/doses/certainty), ahead of the real deterministic gates in Phase 7/8
- Structured-output parsing against `output_schema` (partial here; full validation is Phase 8); reject/retry on malformed JSON
- User text explicitly handled as untrusted per `prompt_safety.untrusted_inputs`, never interpreted as instructions

**Pass (spec-given):** "Model produces schema-valid reasoning grounded in retrieved evidence."

**Open decisions:** reconfirm Phase 3's `LLMProvider` choice actually supports reliable structured output for this use; revisit if not.

---

### Phase 7 — Safety Engine

- Deterministic (non-LLM) rule engine: inputs `[ai_output, patient_state, vitals, medication_data, safety_rules]`, outputs `[PASS, MODIFY, BLOCK, ESCALATE]`
- `safety_rules` store using `safety_engine.emergency_triage.rule_schema` (rule_id, condition, severity=critical, action=ESCALATE, source, version); every rule must cite an authoritative source — STOP and ask if one isn't available for a needed rule, per audit finding #6
- `emergency_triage` runs before normal treatment reasoning in the pipeline order
- Medication safety pipeline exactly per spec: `CANDIDATE_MEDICATION → MEDICATION_DB → ALLERGY_CHECK → CURRENT_MED_CHECK → CONDITION_CHECK → CONTRAINDICATION_CHECK → INTERACTION_CHECK → VALIDATOR → ALLOWED|BLOCKED|REQUIRES_REVIEW`
- Fail-closed on internal safety-engine error — no patient-specific guidance released
- `safety_events` logs every BLOCK/ESCALATE/MODIFY with rule_id and version

**Pass (spec-given):** "Safety rules can block unsafe model output."

**Open decisions (high stakes):**
- Authoritative source(s) for emergency/vital thresholds and clinical safety rules — must come from the user/clinical input, never invented
- Concrete medication database for `MEDICATION_DB`, including licensing

---

### Phase 8 — Output Validator

- Validator runs the 10 checks in order (`output_validator.checks`): schema_compliance, unsupported_claims, evidence_availability, dangerous_language, prescription_like_directives, contradictions, safety_engine_result, medication_validation, uncertainty_requirements, escalation_requirements
- On failure: never send to user; bounded retry against the reasoner with feedback, else `safe_fallback` (status=caution, summary, recommended_next_steps, limitations — exact fields from spec)
- Validator's own failure is itself fail-closed
- Enforce in code that no path other than this validator can emit a response to the client

**Pass (spec-given):** "No final clinical response reaches the user without validation."

**Open decisions:** confirm dangerous-language/prescription-like-directive detection is deterministic-pattern-based first (recommended, to avoid another unbounded LLM dependency in the safety-critical path), vs a secondary model check as a supplement.

---

### Phase 9 — Vital Ingestion

- `vitals`, `devices`, `measurements` tables; canonical measurement schema exactly per `vital_system.canonical_measurement` (measurement_id, patient_id, type, value, unit, timestamp ISO8601, source, device_id, quality good/acceptable/poor, confidence)
- `DeviceAdapter` interface + a manual-entry adapter and a simulated-data adapter first, per spec: "Initial dev may use simulated/manual measurements before real device integrations"
- Validation pipeline exactly per spec: format → unit → timestamp → missing_values → physiological_plausibility → device_signal_quality → repeat_if_required; suspicious measurement → `MEASUREMENT_UNRELIABLE`, request another
- Device failure path: `{status: unavailable, reason: DEVICE_ERROR}`; conversation manager only falls back to manual entry after automatic retrieval fails (`automatic_retrieval_preference`: DEVICE → HEALTH_PLATFORM → MEDAI)
- `/vitals`, `/devices` endpoints; measurement history screen

**Pass (spec-given):** "Vitals can enter the canonical patient state."

**Open decisions:** authoritative source for physiological-plausibility bounds per vital type (audit finding #6) — confirm whether this is the same source used for Phase 7's safety thresholds or a distinct one.

---

### Phase 10 — Health Platform Integration

- Concrete `DeviceAdapter` implementations for real wearable/health-platform data, chosen only after Phase 9's abstraction is proven
- Preserve `automatic_retrieval_preference` ordering (device/platform before manual entry)
- Verify the clinical engine has zero device-specific code paths (`vital_system.rules`: "Clinical engine must not depend on a specific wearable") via an adapter-swap regression test

**Proposed pass criteria** *(spec has none — proposed here)*: at least one real (non-simulated) device or health-platform adapter integrated end-to-end (adapter → normalised measurement → vital_service → patient_state) with no change to `clinical_reasoner`/`safety_engine` code; adapter-swap regression test passes; the unavailable/failure path is verified against a real adapter.

**Open decisions:** which concrete health platform(s)/device(s) to target first.

---

### Phase 11 — TTS

- `TextToSpeechProvider` interface + concrete implementation
- Wired strictly after the output validator: `VALIDATED_TEXT → TTS → SPEAKER`; a code-level guard/test ensures no path can call TTS with unvalidated text
- Mobile: interrupt/barge-in playback, streaming if the provider supports it, transcript/text always available alongside audio (accessibility requirement)
- No always-listening behavior beyond explicit mic activation

**Proposed pass criteria** *(spec has none — proposed here)*: a validated response can be spoken via TTS; the user can interrupt mid-utterance; an automated check confirms TTS is only ever invoked on validator-approved text; text form remains available regardless of TTS use.

**Open decisions:** concrete `TextToSpeechProvider`; streaming vs non-streaming scope for this phase.

---

### Phase 12 — Complete Pipeline

- Full end-to-end wiring in the mobile app of the `architecture.canonical_pipeline`: USER → AUDIO → STT → STRUCTURED_PATIENT_STATE → FOLLOW_UP_QUESTIONS → VITAL/HEALTH_DATA → EVIDENCE_RETRIEVAL → CLINICAL_REASONING → DETERMINISTIC_SAFETY → MEDICATION_SAFETY → OUTPUT_VALIDATION → TEXT_RESPONSE → OPTIONAL_TTS
- Session persistence: `session_auto_preserved`, `resume_previous_consultation`, `automatic_profile_memory`
- Confirmation prompts wired at all five `ux.confirmation_required_when` triggers
- Full `ux.screens` set implemented

**Pass (spec-given):** "Complete end-to-end demonstration works."

**Open decisions:** none new — this phase integrates prior decisions.

---

### Phase 13 — Security Hardening

- Secrets management: automated secret-scan in CI, all credentials via env vars, `.env` never committed
- Access control: per-endpoint authorization (users can only access their own patient data), role checks on any admin/ingestion endpoints
- Encryption: TLS everywhere non-local; encrypted sensitive DB columns (decision carried from Phase 1)
- Audit logs: confirm coverage on all mutating and assessment-producing endpoints; enforce the allowed/avoided field lists from `security.logging`
- Privacy controls: data export/delete-my-data flow if in scope — flag as a decision, since the spec doesn't explicitly require it but `minimal_data_collection` plus the missing compliance posture (audit finding #4) suggests it may be expected
- Prompt-injection test suite specifically targeting `prompt_safety.trust_hierarchy` violations (user text or retrieved documents attempting to override system/safety rules)

**Proposed pass criteria** *(spec has none — proposed here)*: secret-scan passes in CI with zero findings; an access-control test suite confirms cross-user data access is denied; TLS enforced in all non-local environments; audit-log field allowlist enforced by a test; a prompt-injection adversarial subset passes, demonstrating user/retrieved text cannot override `system_specification` or `deterministic_safety_rules`.

**Open decisions:** whether to adopt a formal compliance posture now (ties back to audit finding #4) before hardening work locks in a design.

---

### Phase 14 — Evaluation

- Unit tests: symptom_extraction, state_updates, vital_validation, safety_rules, medication_checks, schema_validation, retrieval, output_validation
- Integration tests across every pipeline seam: STT→extraction, extraction→state, state→RAG, RAG→reasoner, reasoner→safety, safety→validator
- E2E tests: complete conversations from USER_SPEAKS to FINAL_VALIDATED_RESPONSE
- Safety/adversarial suite per `testing.safety_adversarial`: emergency_symptoms, missing_data, contradictory_data, invalid_vitals, medication_conflicts, allergies, hallucination_attempts, prompt_injection, malformed_AI_output, insufficient_evidence — including cases whose correct answer is UNKNOWN/INSUFFICIENT_INFORMATION/SEEK_PROFESSIONAL_EVALUATION
- `evaluation_dataset` built to spec's schema, covering every `case_types` value, with expected answers sourced from validated reference material — never from model guesses
- `evaluation_metrics` computed per group (extraction, retrieval, safety, generation, system); safety metrics are mandatory gates, not just reported figures
- Results recorded in `docs/KNOWN_LIMITATIONS.md` plus a benchmark-results artifact

**Proposed pass criteria** *(spec has none — proposed here)*: all four test tiers (unit/integration/e2e/safety-adversarial) pass in CI; the benchmark dataset covers every `case_type`; safety metrics meet thresholds the user explicitly sets (never invented by the agent); results are recorded in `docs/`; no known open P0 safety failure.

**Open decisions:** the actual numeric acceptance thresholds for safety metrics (e.g. minimum emergency-detection sensitivity) — the spec gives none, and none should be invented; the user should set these, ideally with clinical input.

---

### Cross-cutting: UX validation (every phase)

At the close of each phase, explicitly answer the spec's own question: *"Can the user accomplish this through the simplest possible voice-first interaction?"* — add this as a line item in that phase's report, fitting the spec's `report_format`: `TASK / PHASE / CHANGES / TESTS / RESULT / LIMITATIONS / NEXT`.

### Documentation cadence

Rather than a separate final phase, the required `docs/*.md` files and diagrams are written incrementally as each phase lands (e.g. `DATABASE.md` grows during Phases 1/5/9; `AI_PIPELINE.md` and its diagrams during Phases 3–8; `SAFETY.md` during Phase 7; `SECURITY.md` during Phase 13) — consistent with `git.feature_requirements` requiring every feature to be documented, not just implemented.

---

## Consolidated list of decisions needing explicit user sign-off

1. Mobile platform scope (Android / iOS) — Phase 0
2. Field-level encryption approach for sensitive DB columns — Phase 1
3. Data-handling/compliance posture (audit finding #4) — Phase 1
4. Concrete `SpeechToTextProvider` — Phase 2
5. Concrete `LLMProvider` for extraction/reasoning — Phase 3 (reconfirm at Phase 6)
6. Concrete `MedicalKnowledgeProvider` source(s), `EmbeddingProvider`, reranking approach — Phase 5
7. Authoritative source(s) for emergency/safety thresholds and rules — Phase 7
8. Concrete medication database (`MEDICATION_DB`) — Phase 7
9. Authoritative source for physiological-plausibility vital bounds — Phase 9
10. Concrete health-platform/device targets — Phase 10
11. Concrete `TextToSpeechProvider`; streaming vs non-streaming — Phase 11
12. Privacy/data-subject-rights scope (export/delete) — Phase 13
13. Numeric safety-metric acceptance thresholds — Phase 14
