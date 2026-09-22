import pytest
from httpx import AsyncClient

from app.main import app
from app.providers.embeddings import get_embedding_provider
from app.providers.llm import get_llm_provider
from tests.fakes import FakeEmbeddingProvider, FakeReasoningLLMProvider, NotConfiguredLLMProvider

pytestmark = pytest.mark.asyncio


async def _authed_headers(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post("/auth/register", json={"email": email, "password": "s3curePassw0rd"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_conversation_created_and_listed(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "conv1@example.com")

    create_resp = await client.post("/conversations", headers=headers)
    assert create_resp.status_code == 201
    conversation_id = create_resp.json()["id"]

    list_resp = await client.get("/conversations", headers=headers)
    assert list_resp.status_code == 200
    assert any(c["id"] == conversation_id for c in list_resp.json())


async def test_send_message_asks_highest_priority_missing_info_and_persists(client: AsyncClient) -> None:
    """Phase 4: with an empty profile/history/allergies/medications and no extracted symptoms
    yet, medication_allergy_safety (allergies) is the highest-priority non-empty tier — see
    app/conversation/missing_info.py. No LLM is configured in the test environment, so the
    deterministic fallback template is used (app/conversation/manager.py)."""

    headers = await _authed_headers(client, "conv2@example.com")
    conversation_id = (await client.post("/conversations", headers=headers)).json()["id"]

    resp = await client.post(
        "/messages",
        headers=headers,
        json={"conversation_id": conversation_id, "content": "I have had a headache since this morning"},
    )
    assert resp.status_code == 201
    body = resp.json()

    assert body["user_message"]["role"] == "user"
    assert body["user_message"]["content"] == "I have had a headache since this morning"
    assert body["assistant_message"]["role"] == "assistant"
    assert body["assistant_message"]["content"] == "Could you tell me about any known drug allergies?"

    list_resp = await client.get("/messages", headers=headers, params={"conversation_id": conversation_id})
    assert list_resp.status_code == 200
    roles = [m["role"] for m in list_resp.json()]
    assert roles == ["user", "assistant"]


async def test_send_message_runs_real_assessment_when_nothing_left_to_ask(client: AsyncClient) -> None:
    """Phase 12: a patient whose profile/history/allergies/medications are all filled in — and
    who has no outstanding incomplete symptoms — gets a real validated Assessment as the reply,
    not a placeholder. This is architecture.canonical_pipeline's remaining steps
    (EVIDENCE_RETRIEVAL through OUTPUT_VALIDATION) reached automatically from the conversation
    loop, the same pipeline POST /assessment runs."""

    headers = await _authed_headers(client, "conv4@example.com")
    await client.patch(
        "/profile",
        headers=headers,
        json={"age": 40, "sex": "female", "height_cm": 165, "weight_kg": 60, "consent_status": "granted"},
    )
    await client.post("/history", headers=headers, json={"condition": "asthma"})
    await client.post("/allergies", headers=headers, json={"substance": "penicillin"})
    await client.post("/medications", headers=headers, json={"name": "albuterol"})

    conversation_id = (await client.post("/conversations", headers=headers)).json()["id"]

    from app.reasoning.schema import Assessment

    good_assessment = Assessment(
        status="caution", summary="Possible explanations include a mild viral illness.", confidence="low"
    )
    app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbeddingProvider()
    app.dependency_overrides[get_llm_provider] = lambda: FakeReasoningLLMProvider([good_assessment])
    try:
        resp = await client.post(
            "/messages", headers=headers, json={"conversation_id": conversation_id, "content": "just checking in"}
        )
    finally:
        del app.dependency_overrides[get_embedding_provider]
        del app.dependency_overrides[get_llm_provider]

    assert resp.status_code == 201
    body = resp.json()
    assert body["assistant_message"]["content"] == good_assessment.summary
    assert body["is_assessment"] is True
    assert body["assessment_status"] == "caution"
    assert body["escalation"] is None


async def test_send_message_assessment_falls_back_to_safe_text_when_llm_not_configured(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "conv5@example.com")
    await client.patch(
        "/profile",
        headers=headers,
        json={"age": 40, "sex": "female", "height_cm": 165, "weight_kg": 60, "consent_status": "granted"},
    )
    await client.post("/history", headers=headers, json={"condition": "asthma"})
    await client.post("/allergies", headers=headers, json={"substance": "penicillin"})
    await client.post("/medications", headers=headers, json={"name": "albuterol"})

    conversation_id = (await client.post("/conversations", headers=headers)).json()["id"]

    app.dependency_overrides[get_llm_provider] = lambda: NotConfiguredLLMProvider()
    try:
        resp = await client.post(
            "/messages", headers=headers, json={"conversation_id": conversation_id, "content": "just checking in"}
        )
    finally:
        del app.dependency_overrides[get_llm_provider]

    assert resp.status_code == 201
    body = resp.json()
    assert body["is_assessment"] is True
    assert body["assistant_message"]["content"] == "Insufficient information to provide a reliable assessment."


async def test_send_message_assessment_surfaces_escalation_for_mobile_confirmation_prompt(
    client: AsyncClient,
) -> None:
    """The `escalation`/`assessment_status` fields on the exchange response are what the mobile
    app uses to show a confirmation prompt for a high-risk result
    (ux.confirmation_required_when: high_risk_recommendation_considered) — verified here at the
    API boundary, not just that the text happens to contain the right words."""

    headers = await _authed_headers(client, "conv6@example.com")
    await client.patch(
        "/profile",
        headers=headers,
        json={"age": 40, "sex": "female", "height_cm": 165, "weight_kg": 60, "consent_status": "granted"},
    )
    await client.post("/history", headers=headers, json={"condition": "asthma"})
    await client.post("/allergies", headers=headers, json={"substance": "penicillin"})
    await client.post("/medications", headers=headers, json={"name": "albuterol"})

    conversation_id = (await client.post("/conversations", headers=headers)).json()["id"]

    from app.reasoning.schema import Assessment

    emergency_assessment = Assessment(
        status="emergency",
        summary="This requires urgent attention.",
        confidence="low",
        escalation="Seek emergency care immediately.",
    )
    app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbeddingProvider()
    app.dependency_overrides[get_llm_provider] = lambda: FakeReasoningLLMProvider([emergency_assessment])
    try:
        resp = await client.post(
            "/messages", headers=headers, json={"conversation_id": conversation_id, "content": "just checking in"}
        )
    finally:
        del app.dependency_overrides[get_embedding_provider]
        del app.dependency_overrides[get_llm_provider]

    assert resp.status_code == 201
    body = resp.json()
    assert body["assessment_status"] == "emergency"
    assert body["escalation"] == "Seek emergency care immediately."
    assert "Seek emergency care immediately." in body["assistant_message"]["content"]


async def test_cannot_message_another_patients_conversation(client: AsyncClient) -> None:
    headers_a = await _authed_headers(client, "convA@example.com")
    headers_b = await _authed_headers(client, "convB@example.com")

    conversation_id = (await client.post("/conversations", headers=headers_a)).json()["id"]

    resp = await client.post(
        "/messages", headers=headers_b, json={"conversation_id": conversation_id, "content": "hello"}
    )
    assert resp.status_code == 404

    list_resp = await client.get("/messages", headers=headers_b, params={"conversation_id": conversation_id})
    assert list_resp.status_code == 404


async def test_message_content_encrypted_at_rest(client: AsyncClient, db_session) -> None:
    headers = await _authed_headers(client, "conv3@example.com")
    conversation_id = (await client.post("/conversations", headers=headers)).json()["id"]

    await client.post(
        "/messages", headers=headers, json={"conversation_id": conversation_id, "content": "penicillin allergy"}
    )

    from sqlalchemy import text

    raw = await db_session.execute(
        text("SELECT content FROM messages WHERE conversation_id = :cid AND role = 'user'"),
        {"cid": conversation_id},
    )
    assert raw.scalar_one() != "penicillin allergy"
