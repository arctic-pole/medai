# MEDAI — Architecture

> Stub created in Phase 0. Expanded as later phases land (see `IMPLEMENTATION_PLAN.md`).

## Stack

- Mobile: Flutter
- Backend: Python + FastAPI
- Database: PostgreSQL (+ pgvector extension for embeddings, see `docker-compose.yml`)
- AI providers: accessed only through provider-abstraction interfaces (`app/providers/`) —
  `LLMProvider`, `SpeechToTextProvider`, `TextToSpeechProvider`, `EmbeddingProvider`,
  `VectorStore`, `MedicalKnowledgeProvider`, `DeviceAdapter`. No concrete vendor is committed
  to in code without the user's explicit sign-off (see `IMPLEMENTATION_PLAN.md`'s consolidated
  decisions list).

## Canonical pipeline

Per `medai_spec.yaml` `architecture.canonical_pipeline`:

```
USER → AUDIO → STT → STRUCTURED_PATIENT_STATE → FOLLOW_UP_QUESTIONS
     → VITAL/HEALTH_DATA → EVIDENCE_RETRIEVAL → CLINICAL_REASONING
     → DETERMINISTIC_SAFETY → MEDICATION_SAFETY → OUTPUT_VALIDATION
     → TEXT_RESPONSE → OPTIONAL_TTS
```

`patient_state`, `safety_engine`, and `output_validator` must never be bypassed
(`architecture.bypass_forbidden`); `medication_safety` carries the same constraint via its own
rule (see `IMPLEMENTATION_PLAN.md` audit finding #1 for the spec inconsistency this creates).

## Diagrams

Required (per `medai_spec.yaml` `documentation.required_diagrams`), to be added under
`docs/diagrams/` as the relevant phase lands: complete_system_architecture, voice_pipeline,
patient_state_pipeline, RAG_pipeline, vital_pipeline, safety_pipeline, medication_pipeline,
database_architecture, deployment_architecture.
