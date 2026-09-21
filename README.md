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
- `mobile/` — Flutter app (voice/text conversation UI) — see `mobile/README.md` for status.
- `docs/` — architecture, API, database, AI pipeline, safety, security, testing, deployment,
  and known-limitations documentation, written incrementally per phase.

## Status

Phase 8 (Output Validator) done, as an **internal capability only** — same reasoning as Phases
6/7 (no `/assessment` endpoint yet; that's a deliberate deferral, not an oversight). `app/
validation/` runs the 10 spec-defined checks, retries the reasoner once with correction
feedback on failure, and falls back to a safe response if that also fails or if anything goes
wrong internally. Verified live in an unusually convincing way: a real run hit both a
successfully-retried transient API error *and* a real rate limit mid-correction, and the
fail-closed path handled both correctly — including correctly rejecting one real LLM response
for contradicting the deterministic safety engine's escalation decision. Phases 5–7 (Medical
Knowledge/RAG, Conversation Manager, Safety Engine & Medication Safety, Clinical Reasoning) and
Phases 0–2 are also done. LLM provider is Gemini (`GEMINI_API_KEY` in `.env`), verified live;
note its free tier caps at 20 requests/day **per model id** — `GEMINI_MODEL` in `.env` lets you
switch to a fresh quota if you hit it. See `docs/KNOWN_LIMITATIONS.md` for the current,
up-to-date status and open decisions, `docs/AI_PIPELINE.md` for how the pieces fit together,
and `mobile/README.md` for mobile-specific gaps.

## Backend — local development

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install torch --index-url https://download.pytorch.org/whl/cpu  # CPU-only wheel first,
                               # otherwise sentence-transformers may pull a multi-GB CUDA build
pip install -e ".[dev]"
cp ../.env.example ../.env    # then edit values, incl. GEMINI_API_KEY if you want symptom
                               # extraction (POST /symptoms/extract) to actually work
docker compose -f ../docker-compose.yml up -d db
uvicorn app.main:app --reload
```

First use of `POST /evidence/ingest` or `/evidence` downloads the `BAAI/bge-large-en-v1.5`
embedding model (~1.3GB) from Hugging Face and caches it — expect the first call to take a while.

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
