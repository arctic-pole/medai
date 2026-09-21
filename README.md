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

`POST /assessment` is now live — the first endpoint in the codebase allowed to return
clinical-shaped output, chaining patient state, evidence retrieval, clinical reasoning, the
deterministic safety engine, and the output validator (Phases 3, 5, 6, 7, 8) into one gated
pipeline. It always returns `200` with a valid `Assessment` body, falling back to a safe
"insufficient information" response rather than an error whenever anything fails a check or
goes wrong internally — **verified live**, including two clean real successes and one correct
fail-closed resolution under a real rate limit. Known gaps: vitals are always empty (Phase 9
doesn't exist yet); the endpoint doesn't yet cross-check its own proposed medications against
medication safety (no reliable way yet to extract a drug name from free text); and worst-case
latency can approach 2 minutes when the LLM is repeatedly failing (each of up to 4 real calls
in the retry/correction path can take up to its own 30s timeout) — a real request-timeout bug
(no bound at all) was found and fixed here, but callers should still use a generous client
timeout. Phases 0–8 (Foundation through Output Validator) are all done — see
`docs/KNOWN_LIMITATIONS.md` for the up-to-date phase-by-phase status.

LLM provider is Gemini (`GEMINI_API_KEY` in `.env`), verified live across most phases. Its free
tier is rate-limited in a way that's turned out less predictable than first assumed: four model
ids have now hit `429`s or turned out deprecated in one day of testing (`gemini-3.8-flash`,
`gemini-3.6-flash`, `gemini-3.7-flash`, and `gemini-2.5-flash`) — switching `GEMINI_MODEL` is
**not** a reliable way to get a fresh quota, despite what an earlier version of this doc said;
a paid tier or waiting for the daily reset is the real fix. See `docs/AI_PIPELINE.md` for how
the pieces fit together and
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
