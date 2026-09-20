# MEDAI

**Multimodal AI Health Assessment & Clinical Decision Support System** — a clinical decision
support *prototype*.

MEDAI is **not**: an autonomous doctor, a prescription service, a diagnostic system, or an
emergency service. It never represents itself as a licensed doctor, and never claims its output
is a medical diagnosis or a prescription. See `medai_spec.yaml` (`meta`, `system_disclaimers`)
for the full, authoritative statement of scope.

## What this repo contains

- `medai_spec.yaml` — the authoritative project specification. Every implementation decision
  must map back to a requirement in this file.
- `IMPLEMENTATION_PLAN.md` — an audit of the spec plus a phase-by-phase build plan expanding
  the spec's own `phases:` block into concrete tasks, tech choices, and exit criteria.
- `backend/` — Python 3.12 + FastAPI service.
- `mobile/` — Flutter app (not yet scaffolded — see `mobile/README.md` for the current blocker).
- `docs/` — architecture, API, database, AI pipeline, safety, security, testing, deployment,
  and known-limitations documentation, written incrementally per phase.

## Status

Phase 2 (Conversation) done: users can speak (or type) to the mobile app and get a text
response, round-tripping through real `/conversations` and `/messages` APIs — no medical
reasoning yet, by design (`phases.2_conversation.constraint`). Phase 1 (Patient Data) and
Phase 0 (Foundation) are also done. See `docs/KNOWN_LIMITATIONS.md` for the current, up-to-date
status and open decisions, and `mobile/README.md` for mobile-specific gaps.

## Backend — local development

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
cp ../.env.example ../.env    # then edit values
docker compose -f ../docker-compose.yml up -d db
uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/healthz` → `{"status": "ok"}`

Run tests (integration tests need a `medai_test` database on the same Postgres server —
`CREATE DATABASE medai_test;`, created automatically in CI):

```bash
pytest
```

## Mobile — local development

Flutter app scaffolded in `mobile/`. See `mobile/README.md` for setup, status, and known gaps
(no Android SDK / Xcode on this machine — web is the only verified target so far).

```bash
cd mobile
flutter pub get
flutter test
flutter run -d chrome
```

## Documentation

See `docs/` for architecture, API, database, AI pipeline, safety, security, testing, deployment,
and known-limitations docs (filled in incrementally as each phase lands).
