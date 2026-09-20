# MEDAI — AI Pipeline

> Filled in incrementally as each AI-related phase lands. This is the Phase 3 state.

## Canonical pipeline (medai_spec.yaml architecture.canonical_pipeline)

```
USER → AUDIO → STT → STRUCTURED_PATIENT_STATE → FOLLOW_UP_QUESTIONS
     → VITAL/HEALTH_DATA → EVIDENCE_RETRIEVAL → CLINICAL_REASONING
     → DETERMINISTIC_SAFETY → MEDICATION_SAFETY → OUTPUT_VALIDATION
     → TEXT_RESPONSE → OPTIONAL_TTS
```

Built so far: `STT` (on-device, mobile-side, Phase 2) → `STRUCTURED_PATIENT_STATE` (partial —
symptom extraction only, Phase 3, this doc). Everything from `FOLLOW_UP_QUESTIONS` onward is
later phases (4–11).

## Provider abstraction

`app/providers/llm/base.py` defines `LLMProvider` (`generate`, `structured_generate`, `stream`)
per `architecture.provider_interfaces`. The only concrete implementation is
`app/providers/llm/openai_provider.py` (`OpenAIProvider`) — **decided by the user in Phase 3**,
not fabricated. It is selected in exactly one place: `app/providers/llm/get_llm_provider()`
(`app/providers/llm/__init__.py`); swapping providers means writing a new `LLMProvider`
subclass and changing that one function.

`OpenAIProvider` fails closed: with no `OPENAI_API_KEY` configured, every method raises
`LLMNotConfiguredError` rather than returning a fabricated response
(`error_handling.fail_closed_principle`). As of this writing no key has been supplied, so
extraction is implemented and tested (against a `FakeLLMProvider`, see `backend/tests/fakes.py`)
but has not been exercised against the real OpenAI API — see `docs/KNOWN_LIMITATIONS.md`.

Model: `gpt-4o-mini` by default (`OPENAI_MODEL` env var) — chosen for structured-output support
at reasonable cost for a prototype; change it any time via `.env`, no code change needed.

## Symptom extraction (Phase 3)

- **Input**: the user-role messages of one conversation (`app/api/symptoms.py:extract_symptoms`).
- **Prompting**: `app/patient_state/extraction.py` — a system prompt instructing the model to
  extract only what the patient actually stated, leave unmentioned fields null, and never
  suggest a cause, condition, or treatment (this endpoint performs *extraction*, not reasoning,
  per `phases.2_conversation.constraint` carrying into Phase 3).
- **Output**: `SymptomExtractionResult` (a Pydantic model wrapping `list[ExtractedSymptom]`),
  requested via `structured_generate` (OpenAI's structured-outputs / `.chat.completions.parse`,
  which validates the model's JSON against the Pydantic schema before it's ever used) —
  satisfies `clinical_reasoner.prompting.rule`: "use structured output wherever supported."
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

## Not yet implemented

`FOLLOW_UP_QUESTIONS`/`conversation_manager` question logic (Phase 4), evidence retrieval / RAG
(Phase 5), the full `clinical_reasoner` (Phase 6), and everything downstream of it.
