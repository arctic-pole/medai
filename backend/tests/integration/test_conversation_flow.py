import pytest
from httpx import AsyncClient

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


async def test_send_message_returns_stub_reply_and_persists(client: AsyncClient) -> None:
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
    assert "headache since this morning" in body["assistant_message"]["content"]
    # Phase 2 scaffolding must not look like real reasoning/diagnosis
    assert "placeholder" in body["assistant_message"]["content"].lower()

    list_resp = await client.get("/messages", headers=headers, params={"conversation_id": conversation_id})
    assert list_resp.status_code == 200
    roles = [m["role"] for m in list_resp.json()]
    assert roles == ["user", "assistant"]


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
