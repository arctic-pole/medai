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

The conversation itself is the complete interface: `POST /messages` asks follow-up questions
until nothing more is missing, then automatically runs the full clinical pipeline (patient state
→ vital ingestion, manual or Health Connect → evidence retrieval → clinical reasoning → the
deterministic safety engine → output validation) and returns a validated `Assessment`'s summary
as the reply — never raw LLM output, by construction. Optional spoken audio for that same,
actually-validated result is available via `POST /assessment/speech`; a high-risk result
triggers a required confirmation prompt on mobile; session persistence resumes the most recent
conversation on launch. As of Phase 13 (security hardening), the backend has also been audited
end to end: a real vulnerability was found and fixed (both the JWT-signing key and the
field-encryption key shipped with public placeholder defaults that nothing stopped a real
deployment from silently using — the app now refuses to start with either one outside
`environment=="development"`), automated secret-scanning runs in CI, roughly a dozen
previously-unbounded input fields were bounded (including an unauthenticated login-password
DoS vector), a dedicated prompt-injection adversarial test suite was added, and
`GET /privacy/export` / `DELETE /privacy/me` were built and verified live against real data.
**Verified live**: the automatic assessment pipeline (0.3s, register → fill profile/history/
allergies/medications → message); real Health Connect data synced end-to-end on a real Android
emulator (Phase 10); a real `/assessment/speech` call returning genuine WAV audio (Phase 11); the
new secrets guard refusing an insecure production startup and accepting a secure one; and the
full privacy export/delete flow (including confirming a deleted account's access token
immediately stops working). Known gaps: medication proposals aren't cross-checked against
medication safety; 13 of 15 `ux.screens` remain unbuilt on mobile (their backend APIs already
exist); only 1 of 5 confirmation-prompt triggers has real signal to act on; numeric vital values
aren't encrypted at rest (unlike every other sensitive column); no rate limiting on login
attempts; no real deployment target exists to configure TLS against. Phases 0–13 (Foundation
through Security Hardening) are all done — see `docs/KNOWN_LIMITATIONS.md` and
`docs/SECURITY.md` for the up-to-date, full-detail status.

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
