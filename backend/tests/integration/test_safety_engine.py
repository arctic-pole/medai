import pytest
from sqlalchemy import select

from app.db.models import Patient, SafetyEvent, User
from app.safety.engine import evaluate_safety
from app.safety.schema import MedicationCheckResult

pytestmark = pytest.mark.asyncio


async def _make_patient(db_session, email: str) -> Patient:
    user = User(email=email, hashed_password="not-a-real-hash")
    db_session.add(user)
    await db_session.flush()
    patient = Patient(user_id=user.id)
    db_session.add(patient)
    await db_session.flush()
    await db_session.commit()
    return patient


async def test_normal_vitals_and_no_medication_findings_pass_and_log_nothing(db_session) -> None:
    patient = await _make_patient(db_session, "safeA@example.com")

    evaluation = await evaluate_safety(db_session, patient_id=patient.id, vitals={"heart_rate": 72, "spo2": 98})

    assert evaluation.decision == "PASS"
    events = (await db_session.execute(select(SafetyEvent).where(SafetyEvent.patient_id == patient.id))).scalars().all()
    assert events == []


async def test_low_spo2_escalates_and_is_logged(db_session) -> None:
    patient = await _make_patient(db_session, "safeB@example.com")

    evaluation = await evaluate_safety(db_session, patient_id=patient.id, vitals={"spo2": 85})

    assert evaluation.decision == "ESCALATE"
    events = (await db_session.execute(select(SafetyEvent).where(SafetyEvent.patient_id == patient.id))).scalars().all()
    assert len(events) == 1
    assert events[0].decision == "ESCALATE"
    assert events[0].rule_id == "VITAL_SPO2_EMERGENCY_001"


async def test_blocked_medication_takes_precedence_over_modify_but_not_escalate(db_session) -> None:
    patient = await _make_patient(db_session, "safeC@example.com")
    blocked = [MedicationCheckResult(candidate_name="x", decision="BLOCKED", reasons=["allergy"])]

    # no vital escalation -> BLOCK wins
    evaluation = await evaluate_safety(db_session, patient_id=patient.id, vitals={}, medication_findings=blocked)
    assert evaluation.decision == "BLOCK"

    # vital escalation present -> ESCALATE still wins over a blocked medication
    evaluation2 = await evaluate_safety(
        db_session, patient_id=patient.id, vitals={"spo2": 85}, medication_findings=blocked
    )
    assert evaluation2.decision == "ESCALATE"


async def test_requires_review_medication_yields_modify(db_session) -> None:
    patient = await _make_patient(db_session, "safeD@example.com")
    review = [MedicationCheckResult(candidate_name="x", decision="REQUIRES_REVIEW", reasons=["interaction"])]

    evaluation = await evaluate_safety(db_session, patient_id=patient.id, vitals={}, medication_findings=review)

    assert evaluation.decision == "MODIFY"
    events = (await db_session.execute(select(SafetyEvent).where(SafetyEvent.patient_id == patient.id))).scalars().all()
    assert len(events) == 1
    assert events[0].decision == "MODIFY"
    assert events[0].rule_id == "MEDICATION_SAFETY:x"


async def test_allowed_medication_not_logged(db_session) -> None:
    patient = await _make_patient(db_session, "safeE@example.com")
    allowed = [MedicationCheckResult(candidate_name="x", decision="ALLOWED")]

    evaluation = await evaluate_safety(db_session, patient_id=patient.id, vitals={}, medication_findings=allowed)

    assert evaluation.decision == "PASS"
    events = (await db_session.execute(select(SafetyEvent).where(SafetyEvent.patient_id == patient.id))).scalars().all()
    assert events == []
