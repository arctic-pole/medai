"""Phase 13 (security_hardening: input_sanitisation). Every user-writable string/list field
must have an explicit upper bound — found several that didn't (notes, reaction, severity,
dosage, frequency, sex, consent_status, emergency_contact_*, login password, refresh token,
vital unit/device_type/label, and VitalSyncRequest.readings' list length) and fixed them in
app/schemas/*.py. These tests assert the boundary actually rejects oversized input, not just
that reasonable input still works (already covered elsewhere)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _authed_headers(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post("/auth/register", json={"email": email, "password": "s3curePassw0rd"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_login_rejects_an_oversized_password_before_hashing_it(client: AsyncClient) -> None:
    """The real risk: an unbounded password forces argon2 to hash an arbitrarily large input on
    every unauthenticated attempt — a CPU-cost DoS vector. This must be a fast 422, not a slow
    hash-then-fail."""

    huge_password = "a" * 10_000
    resp = await client.post("/auth/login", json={"email": "nobody@example.com", "password": huge_password})
    assert resp.status_code == 422


async def test_medical_history_notes_rejects_oversized_input(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "bounds-history@example.com")
    resp = await client.post(
        "/history", headers=headers, json={"condition": "asthma", "notes": "x" * 10_000}
    )
    assert resp.status_code == 422


async def test_allergy_reaction_rejects_oversized_input(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "bounds-allergy@example.com")
    resp = await client.post(
        "/allergies", headers=headers, json={"substance": "penicillin", "reaction": "x" * 10_000}
    )
    assert resp.status_code == 422


async def test_profile_emergency_contact_rejects_oversized_input(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "bounds-profile@example.com")
    resp = await client.patch(
        "/profile", headers=headers, json={"emergency_contact_name": "x" * 10_000}
    )
    assert resp.status_code == 422


async def test_vitals_sync_rejects_an_unbounded_readings_list(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "bounds-vitals@example.com")
    device_id = (
        await client.post("/devices", headers=headers, json={"device_type": "health_connect"})
    ).json()["id"]

    too_many_readings = [
        {"type": "heart_rate", "value": 70, "unit": "bpm", "timestamp": "2026-06-01T00:00:00Z"}
        for _ in range(1001)
    ]
    resp = await client.post(
        "/vitals/sync", headers=headers, json={"device_id": device_id, "readings": too_many_readings}
    )
    assert resp.status_code == 422


async def test_vitals_unit_rejects_oversized_input(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "bounds-vitals-unit@example.com")
    resp = await client.post(
        "/vitals", headers=headers, json={"type": "heart_rate", "value": 70, "unit": "b" * 100}
    )
    assert resp.status_code == 422
