# MEDAI — AI Pipeline

> Filled in incrementally as each AI-related phase lands. This is the Phase 5 state.

## Canonical pipeline (medai_spec.yaml architecture.canonical_pipeline)

```
USER → AUDIO → STT → STRUCTURED_PATIENT_STATE → FOLLOW_UP_QUESTIONS
     → VITAL/HEALTH_DATA → EVIDENCE_RETRIEVAL → CLINICAL_REASONING
     → DETERMINISTIC_SAFETY → MEDICATION_SAFETY → OUTPUT_VALIDATION
     → TEXT_RESPONSE → OPTIONAL_TTS
```

Built so far: `STT` (on-device, mobile-side, Phase 2) → `STRUCTURED_PATIENT_STATE` (partial —
symptom extraction only, Phase 3) → `FOLLOW_UP_QUESTIONS` (Phase 4, deterministic) ...
`EVIDENCE_RETRIEVAL` (Phase 5, this doc — not yet wired into the conversation loop itself, see
below). `VITAL/HEALTH_DATA` and everything from `CLINICAL_REASONING` onward are later phases
(6, 9–11).

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

## Conversation manager (Phase 4)

`app/conversation/manager.py` + `app/conversation/missing_info.py` implement
`conversation_manager.flow`: on each `POST /messages`, the canonical patient state is
re-assembled (`build_patient_state`), compared against a fixed set of clinically-relevant
fields, and the single highest-priority missing one becomes a follow-up question — replacing
Phase 2's echo scaffold, exactly as that scaffold's own docstring said it would.

- **Deterministic by design, not LLM-driven.** `identify_missing_info` and `select_action` never
  call an LLM — they inspect `PatientState` (itself built only from DB rows) and apply
  `conversation_manager.question_priority` in a fixed order. This means the interview works
  fully even with `OPENAI_API_KEY` unset (as it currently is) — a deliberate choice given Phase
  3's provider isn't wired to a real key yet, not a spec requirement. The LLM is used, when
  configured, only for *phrasing* the chosen question more naturally
  (`manager.py:_phrase_question`) — a best-effort NLG step with a deterministic template
  fallback on any failure, never the decision itself.
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

## Not yet implemented

The full `clinical_reasoner` (Phase 6) and everything downstream of it — including real
emergency detection and vital-based questions (see the conversation manager section above).
