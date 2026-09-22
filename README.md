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

The full text+voice output pipeline is now live: `POST /assessment` returns a validated
`Assessment`, and `POST /assessment/speech` returns spoken audio of that same, actually-validated
result — never raw LLM output, by construction (`ValidatedText`, `app/tts/schema.py`, can only be
minted by code that has already called `get_validated_output()`). This chains patient state,
vital ingestion (manual + Health Connect), evidence retrieval, clinical reasoning, the
deterministic safety engine, output validation, and TTS (Phases 3, 5, 6, 7, 8, 9, 10, 11) into
one gated pipeline. `POST /assessment` always returns `200` with a valid `Assessment` body,
falling back to a safe "insufficient information" response rather than an error whenever
anything fails a check; `POST /assessment/speech` returns `503 TTS_ERROR` on a synthesis
failure specifically, without ever affecting the text endpoint — TTS is optional, never the only
response channel. **Verified live**: real Health Connect data synced end-to-end on a real
Android emulator (Phase 10), and a real HTTP call to `/assessment/speech` that hit Gemini's real
rate limit, correctly failed closed to `SAFE_FALLBACK`, and returned a genuine ~376KB WAV file
from real offline (pyttsx3) synthesis (Phase 11). Known gaps: the endpoint doesn't yet
cross-check its own proposed medications against medication safety; Health Connect's
`DeviceAdapter` necessarily lives in the mobile app, not the backend (no cloud API exists for
it); Apple HealthKit and cloud health platforms (Fitbit, Withings) remain unimplemented; TTS has
no streaming synthesis and isn't wired into the automatic conversation-reply loop, only an
explicit "Get assessment" action; and worst-case `/assessment` latency can approach 2 minutes
when the LLM is repeatedly failing — callers should use a generous client timeout. Phases 0–11
(Foundation through TTS) are all done — see `docs/KNOWN_LIMITATIONS.md` for the up-to-date
phase-by-phase status.

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

Flutter app scaffolded in `mobile/`. See `mobile/README.md` for setup, status, and known gaps.
Android (via the SDK/emulator installed for Phase 10) and web (Chrome) are both verified
targets; iOS is not (no Xcode/macOS on this machine).

```bash
cd mobile
flutter pub get
flutter test
flutter run -d chrome    # or an Android emulator/device: flutter run -d <device-id>
```

## Documentation

See `docs/` for architecture, API, database, AI pipeline, safety, security, testing, deployment,
and known-limitations docs (filled in incrementally as each phase lands).
