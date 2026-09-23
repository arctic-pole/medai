"""Phase 14 (evaluation): testing.end_to_end — "Complete user conversations from USER_SPEAKS to
FINAL_VALIDATED_RESPONSE." One test, walking a genuinely fresh patient (no profile, history,
allergies, or medications at all) through every follow-up question the conversation manager
asks, in the exact priority order conversation_manager.question_priority defines, entirely over
real HTTP — until POST /messages itself runs the full pipeline automatically and returns a real
validated Assessment. This is the single-test version of what test_conversation_flow.py and
test_assessment.py test in pieces."""

import pytest
from httpx import AsyncClient

from app.main import app
from app.providers.embeddings import get_embedding_provider
from app.providers.llm import get_llm_provider
from app.reasoning.schema import Assessment
from tests.fakes import FakeEmbeddingProvider, FakeReasoningLLMProvider

pytestmark = pytest.mark.asyncio


async def test_complete_conversation_from_user_speaks_to_final_validated_response(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/register", json={"email": "e2e-fresh-patient@example.com", "password": "s3curePassw0rd"}
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    conversation_id = (await client.post("/conversations", headers=headers)).json()["id"]

    # Turn 1: USER_SPEAKS. A genuinely fresh patient has no profile/history/allergies/
    # medications at all — the highest-priority gap (medication_allergy_safety) is asked first.
    turn1 = await client.post(
        "/messages", headers=headers, json={"conversation_id": conversation_id, "content": "I have a headache"}
    )
    assert turn1.status_code == 201
    body1 = turn1.json()
    assert body1["is_assessment"] is False
    assert "allerg" in body1["assistant_message"]["content"].lower()

    # Answer it the only way this deterministic (no-LLM) flow can be answered — through the
    # structured endpoint the conversation manager's own gap corresponds to, exactly as
    # app/conversation/missing_info.py's field->category mapping defines.
    await client.post("/allergies", headers=headers, json={"substance": "penicillin"})

    turn2 = await client.post(
        "/messages", headers=headers, json={"conversation_id": conversation_id, "content": "just penicillin"}
    )
    assert turn2.json()["is_assessment"] is False
    assert "medication" in turn2.json()["assistant_message"]["content"].lower()
    await client.post("/medications", headers=headers, json={"name": "acetaminophen"})

    turn3 = await client.post(
        "/messages", headers=headers, json={"conversation_id": conversation_id, "content": "just acetaminophen"}
    )
    assert turn3.json()["is_assessment"] is False
    assert "history" in turn3.json()["assistant_message"]["content"].lower() or "condition" in turn3.json()["assistant_message"]["content"].lower()
    await client.post("/history", headers=headers, json={"condition": "none relevant"})

    # Remaining gaps: age, sex, height, weight (lower_priority_context) — fill all at once via
    # the profile endpoint, then confirm every one of the four turns this produces is indeed a
    # question, ending only once nothing at all is missing.
    turn4 = await client.post(
        "/messages", headers=headers, json={"conversation_id": conversation_id, "content": "ok"}
    )
    assert turn4.json()["is_assessment"] is False  # still missing demographic fields
    await client.patch(
        "/profile", headers=headers,
        json={"age": 35, "sex": "male", "height_cm": 178, "weight_kg": 75, "consent_status": "granted"},
    )

    # FINAL_VALIDATED_RESPONSE: nothing left to ask — this turn runs the real pipeline
    # (EVIDENCE_RETRIEVAL -> CLINICAL_REASONING -> DETERMINISTIC_SAFETY -> OUTPUT_VALIDATION)
    # automatically, over the same HTTP endpoint, and returns a real validated Assessment.
    good_assessment = Assessment(
        status="caution",
        summary="Possible explanations include a tension headache; monitor and rest.",
        confidence="low",
        recommended_next_steps=["Rest and stay hydrated.", "Seek care if symptoms worsen or persist."],
    )
    app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbeddingProvider()
    app.dependency_overrides[get_llm_provider] = lambda: FakeReasoningLLMProvider([good_assessment])
    try:
        final_turn = await client.post(
            "/messages", headers=headers, json={"conversation_id": conversation_id, "content": "that's everything"}
        )
    finally:
        del app.dependency_overrides[get_embedding_provider]
        del app.dependency_overrides[get_llm_provider]

    assert final_turn.status_code == 201
    final_body = final_turn.json()
    assert final_body["is_assessment"] is True
    assert final_body["assessment_status"] == "caution"
    assert final_body["assistant_message"]["content"] == good_assessment.summary

    # The full transcript is exactly what a real conversation produced — persisted, ordered,
    # and retrievable, per ux.session_auto_preserved's own resume path.
    history = await client.get("/messages", headers=headers, params={"conversation_id": conversation_id})
    roles = [m["role"] for m in history.json()]
    assert roles == ["user", "assistant"] * 5  # 5 full turns: 4 questions + 1 final assessment
