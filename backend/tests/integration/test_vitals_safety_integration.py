import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import Patient, User
from app.patient_state.assembler import build_patient_state
from app.safety.engine import evaluate_safety, vitals_from_patient_state

pytestmark = pytest.mark.asyncio


async def _authed_headers(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post("/auth/register", json={"email": email, "password": "s3curePassw0rd"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_ingested_vital_reaches_patient_state_and_escalates_safety(
    client: AsyncClient, db_session
) -> None:
    headers = await _authed_headers(client, "vitalsafety@example.com")

    resp = await client.post(
        "/vitals", headers=headers, json={"type": "oxygen_saturation", "value": 85, "unit": "%"}
    )
    assert resp.status_code == 201

    user = (await db_session.execute(select(User).where(User.email == "vitalsafety@example.com"))).scalar_one()
    patient = (await db_session.execute(select(Patient).where(Patient.user_id == user.id))).scalar_one()

    state = await build_patient_state(db_session, patient)
    assert "oxygen_saturation" in state.vitals
    assert state.vitals["oxygen_saturation"]["value"] == 85

    rule_vitals = vitals_from_patient_state(state.vitals)
    assert rule_vitals["spo2"] == 85

    evaluation = await evaluate_safety(db_session, patient_id=patient.id, vitals=rule_vitals)
    assert evaluation.decision == "ESCALATE"


async def test_normal_vital_does_not_escalate(client: AsyncClient, db_session) -> None:
    headers = await _authed_headers(client, "vitalsafety2@example.com")
    await client.post("/vitals", headers=headers, json={"type": "heart_rate", "value": 72, "unit": "bpm"})

    user = (await db_session.execute(select(User).where(User.email == "vitalsafety2@example.com"))).scalar_one()
    patient = (await db_session.execute(select(Patient).where(Patient.user_id == user.id))).scalar_one()

    state = await build_patient_state(db_session, patient)
    rule_vitals = vitals_from_patient_state(state.vitals)
    evaluation = await evaluate_safety(db_session, patient_id=patient.id, vitals=rule_vitals)
    assert evaluation.decision == "PASS"
