import pytest
from httpx import AsyncClient

from app.db.models import Symptom
from app.main import app
from app.providers.llm import get_llm_provider
from app.providers.tts import get_tts_provider
from app.reasoning.schema import Assessment
from tests.fakes import FailingTTSProvider, FakeReasoningLLMProvider, FakeTTSProvider, NotConfiguredLLMProvider

pytestmark = pytest.mark.asyncio


async def _authed_headers(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post("/auth/register", json={"email": email, "password": "s3curePassw0rd"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _conversation_with_symptom(client: AsyncClient, headers: dict[str, str], db_session) -> str:
    conversation_id = (await client.post("/conversations", headers=headers)).json()["id"]
    await client.post(
        "/messages", headers=headers, json={"conversation_id": conversation_id, "content": "I have a headache"}
    )

    patient_resp = await client.get("/patient", headers=headers)
    patient_id = patient_resp.json()["id"]
    db_session.add(Symptom(patient_id=patient_id, symptom="headache", severity=6, certainty="user_reported"))
    await db_session.commit()

    return conversation_id


async def test_assessment_speech_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/assessment/speech", json={"conversation_id": "00000000-0000-0000-0000-000000000000"})
    assert resp.status_code in (401, 403)


async def test_assessment_speech_404_for_unowned_conversation(client: AsyncClient) -> None:
    headers_a = await _authed_headers(client, "speechA@example.com")
    headers_b = await _authed_headers(client, "speechB@example.com")
    conversation_id = (await client.post("/conversations", headers=headers_a)).json()["id"]

    resp = await client.post("/assessment/speech", headers=headers_b, json={"conversation_id": conversation_id})
    assert resp.status_code == 404


async def test_assessment_speech_returns_audio_for_a_validated_assessment(client: AsyncClient, db_session) -> None:
    headers = await _authed_headers(client, "speechC@example.com")
    conversation_id = await _conversation_with_symptom(client, headers, db_session)

    good_assessment = Assessment(
        status="caution", summary="Possible explanations include a tension headache.", confidence="low"
    )
    fake_tts = FakeTTSProvider()
    app.dependency_overrides[get_llm_provider] = lambda: FakeReasoningLLMProvider([good_assessment])
    app.dependency_overrides[get_tts_provider] = lambda: fake_tts
    try:
        resp = await client.post("/assessment/speech", headers=headers, json={"conversation_id": conversation_id})
    finally:
        del app.dependency_overrides[get_llm_provider]
        del app.dependency_overrides[get_tts_provider]

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert resp.content == f"FAKE_AUDIO:{good_assessment.summary}".encode()
    assert fake_tts.synthesized_texts == [good_assessment.summary]


async def test_assessment_speech_502s_when_tts_engine_fails(client: AsyncClient, db_session) -> None:
    """Requirement: graceful handling of TTS failure, and text remains available when TTS
    fails. This endpoint fails closed with 503 TTS_ERROR rather than silent/fake audio — and a
    parallel call to POST /assessment (text) for the same conversation still succeeds,
    demonstrating TTS is never the only response channel."""

    headers = await _authed_headers(client, "speechD@example.com")
    conversation_id = await _conversation_with_symptom(client, headers, db_session)

    good_assessment = Assessment(
        status="caution", summary="Possible explanations include a tension headache.", confidence="low"
    )

    app.dependency_overrides[get_llm_provider] = lambda: FakeReasoningLLMProvider([good_assessment])
    app.dependency_overrides[get_tts_provider] = lambda: FailingTTSProvider()
    try:
        speech_resp = await client.post("/assessment/speech", headers=headers, json={"conversation_id": conversation_id})
        assert speech_resp.status_code == 503
        assert "TTS_ERROR" in speech_resp.json()["detail"]

        # Independently, the text endpoint (same conversation, fresh fake LLM instance since
        # FakeReasoningLLMProvider's canned queue is consumed per-call) still works.
        app.dependency_overrides[get_llm_provider] = lambda: FakeReasoningLLMProvider([good_assessment])
        text_resp = await client.post("/assessment", headers=headers, json={"conversation_id": conversation_id})
        assert text_resp.status_code == 200
        assert text_resp.json()["summary"] == good_assessment.summary
    finally:
        del app.dependency_overrides[get_llm_provider]
        del app.dependency_overrides[get_tts_provider]


async def test_assessment_speech_falls_back_to_safe_text_when_llm_not_configured(client: AsyncClient, db_session) -> None:
    """When get_validated_output() itself fails closed to SAFE_FALLBACK (no LLM configured),
    that fallback text — not an error — is what gets spoken."""

    headers = await _authed_headers(client, "speechE@example.com")
    conversation_id = await _conversation_with_symptom(client, headers, db_session)
    fake_tts = FakeTTSProvider()

    app.dependency_overrides[get_llm_provider] = lambda: NotConfiguredLLMProvider()
    app.dependency_overrides[get_tts_provider] = lambda: fake_tts
    try:
        resp = await client.post("/assessment/speech", headers=headers, json={"conversation_id": conversation_id})
    finally:
        del app.dependency_overrides[get_llm_provider]
        del app.dependency_overrides[get_tts_provider]

    assert resp.status_code == 200
    assert fake_tts.synthesized_texts == ["Insufficient information to provide a reliable assessment."]
