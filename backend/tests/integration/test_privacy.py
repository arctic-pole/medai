"""Phase 13 (security_hardening: privacy_controls). GET /privacy/export and DELETE /privacy/me
(app/api/privacy.py, app/privacy/service.py) — user-confirmed scope: build both."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import Patient, User

pytestmark = pytest.mark.asyncio


async def _register(client: AsyncClient, email: str, password: str = "s3curePassw0rd") -> dict[str, str]:
    resp = await client.post("/auth/register", json={"email": email, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_delete_requires_auth(client: AsyncClient) -> None:
    resp = await client.request("DELETE", "/privacy/me", json={"password": "irrelevant"})
    assert resp.status_code in (401, 403)


async def test_export_returns_every_category_of_the_callers_own_real_data(client: AsyncClient) -> None:
    headers = await _register(client, "privacy-export@example.com")

    await client.patch(
        "/profile", headers=headers,
        json={"age": 40, "sex": "female", "height_cm": 165, "weight_kg": 60, "consent_status": "granted"},
    )
    await client.post("/history", headers=headers, json={"condition": "asthma"})
    await client.post("/allergies", headers=headers, json={"substance": "penicillin", "reaction": "hives"})
    await client.post("/medications", headers=headers, json={"name": "albuterol"})
    conversation_id = (await client.post("/conversations", headers=headers)).json()["id"]
    await client.post("/messages", headers=headers, json={"conversation_id": conversation_id, "content": "hello"})
    await client.post("/vitals", headers=headers, json={"type": "heart_rate", "value": 72, "unit": "bpm"})
    device_id = (await client.post("/devices", headers=headers, json={"device_type": "manual", "label": "x"})).json()["id"]

    resp = await client.get("/privacy/export", headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["user"]["email"] == "privacy-export@example.com"
    assert body["profile"]["age"] == 40
    assert body["medical_history"][0]["condition"] == "asthma"
    assert body["allergies"][0]["substance"] == "penicillin"
    assert body["allergies"][0]["reaction"] == "hives"  # decrypted, real plaintext for the owner
    assert body["current_medications"][0]["name"] == "albuterol"
    assert len(body["conversations"]) == 1
    assert body["conversations"][0]["messages"][0]["content"] == "hello"
    assert body["vitals"][0]["type"] == "heart_rate"
    assert body["vitals"][0]["value"] == 72
    assert body["devices"][0]["id"] == device_id
    assert len(body["audit_logs"]) > 0  # included for transparency


async def test_export_never_includes_another_patients_data(client: AsyncClient) -> None:
    headers_a = await _register(client, "privacy-isoA@example.com")
    headers_b = await _register(client, "privacy-isoB@example.com")

    await client.post("/allergies", headers=headers_a, json={"substance": "shellfish"})

    export_b = await client.get("/privacy/export", headers=headers_b)
    assert export_b.json()["allergies"] == []


async def test_delete_rejects_wrong_password(client: AsyncClient, db_session) -> None:
    headers = await _register(client, "privacy-wrongpw@example.com", password="theRealPassword1")

    resp = await client.request("DELETE", "/privacy/me", headers=headers, json={"password": "not-the-real-password"})
    assert resp.status_code == 401

    # Account still exists and is unaffected.
    user = (await db_session.execute(select(User).where(User.email == "privacy-wrongpw@example.com"))).scalar_one()
    assert user is not None


async def test_delete_cascades_across_every_owned_table(client: AsyncClient, db_session) -> None:
    password = "theRealPassword1"
    headers = await _register(client, "privacy-delete@example.com", password=password)

    await client.patch("/profile", headers=headers, json={"age": 40, "consent_status": "granted"})
    await client.post("/history", headers=headers, json={"condition": "asthma"})
    await client.post("/allergies", headers=headers, json={"substance": "penicillin"})
    await client.post("/medications", headers=headers, json={"name": "albuterol"})
    conversation_id = (await client.post("/conversations", headers=headers)).json()["id"]
    await client.post("/messages", headers=headers, json={"conversation_id": conversation_id, "content": "hello"})
    await client.post("/vitals", headers=headers, json={"type": "heart_rate", "value": 72, "unit": "bpm"})
    await client.post("/devices", headers=headers, json={"device_type": "manual"})

    user_before = (
        await db_session.execute(select(User).where(User.email == "privacy-delete@example.com"))
    ).scalar_one()
    user_id = user_before.id

    resp = await client.request("DELETE", "/privacy/me", headers=headers, json={"password": password})
    assert resp.status_code == 204

    # The user row itself is gone.
    user_after = (await db_session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    assert user_after is None

    # The old access token no longer resolves to anything — the account is functionally gone.
    followup = await client.get("/patient", headers=headers)
    assert followup.status_code == 401

    # A brand new registration with the same email succeeds — proves the row (and its unique
    # email constraint) was actually removed, not just unlinked.
    reregister = await client.post("/auth/register", json={"email": "privacy-delete@example.com", "password": "aDifferentPassword1"})
    assert reregister.status_code == 201
