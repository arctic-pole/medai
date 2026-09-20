import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _authed_headers(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post("/auth/register", json={"email": email, "password": "s3curePassw0rd"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_profile_get_creates_default_then_updates(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "profile@example.com")

    get_resp = await client.get("/profile", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["consent_status"] == "not_provided"

    update_resp = await client.patch(
        "/profile", headers=headers, json={"age": 34, "sex": "female", "consent_status": "granted"}
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["age"] == 34
    assert body["sex"] == "female"
    assert body["consent_status"] == "granted"


async def test_allergy_crud_and_encryption_at_rest(client: AsyncClient, db_session) -> None:
    headers = await _authed_headers(client, "allergy@example.com")

    create_resp = await client.post(
        "/allergies", headers=headers, json={"substance": "penicillin", "reaction": "rash", "severity": "moderate"}
    )
    assert create_resp.status_code == 201
    allergy_id = create_resp.json()["id"]
    assert create_resp.json()["substance"] == "penicillin"

    # verify the raw DB column is not plaintext (application-level encryption at rest)
    from sqlalchemy import text

    raw = await db_session.execute(text("SELECT substance FROM allergies WHERE id = :id"), {"id": allergy_id})
    raw_value = raw.scalar_one()
    assert raw_value != "penicillin"

    list_resp = await client.get("/allergies", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    update_resp = await client.patch(f"/allergies/{allergy_id}", headers=headers, json={"severity": "severe"})
    assert update_resp.status_code == 200
    assert update_resp.json()["severity"] == "severe"

    delete_resp = await client.delete(f"/allergies/{allergy_id}", headers=headers)
    assert delete_resp.status_code == 204

    final_list = await client.get("/allergies", headers=headers)
    assert final_list.json() == []


async def test_history_and_medications_isolated_per_patient(client: AsyncClient) -> None:
    headers_a = await _authed_headers(client, "userA@example.com")
    headers_b = await _authed_headers(client, "userB@example.com")

    await client.post("/history", headers=headers_a, json={"condition": "asthma"})
    await client.post(
        "/medications", headers=headers_a, json={"name": "albuterol", "dosage": "2 puffs", "frequency": "as needed"}
    )

    # user B cannot see user A's data
    history_b = await client.get("/history", headers=headers_b)
    medications_b = await client.get("/medications", headers=headers_b)
    assert history_b.json() == []
    assert medications_b.json() == []

    history_a = await client.get("/history", headers=headers_a)
    assert len(history_a.json()) == 1
    assert history_a.json()[0]["condition"] == "asthma"


async def test_cannot_access_another_patients_entry_by_id(client: AsyncClient) -> None:
    headers_a = await _authed_headers(client, "ownerA@example.com")
    headers_b = await _authed_headers(client, "ownerB@example.com")

    create_resp = await client.post("/history", headers=headers_a, json={"condition": "migraine"})
    entry_id = create_resp.json()["id"]

    forbidden_get = await client.patch(f"/history/{entry_id}", headers=headers_b, json={"status": "resolved"})
    assert forbidden_get.status_code == 404
