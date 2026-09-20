# Known Limitations

> Updated as each phase lands. See `IMPLEMENTATION_PLAN.md` for the full phase plan and its
> consolidated list of open decisions.

## Current phase: 0 — Foundation

- No AI features exist yet (by design — `medai_spec.yaml` `phases.0_foundation.constraint`).
- Mobile app is not yet scaffolded — the Flutter SDK was not available in the environment used
  to bootstrap this repo. See `mobile/README.md`.
- No concrete AI/data provider (LLM, STT, TTS, embeddings, vector store, medical knowledge
  source, medication database) has been chosen. See `IMPLEMENTATION_PLAN.md`'s consolidated
  decisions list.
- No compliance posture (HIPAA/GDPR-equivalent or explicit non-claim) has been adopted yet.
- This is a prototype. It is not a licensed medical device, not a diagnostic system, and must
  never be presented as either (`medai_spec.yaml` `system_disclaimers`).
