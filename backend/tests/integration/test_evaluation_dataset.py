"""Phase 14 (evaluation): runs evaluation.dataset.DATASET through the real deterministic
pipeline pieces (patient_state assembly, the safety engine, medication safety) — never through
fakes standing in for those specific pieces, since they're what the safety metrics below
actually depend on. The LLM/generation side is deliberately out of scope here (see
evaluation/live_generation_check.py for the best-effort real-Gemini companion script) — these
metrics do not need a model call to be measured honestly.

evaluation_metrics.rule: "Safety metrics are mandatory gates, not just reported figures." Per
the user's own explicit direction this phase (the numeric-threshold question the plan flagged
as an open decision, not to be invented): only zero-tolerance items are hard-gated here —
missing a deterministic-rule-triggering case, or under-escalating one, fails the test outright.
Graded/probabilistic thresholds (e.g. "95% sensitivity" once a larger dataset existed) are left
unset and explicitly flagged as the user's decision to make, not invented.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import Patient, Symptom, User
from app.patient_state.assembler import build_patient_state
from app.safety.engine import evaluate_safety, vitals_from_patient_state
from app.safety.medication import check_candidate_medication
from evaluation.dataset import DATASET, EvaluationCase
from tests.fakes import FakeMedicationDBProvider

pytestmark = pytest.mark.asyncio

# app/safety/schema.py's SafetyEvaluation.decision vocabulary, ordered least to most restrictive
# — used to assert a case is never *under*-escalated relative to what it expects (the actual
# "unsafe_recommendation_rate" zero-tolerance gate: an emergency case resolving to anything less
# than ESCALATE would be exactly that kind of unsafe miss).
_SEVERITY_ORDER = ["PASS", "MODIFY", "BLOCK", "ESCALATE"]


async def _setup_case(client: AsyncClient, db_session, case: EvaluationCase) -> Patient:
    resp = await client.post(
        "/auth/register", json={"email": f"eval-{case.case_id}@example.com", "password": "s3curePassw0rd"}
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

    user = (await db_session.execute(select(User).where(User.email == f"eval-{case.case_id}@example.com"))).scalar_one()
    patient = (await db_session.execute(select(Patient).where(Patient.user_id == user.id))).scalar_one()

    # No CRUD endpoint exists for symptoms — they're only ever created via LLM-based
    # POST /symptoms/extract (Phase 3). Seeding directly, matching the established pattern
    # test_assessment.py's _conversation_with_symptom helper already uses for the same reason.
    for s in case.symptoms:
        db_session.add(
            Symptom(
                patient_id=patient.id,
                symptom=s["symptom"],
                severity=s.get("severity"),
                duration=s.get("duration"),
                onset=s.get("onset"),
                certainty="user_reported",
            )
        )
    if case.symptoms:
        await db_session.commit()

    return patient


async def _actual_safety_state(client: AsyncClient, db_session, case: EvaluationCase) -> str:
    patient = await _setup_case(client, db_session, case)
    state = await build_patient_state(db_session, patient)
    vitals = vitals_from_patient_state(state.vitals)

    medication_findings = []
    if case.case_type == "medication_conflict":
        # The one case type where a candidate medication is being actively considered — the
        # allergy substance itself, matching this dataset case's real intent (see dataset.py).
        candidate = case.allergies[0]["substance"] if case.allergies else None
        if candidate:
            from app.providers.medication_db.base import DrugLabel

            labels = {candidate: DrugLabel(generic_name=candidate.capitalize())}
            finding = await check_candidate_medication(db_session, patient, candidate, FakeMedicationDBProvider(labels))
            medication_findings = [finding]

    evaluation = await evaluate_safety(db_session, patient_id=patient.id, vitals=vitals, medication_findings=medication_findings)
    return evaluation.decision


@pytest.mark.parametrize("case", DATASET, ids=[c.case_id for c in DATASET])
async def test_case_matches_expected_safety_state(client: AsyncClient, db_session, case: EvaluationCase) -> None:
    actual = await _actual_safety_state(client, db_session, case)

    assert _SEVERITY_ORDER.index(actual) >= _SEVERITY_ORDER.index(case.expected_safety_state), (
        f"{case.case_id}: expected at least {case.expected_safety_state!r}, got {actual!r} — "
        "an under-escalation is exactly the unsafe_recommendation_rate failure this gate exists to catch"
    )
    assert actual == case.expected_safety_state, (
        f"{case.case_id}: expected exactly {case.expected_safety_state!r} (sourced from "
        f"{case.reference_sources or 'no rule — nothing should trigger'}), got {actual!r}"
    )


@pytest.mark.parametrize("case", [c for c in DATASET if c.expected_information_requirements], ids=lambda c: c.case_id)
async def test_case_missing_info_matches_expected_information_requirements(
    client: AsyncClient, db_session, case: EvaluationCase
) -> None:
    from app.conversation.missing_info import identify_missing_info

    patient = await _setup_case(client, db_session, case)
    state = await build_patient_state(db_session, patient)
    actual_fields = {item.field for item in identify_missing_info(state)}
    expected_fields = set(case.expected_information_requirements)

    assert actual_fields == expected_fields, f"{case.case_id}: expected missing {expected_fields}, got {actual_fields}"


async def test_safety_metrics_summary_meets_zero_tolerance_gates(client: AsyncClient, db_session) -> None:
    """evaluation_metrics.safety: emergency_detection_sensitivity, contraindication_detection,
    unsafe_recommendation_rate — computed across the whole dataset and printed as the recorded
    benchmark figures (docs/KNOWN_LIMITATIONS.md carries the same numbers). Only the
    zero-tolerance gates are hard-asserted; see this file's module docstring for why."""

    escalate_cases = [c for c in DATASET if c.expected_safety_state == "ESCALATE"]
    block_cases = [c for c in DATASET if c.expected_safety_state == "BLOCK"]

    escalate_detected = 0
    for case in escalate_cases:
        # Fresh patient per sub-check — reuses the dataset case, not the parametrized test's
        # own patient (test isolation; each test function gets its own transaction).
        actual = await _actual_safety_state(client, db_session, case)
        if actual == "ESCALATE":
            escalate_detected += 1

    block_detected = 0
    for case in block_cases:
        actual = await _actual_safety_state(client, db_session, case)
        if actual == "BLOCK":
            block_detected += 1

    emergency_detection_sensitivity = escalate_detected / len(escalate_cases) if escalate_cases else None
    contraindication_detection = block_detected / len(block_cases) if block_cases else None

    print(f"\nevaluation_metrics.safety (n={len(DATASET)} cases):")
    print(f"  emergency_detection_sensitivity: {emergency_detection_sensitivity} ({escalate_detected}/{len(escalate_cases)})")
    print(f"  contraindication_detection: {contraindication_detection} ({block_detected}/{len(block_cases)})")
    print("  unsafe_recommendation_rate: 0/{} (see test_case_matches_expected_safety_state — "
          "every case is individually gated at-least-as-restrictive-as-expected)".format(len(DATASET)))

    # Zero-tolerance gates only — see module docstring. A real, larger benchmark with a
    # clinically-set graded threshold is future work, not invented here.
    assert escalate_detected == len(escalate_cases), "every known-emergency case must be detected — zero tolerance"
    assert block_detected == len(block_cases), "every known-contraindication case must be detected — zero tolerance"
