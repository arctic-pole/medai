# MEDAI — Security

> Expanded fully in Phase 13 (Security Hardening). This is the Phase 1 baseline.

## Data-handling posture (interim)

`medai_spec.yaml` names no compliance framework (audit finding #4 in `IMPLEMENTATION_PLAN.md`).
Until the user adopts a specific posture, this codebase treats all patient data (profile,
history, allergies, medications) **as if it were regulated health data**: encrypted at rest at
the application layer, never logged in raw form, access-controlled per-user, and never sent to
any third party. This is a precaution, not a compliance claim — see `docs/KNOWN_LIMITATIONS.md`
and `medai_spec.yaml` `system_disclaimers`.

## Implemented (Phase 1)

- **Transport**: local dev runs over HTTP; TLS termination is a Phase 13 deployment concern.
- **Auth**: JWT access (15 min) + refresh (7 day) tokens, argon2 password hashing.
- **Access control**: every patient-data endpoint resolves the current user's own `Patient` row;
  entries owned by another patient 404 rather than 403 (avoids confirming existence).
- **Encryption at rest**: `app/db/encrypted_types.EncryptedString` (Fernet) on sensitive free-text
  columns — see `docs/DATABASE.md`.
- **Audit logging**: `app/audit/middleware.py` writes one row per request restricted to exactly
  the fields `security.logging.allowed` permits (request_id, user_uuid, timestamp, module,
  latency, error_code) — request/response bodies are never logged.
- **Secrets**: all credentials read from environment variables (`app/core/config.py`); `.env` is
  gitignored; `.env.example` carries only clearly-marked dev-only default values.
- **Identifiers**: UUID primary keys throughout.

## Deferred to Phase 13

Formal secret-scanning in CI, infra-level encryption/TLS enforcement, granular RBAC (currently
single role: "the authenticated user, for their own data"), data export/delete flow, the
prompt-injection-specific adversarial test suite (Phase 14 builds on this), and locking down the
dev-only permissive CORS policy (`app/main.py`, `allow_origins=["*"]`, active only when
`ENVIRONMENT=development`) added in Phase 2 so the Flutter web client can reach the API locally.

Phase 2 also extended `EncryptedString` (Phase 1) to `messages.content` — conversation
transcripts can carry the same sensitivity as medical history/allergies.
