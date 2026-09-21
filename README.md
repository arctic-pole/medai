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

Phase 5 (Medical Knowledge / RAG) done: `POST /evidence/ingest` pulls real content from
MedlinePlus, chunks and embeds it (self-hosted `BAAI/bge-large-en-v1.5`), and stores it in
Postgres/pgvector; `GET /evidence?query=` retrieves it back, ranked and traceable to its source
— verified live with real data (see `docs/AI_PIPELINE.md`). Phase 4 (Conversation Manager) also
done: `POST /messages` conducts a structured interview, working with or without an LLM
configured. Phase 3 (`POST /symptoms/extract`) still needs a real `GEMINI_API_KEY` to do
anything beyond fail closed (LLM provider is Gemini — see `docs/KNOWN_LIMITATIONS.md`).
Phases 0–2 (Foundation, Patient Data, Conversation) are also done.
See `docs/KNOWN_LIMITATIONS.md` for the current, up-to-date status and open decisions, and
`mobile/README.md` for mobile-specific gaps.

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
