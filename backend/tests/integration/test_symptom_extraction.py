import pytest
from httpx import AsyncClient

from app.main import app
from app.patient_state.assembler import build_patient_state
from app.providers.llm import get_llm_provider
from tests.fakes import FakeLLMProvider, NotConfiguredLLMProvider

pytestmark = pytest.mark.asyncio


async def _authed_headers(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post("/auth/register", json={"email": email, "password": "s3curePassw0rd"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _conversation_with_message(client: AsyncClient, headers: dict[str, str], text: str) -> str:
    conversation_id = (await client.post("/conversations", headers=headers)).json()["id"]
    await client.post("/messages", headers=headers, json={"conversation_id": conversation_id, "content": text})
    return conversation_id


async def test_extract_fails_closed_when_llm_not_configured(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "noconfig@example.com")
    conversation_id = await _conversation_with_message(client, headers, "I have a headache")

    app.dependency_overrides[get_llm_provider] = lambda: NotConfiguredLLMProvider()
    try:
        resp = await client.post("/symptoms/extract", headers=headers, json={"conversation_id": conversation_id})
    finally:
        del app.dependency_overrides[get_llm_provider]

    assert resp.status_code == 503
    assert "LLM_ERROR" in resp.json()["detail"]


async def test_extract_with_fake_provider_stores_and_lists_symptoms(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "extract@example.com")
    conversation_id = await _conversation_with_message(client, headers, "My head has been pounding since noon")

    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()
    try:
        resp = await client.post("/symptoms/extract", headers=headers, json={"conversation_id": conversation_id})
    finally:
        del app.dependency_overrides[get_llm_provider]

    assert resp.status_code == 201
    body = resp.json()
    assert len(body) == 1
    assert body[0]["symptom"] == "headache"
    assert body[0]["conversation_id"] == conversation_id

    list_resp = await client.get("/symptoms", headers=headers, params={"conversation_id": conversation_id})
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


async def test_extract_rejects_conversation_with_no_user_messages(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "empty@example.com")
    conversation_id = (await client.post("/conversations", headers=headers)).json()["id"]

    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()
    try:
        resp = await client.post("/symptoms/extract", headers=headers, json={"conversation_id": conversation_id})
    finally:
        del app.dependency_overrides[get_llm_provider]

    assert resp.status_code == 400


async def test_cannot_extract_for_another_patients_conversation(client: AsyncClient) -> None:
    headers_a = await _authed_headers(client, "symA@example.com")
    headers_b = await _authed_headers(client, "symB@example.com")
    conversation_id = await _conversation_with_message(client, headers_a, "I feel dizzy")

    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()
    try:
        resp = await client.post("/symptoms/extract", headers=headers_b, json={"conversation_id": conversation_id})
    finally:
        del app.dependency_overrides[get_llm_provider]

    assert resp.status_code == 404


async def test_patient_state_assembler_includes_extracted_symptoms_and_unknowns(
    client: AsyncClient, db_session
) -> None:
    from sqlalchemy import select

    from app.db.models import Patient, User

    headers = await _authed_headers(client, "assemble@example.com")
    conversation_id = await _conversation_with_message(client, headers, "My head has been pounding since noon")

    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()
    try:
        await client.post("/symptoms/extract", headers=headers, json={"conversation_id": conversation_id})
    finally:
        del app.dependency_overrides[get_llm_provider]

    user = (await db_session.execute(select(User).where(User.email == "assemble@example.com"))).scalar_one()
    patient = (await db_session.execute(select(Patient).where(Patient.user_id == user.id))).scalar_one()

    state = await build_patient_state(db_session, patient)

    assert len(state.symptoms) == 1
    assert state.symptoms[0].symptom == "headache"
    # nothing filled in on the profile yet -> must show up as unknown, never guessed
    assert "age" in state.unknowns
    assert "sex" in state.unknowns
    assert state.data_quality["profile_completeness"] < 1.0
