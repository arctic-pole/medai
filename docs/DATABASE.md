# MEDAI — Database

PostgreSQL only (+ pgvector extension for embeddings, added in Phase 5). Access via SQLAlchemy
2.x async ORM; schema changes via Alembic migrations in `backend/alembic/versions/`.

## Phase 1 tables

| Table | Purpose | Notes |
|---|---|---|
| `users` | Auth identity (email + hashed password) | UUID PK, unique email |
| `patients` | One patient record per user | 1:1 with `users` in this prototype (personal health assistant, not multi-patient) |
| `patient_profiles` | Scalar demographic + consent fields from `patient_profile.required_fields` | PK = `patient_id`; `emergency_contact_*` encrypted at rest |
| `medical_history` | Known conditions + relevant history | `condition`/`notes` encrypted at rest |
| `allergies` | Allergy records | `substance`/`reaction` encrypted at rest |
| `current_medications` | Current medication records | `name`/`dosage`/`frequency` encrypted at rest |
| `consents` | Append-only consent event log | **Not** an explicit table in `medai_spec.yaml database.tables` — added to satisfy `security.consent_record_fields` (user, consent_type, timestamp, version, status), which names required fields but no table. Flagged in `IMPLEMENTATION_PLAN.md`. |
| `audit_logs` | One row per HTTP request | Only `security.logging.allowed` fields are ever written (see `app/audit/middleware.py`) |
| `conversations` | Phase 2: one row per conversation | Belongs to a patient |
| `messages` | Phase 2: one row per turn (`role` = user/assistant) | `content` encrypted at rest, same as Phase 1's sensitive columns |
| `symptoms` | Phase 3: one row per LLM-extracted symptom | `symptom_extraction.fields`; free-text fields encrypted at rest; linked to the source `conversation_id` |

The canonical `patient_state.schema` (patient + symptoms + medical_history + allergies +
medications + vitals + unknowns + data_quality, etc.) is **not** stored as a single blob — it's
assembled on demand by `app/patient_state/assembler.py` from the tables above (`vitals` stays
`{}` until Phase 9; `recent_events`/`risk_factors` stay `[]` until Phase 4/6, since computing them
is clinical inference out of scope for this assembly step).

`known_conditions`, `allergies`, `current_medications`, and `relevant_history` from
`patient_profile.required_fields` are assembled into the logical "profile" at the API layer from
`patient_profiles` + the three related tables above, rather than stored as JSON blobs on one row
— matching `database.tables` listing them as separate tables.

## Encryption at rest

Per `security.minimum_requirements: encrypted_sensitive_data`, genuinely sensitive free-text
columns (allergy substances/reactions, medication names/dosages, medical history conditions/
notes, emergency contact info) use `app/db/encrypted_types.EncryptedString` — a SQLAlchemy
`TypeDecorator` that transparently encrypts with Fernet (symmetric, `FIELD_ENCRYPTION_KEY` env
var) on write and decrypts on read. This is an **application-level** control, independent of and
complementary to TLS in transit and any infra-level disk encryption decided in Phase 13.

**Known Alembic caveat:** `alembic revision --autogenerate` does not add the
`import app.db.encrypted_types` line for columns using this custom type — add it by hand to each
generated migration that touches an encrypted column (see the Phase 1 migration for an example).

## Local development

```bash
docker compose up -d db                    # starts Postgres (pgvector/pgvector:pg16)
cd backend
alembic upgrade head                       # applies all migrations
```

A second database, `medai_test`, is used for integration tests (`backend/tests/conftest.py`) so
test runs never touch dev data. Create it once locally with:

```sql
CREATE DATABASE medai_test;
```

CI creates it automatically via the Postgres service container's `POSTGRES_DB` setting.
