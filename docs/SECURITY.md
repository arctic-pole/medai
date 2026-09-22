# MEDAI — Security

> Phase 13 (Security Hardening). Supersedes the Phase 1 baseline this doc originally held —
> see git history for that version.

## Data-handling posture (interim)

`medai_spec.yaml` names no compliance framework (audit finding #4 in `IMPLEMENTATION_PLAN.md`).
This codebase treats all patient data (profile, history, allergies, medications, conversations,
vitals) **as if it were regulated health data**: encrypted at rest at the application layer
(with one disclosed exception — see "Encryption" below), never logged in raw form,
access-controlled per-user, and never sent to any third party beyond the explicitly-chosen
providers (Gemini for reasoning, MedlinePlus/openFDA for reference data). This is a precaution,
not a compliance claim — see `docs/KNOWN_LIMITATIONS.md` and `medai_spec.yaml`
`system_disclaimers`.

## Secrets management

- All credentials are read from environment variables (`app/core/config.py`), never
  hard-coded as the value actually used. `.env` is gitignored (confirmed never committed —
  `git log --all` for it is empty); `.env.example` carries only clearly-marked dev-only values.
- **Startup guard (Phase 13, a real vulnerability found and fixed)**: `JWT_SECRET_KEY` and
  `FIELD_ENCRYPTION_KEY` both shipped with well-known placeholder defaults so local setup works
  out of the box — but nothing previously stopped a real deployment from silently running with
  either one unchanged. Since both values are public (visible in this open-source repo),
  running with the default `JWT_SECRET_KEY` would let anyone forge valid access tokens for any
  user, and running with the default `FIELD_ENCRYPTION_KEY` would make every "encrypted at
  rest" column trivially decryptable. `Settings` now has a `model_validator` (`app/core/
  config.py`) that refuses to start — raises immediately, not a warning — if either value is
  still the placeholder while `ENVIRONMENT != "development"`. Verified live: startup with
  `ENVIRONMENT=production` and the default keys fails with a clear error naming exactly which
  secret(s) are the problem; startup with real generated values succeeds. `tests/unit/
  test_config.py`.
- **Automated secret-scanning in CI** (`.github/workflows/secret-scan.yml`): `gitleaks/
  gitleaks-action@v3`, on every push/PR plus a daily scheduled scan (to catch a secret that
  reaches history via some path this workflow itself didn't cover at the time). Free for this
  repo (personal-account repos don't need a license; only organizations do). A manual scan of
  the full git history for common key-shaped patterns (`AIza...`, `sk-...`, PEM private key
  headers) was also run before enabling this and found nothing — see commit history for Phase
  13 for the exact check.

## Access control

- Every patient-data endpoint resolves the caller's own `Patient` row via `get_current_patient`
  (`app/api/deps.py`) — there is no way to pass another patient's id in and have it honored.
  Entry-level endpoints (`/history/{id}`, `/allergies/{id}`, `/medications/{id}`) additionally
  verify `entry.patient_id == patient.id` before any read/write, and return `404` (not `403`)
  for another patient's entry — never confirms the entry exists at all.
- **Phase 13 audit**: every one of the 13 API routers was read and confirmed to follow this
  pattern with no exception; the one router that doesn't use `get_current_patient`
  (`/evidence` — public reference-material ingestion/search, not patient data) uses
  `get_current_user` instead (authenticated, but deliberately not patient-scoped, since the
  data itself isn't patient-specific).
- **No admin/RBAC role exists, and none was invented.** `medai_spec.yaml` names no admin
  concept. Every endpoint is either "the authenticated user, for their own data" or "any
  authenticated user" (evidence ingestion/search only) — a proportionate control for this
  prototype's threat model (a personal health assistant, not a multi-tenant SaaS with a
  provider/patient distinction). A real deployment serving multiple organizations would need to
  revisit this before, e.g., exposing `/evidence/ingest` (which makes real outbound network
  calls) to arbitrary users.
- Consolidated test coverage: `tests/integration/test_access_control.py` (no-auth-required
  sweep across every `GET`, cross-user `404` for allergies/medications/history PATCH+DELETE and
  conversation `GET`) plus the pre-existing per-feature tests this didn't duplicate
  (`test_conversation_flow.py`, `test_assessment.py`, `test_assessment_speech.py`,
  `test_vitals.py`, `test_patient_data.py`).

## Encryption

- **At rest**: `app/db/encrypted_types.EncryptedString` (Fernet, `FIELD_ENCRYPTION_KEY`) on
  every free-text column carrying clinical detail — medical history conditions/notes, allergy
  substances/reactions, medication names/dosages/frequencies, symptom fields, message content,
  emergency contact info. Application-level, independent of and complementary to disk-level
  encryption a real deployment's infrastructure would add.
- **Disclosed gap, not silently accepted**: numeric vital values (`measurements.value`,
  `vitals.value` — heart rate, SpO2, blood pressure, etc.) are **not** encrypted at rest, unlike
  every other sensitive column. `EncryptedString` only wraps `str` columns; encrypting a `Float`
  would need a new `EncryptedFloat`-style type (storing as encrypted text, cast back to float on
  read) plus a migration, and wasn't attempted in this phase — flagged here rather than declared
  done. The `type` label (e.g. `"heart_rate"`) is also unencrypted, so the *fact* that a vital
  of a given kind was recorded is visible at the DB level even before this gap is closed.
- **Transport (TLS)**: local dev runs over plain HTTP; this is a reverse-proxy/deployment
  concern this prototype has no real deployment target to configure against. For any real
  deployment: terminate TLS in front of `uvicorn` (e.g. Caddy or nginx, both of which can obtain
  and renew a certificate automatically) rather than serving TLS from `uvicorn` itself, and set
  `Strict-Transport-Security` at that layer. Not implemented here — documented as a concrete,
  actionable requirement rather than left vague.
- **Identifiers**: UUID primary keys throughout (`security.minimum_requirements: UUID_
  identifiers`) — no sequential/guessable ids anywhere.

## Audit logs

`app/audit/middleware.py` writes one `audit_logs` row per request (except `/healthz`), with
only the `security.logging.allowed` fields: `request_id`, `user_uuid`, `timestamp`, `module`
(the request path — never the query string), `latency_ms`, `error_code`. The `AuditLog` table
itself has no columns beyond this set, so there is no column a future bug in the middleware
could even accidentally put a request/response body into. Verified behaviorally, not just by
code inspection: `tests/integration/test_audit_log.py` sends a request carrying a genuinely
sensitive marker string and confirms it appears nowhere in the resulting `audit_logs` rows, and
confirms `module` is built from the path only, never a query string.

## Privacy controls

**User-confirmed scope: both export and delete.**

- **`GET /privacy/export`**: every table a patient's own data lives in, in one response —
  profile, medical history, allergies, medications, symptoms, conversations (with their
  messages), devices, measurements, vitals, safety events, consents, and — for transparency —
  the caller's own `audit_logs` rows. `EncryptedString` columns decrypt transparently on read,
  so this is real plaintext, correctly, since the export is for the data's own owner. Excludes
  `clinical_sources`/`knowledge_chunks` (public reference material, not patient data).
- **`DELETE /privacy/me`**: cascades a real `DELETE` across every patient-owned table, in
  explicit dependency order (`app/privacy/service.py:delete_patient_account` — no `ON DELETE
  CASCADE` is declared at the DB level, so this is deliberate application code, not implicit
  schema behavior, and is fully auditable by reading that one function). Requires re-proving the
  account password in the request body first — a stolen/leaked short-lived access token alone
  cannot trigger this irreversible action
  (`ux.manual_interaction_permitted_for: confirmation_of_ambiguous_critical_information`).
  **Deliberately does not delete `audit_logs`**: they carry only the allowed-field set (never
  raw health data, per the guarantee above), and retaining them past an account deletion is a
  defensible, common security practice (investigating an incident that happened before the
  deletion) rather than a privacy violation — a judgment call, stated here rather than made
  silently.
- **Verified live** against a running dev server with real data: a real account with real
  allergies/history/vitals exported correctly (including a real decrypted allergy reaction);
  cross-user export isolation confirmed (patient B's export never contains patient A's data);
  wrong-password delete correctly rejected with `401` and the account left untouched;
  correct-password delete returned `204`, the `users` row was genuinely gone (not just
  unlinked — confirmed by successfully re-registering the same email afterward), and the old
  access token immediately stopped working. `tests/integration/test_privacy.py`.
- No mobile UI exists for these endpoints yet — consistent with Phase 12's scope decision that
  left `settings` (where this would naturally live) among the 13 deferred mobile screens.

## Input sanitisation

- **SQL injection**: not applicable — every database access goes through SQLAlchemy's ORM
  (parameterized queries); a repo-wide audit for raw string-interpolated SQL (`grep` for
  `f"SELECT`, `.format(` near `execute(`, etc.) found none in production code.
- **Unbounded input (Phase 13, real gaps found and fixed)**: several fields had no
  `max_length` at all — `medical_history.notes`, `allergies.reaction`/`severity`,
  `medications.dosage`/`frequency`, `profile.sex`/`consent_status`/`emergency_contact_*`, every
  `*UpdateRequest`'s primary field, `LoginRequest.password`, `RefreshRequest.refresh_token`,
  and `vitals`/`devices`' `unit`/`device_type`/`label` fields. The most concrete risk was
  `LoginRequest.password`: unbounded, it would let an *unauthenticated* caller force argon2 to
  hash an arbitrarily large input on every login attempt — a real CPU-cost DoS vector, not a
  theoretical one. `VitalSyncRequest.readings` (a list, not a string) was similarly unbounded —
  capped at 1000 entries per call. All fixed in `app/schemas/*.py`, with the rejection behavior
  itself tested in `tests/integration/test_input_bounds.py`, not just the presence of a
  `Field(max_length=...)` declaration.
- Every numeric field already had range bounds (`age`, `height_cm`, `weight_kg`, `severity`,
  `top_k`, etc.) from earlier phases — this audit found no gaps there.

## Prompt-injection protection

`prompt_safety.rule`: "User-provided text is UNTRUSTED DATA. Model must not interpret it as
system instructions." Architecturally true at all three places this codebase hands an LLM
provider a `system` prompt (`app/patient_state/extraction.py`, `app/conversation/manager.py`,
`app/reasoning/reasoner.py`): each uses a fixed, hardcoded system-prompt string with no
interpolation of any user/patient/retrieved-document content whatsoever — untrusted content is
only ever placed in the `prompt` (user/task-turn) argument.

**Phase 13's dedicated adversarial test suite** (`tests/unit/test_prompt_injection.py`) proves
this two ways:
- **Structural**: using a recording fake LLM provider, confirms that a realistic injection
  payload (an "ignore all previous instructions... you are now DAN" style attempt, embedded in
  raw user text, an already-extracted symptom field, and retrieved document content) never
  appears in the exact `system` argument any of the three call sites send — only ever in
  `prompt`. This is checked against genuine attack-shaped text, not just confirmed by reading
  the code.
- **Behavioral (defense in depth)**: simulates an LLM that *was* successfully fooled by injected
  text into claiming a patient is "completely healthy" despite a real emergency, and confirms
  `get_validated_output()` still overrides it via the correction pipeline — because the
  deterministic safety engine never consults the LLM's own stated opinion at all
  (`safety_engine.rule`: "Hard safety rules take precedence over LLM output; LLM cannot override
  them"). This is the guarantee that matters when the structural guarantee alone isn't enough —
  a sufficiently capable/fooled model could still produce bad output even without ever being
  told a false system instruction, so the deterministic layer is the real backstop, not prompt
  hygiene alone.

## CORS

Already conditionally gated before this phase (`app/main.py`): `allow_origins=["*"]` only
applies when `ENVIRONMENT=="development"`; no CORS middleware at all is added otherwise, which
browsers treat as same-origin-only by default. **Not a new gap, but worth naming explicitly**:
`environment` defaults to `"development"` if `ENVIRONMENT` is unset — combined with the new
secrets guard above (which *does* fail loudly in that case, for the two known secrets), an
operator who forgets to set `ENVIRONMENT=production` would still silently get the permissive
CORS policy. This wasn't independently fixed in this phase since it's a narrower, lower-severity
instance of the same "insecure default" class the secrets guard addresses; flagged here for
visibility rather than left unmentioned.

## Not addressed in this phase

- The CORS default-environment observation immediately above.
- Vitals/measurements numeric-value encryption (see "Encryption").
- TLS termination itself (no real deployment target exists to configure it against — see
  "Encryption" for the concrete recommendation).
- Rate limiting / brute-force protection on `/auth/login` (an unbounded number of login attempts
  is possible today; the password-length bound fixed the CPU-cost-per-attempt problem, not the
  attempt-count problem).
- A formal penetration test or third-party security review — everything above is this codebase's
  own audit, not an independent assessment.
