"""Phase 14 (evaluation): the real-Gemini companion to test_evaluation_dataset.py. Not a pytest
test — deliberately not part of the automated suite, since it needs a real GEMINI_API_KEY and is
subject to Gemini's free-tier quota/latency, neither of which CI or a routine test run should
depend on (tests/conftest.py deliberately force-blanks GEMINI_API_KEY for exactly this reason).
Run manually against a running dev Postgres (`docker compose up -d`) with a real key in .env:

    ./.venv/Scripts/python.exe -m evaluation.live_generation_check

User-confirmed choice for this phase ("attempt real Gemini calls too") over a fakes-only run.

Unlike test_evaluation_dataset.py (which calls the deterministic pipeline pieces directly),
this script drives the real POST /messages endpoint end-to-end per evaluation.dataset.DATASET
case — the same code path a real user's phone hits — with no provider overrides, so
get_llm_provider() returns the real GeminiProvider and get_embedding_provider() the real
local sentence-transformers model. It writes real rows to the dev DB (settings.database_url),
under eval-<case_id>@example.com accounts, and does not roll anything back.

Cases whose dataset entry intentionally leaves required fields unanswered (ambiguous-001,
incomplete-001, insufficient_information-001 — see their expected_information_requirements)
correctly get a follow-up question back, not a generated assessment; this script records that
as "awaited_more_info", not a failure, since it is the system behaving as specified
(conversation_manager: ask before RUN_ASSESSMENT). generation_metrics can only be computed over
cases that actually produced a generated Assessment.

A quota/network failure on one case doesn't stop the others. Results are printed and written to
evaluation/results.json for docs to reference, disclosing exactly which cases produced a real
model response, which were correctly deferred for more info, and which errored.
"""

import asyncio
import json
import time
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from app.main import app
from evaluation.dataset import DATASET, EvaluationCase


async def _setup_case(client: AsyncClient, case: EvaluationCase) -> dict[str, str]:
    resp = await client.post(
        "/auth/register", json={"email": f"eval-{case.case_id}@example.com", "password": "s3curePassw0rd"}
    )
    if resp.status_code != 201:
        # Account already exists from a prior run of this script — log in instead.
        resp = await client.post(
            "/auth/login", json={"email": f"eval-{case.case_id}@example.com", "password": "s3curePassw0rd"}
        )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    if case.patient_profile:
        await client.patch("/profile", headers=headers, json={**case.patient_profile, "consent_status": "granted"})
    for h in case.history:
        await client.post("/history", headers=headers, json=h)
    for a in case.allergies:
        await client.post("/allergies", headers=headers, json=a)
    for m in case.medications:
        await client.post("/medications", headers=headers, json=m)
    for vital_type, value in case.vitals.items():
        unit = {
            "heart_rate": "bpm", "oxygen_saturation": "%", "blood_pressure_systolic": "mmHg",
            "blood_pressure_diastolic": "mmHg", "body_temperature": "F",
        }[vital_type]
        await client.post("/vitals", headers=headers, json={"type": vital_type, "value": value, "unit": unit})
    # Symptoms have no CRUD endpoint (only LLM-based /symptoms/extract) — the real system would
    # normally learn these from the conversation turn itself, so the first message below states
    # the symptom in the same sentence a real user would, rather than seeding it out of band.

    return headers


def _symptom_sentence(case: EvaluationCase) -> str:
    if not case.symptoms:
        return "I don't have any specific symptoms right now, just checking in."
    s = case.symptoms[0]
    parts = [f"I have {s['symptom']}"]
    if s.get("duration"):
        parts.append(f"for {s['duration']}")
    if s.get("severity") is not None:
        parts.append(f"severity about {s['severity']} out of 10")
    return ", ".join(parts) + "."


async def run() -> list[dict]:
    transport = ASGITransport(app=app)
    results: list[dict] = []

    async with AsyncClient(transport=transport, base_url="http://live-eval") as client:
        for case in DATASET:
            start = time.monotonic()
            try:
                headers = await _setup_case(client, case)
                conversation_id = (await client.post("/conversations", headers=headers)).json()["id"]

                turn = await client.post(
                    "/messages", headers=headers,
                    json={"conversation_id": conversation_id, "content": _symptom_sentence(case)},
                )
                turn.raise_for_status()
                body = turn.json()

                # Answer up to 5 follow-up turns generically if the manager still has gaps this
                # dataset case's own fields didn't cover, so a case can still reach generation
                # even if _setup_case's structured fields don't map to every possible gap. A
                # generic reply never resolves a structured-data gap (e.g. current_medications),
                # so if the manager asks the identical question twice in a row it never will —
                # bail immediately rather than burning the rest of the day's Gemini quota
                # re-asking an unanswerable question (see docs/KNOWN_LIMITATIONS.md — found via
                # exactly this happening on a real run).
                attempts = 0
                last_question = body["assistant_message"]["content"]
                while not body["is_assessment"] and attempts < 5:
                    turn = await client.post(
                        "/messages", headers=headers,
                        json={"conversation_id": conversation_id, "content": "I don't have anything else to add."},
                    )
                    turn.raise_for_status()
                    body = turn.json()
                    attempts += 1
                    if not body["is_assessment"]:
                        question = body["assistant_message"]["content"]
                        if question == last_question:
                            break
                        last_question = question

                latency = time.monotonic() - start
                if not body["is_assessment"]:
                    results.append({
                        "case_id": case.case_id, "status": "awaited_more_info",
                        "last_question": body["assistant_message"]["content"],
                        "latency_seconds": round(latency, 2),
                    })
                    continue

                results.append({
                    "case_id": case.case_id,
                    "status": "generated",
                    "assessment_status": body["assessment_status"],
                    "escalation": body.get("escalation"),
                    "summary": body["assistant_message"]["content"],
                    "latency_seconds": round(latency, 2),
                })
            except Exception as exc:
                results.append({
                    "case_id": case.case_id, "status": "error", "error": f"{type(exc).__name__}: {exc}",
                    "latency_seconds": round(time.monotonic() - start, 2),
                })

    return results


def _summarize(results: list[dict]) -> dict:
    generated = [r for r in results if r["status"] == "generated"]
    # SAFE_FALLBACK's own fixed summary text (app/validation/validator.py) — a generated case
    # that matches it exactly means correction failed and validator.py fell back, which counts
    # against schema_compliance the same way an outright validation failure would.
    fallback_summary = "Insufficient information to provide a reliable assessment."
    non_fallback = [r for r in generated if r["summary"] != fallback_summary]
    return {
        "cases_total": len(results),
        "cases_generated": len(generated),
        "cases_awaited_more_info": len([r for r in results if r["status"] == "awaited_more_info"]),
        "cases_errored": len([r for r in results if r["status"] == "error"]),
        "schema_compliance_rate": len(non_fallback) / len(generated) if generated else None,
        "note": (
            "Every generated case reached POST /messages's is_assessment=true, meaning it "
            "already passed app.validation.validator.get_validated_output — a case here is "
            "only NOT schema-compliant if correction failed and it fell back to SAFE_FALLBACK. "
            "evidence_grounded_response_rate / unsupported_claim_rate are enforced structurally "
            "by the same validator (check_unsupported_claims) before release, not separately "
            "re-measured here."
        ),
    }


if __name__ == "__main__":
    results = asyncio.run(run())
    summary = _summarize(results)
    output = {"summary": summary, "results": results}
    print(json.dumps(output, indent=2))
    out_path = Path(__file__).parent / "results.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nWritten to {out_path}")
