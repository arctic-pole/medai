import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _authed_headers(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post("/auth/register", json={"email": email, "password": "s3curePassw0rd"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_vital_accepted_and_appears_in_current_snapshot(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "vitalsA@example.com")

    resp = await client.post(
        "/vitals", headers=headers, json={"type": "heart_rate", "value": 72, "unit": "bpm"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["source"] == "manual"
    assert body["accepted"] is True

    snapshot = await client.get("/vitals", headers=headers)
    assert snapshot.status_code == 200
    assert snapshot.json()[0]["type"] == "heart_rate"
    assert snapshot.json()[0]["value"] == 72


async def test_create_vital_rejects_wrong_unit_and_does_not_appear_in_snapshot(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "vitalsB@example.com")

    resp = await client.post(
        "/vitals", headers=headers, json={"type": "heart_rate", "value": 72, "unit": "beats per minute"}
    )
    assert resp.status_code == 422
    assert "MEASUREMENT_UNRELIABLE" in resp.json()["detail"]

    snapshot = await client.get("/vitals", headers=headers)
    assert snapshot.json() == []

    # a rejected reading is still logged to history, per "never silently drop"
    history = await client.get("/vitals/history", headers=headers)
    assert len(history.json()) == 1
    assert history.json()[0]["accepted"] is False


async def test_newer_reading_updates_snapshot_older_backdated_one_does_not(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "vitalsC@example.com")

    await client.post(
        "/vitals",
        headers=headers,
        json={"type": "heart_rate", "value": 70, "unit": "bpm", "timestamp": "2026-01-01T00:00:00Z"},
    )
    await client.post(
        "/vitals",
        headers=headers,
        json={"type": "heart_rate", "value": 80, "unit": "bpm", "timestamp": "2026-06-01T00:00:00Z"},
    )
    # backdated — should not overwrite the newer snapshot value
    await client.post(
        "/vitals",
        headers=headers,
        json={"type": "heart_rate", "value": 60, "unit": "bpm", "timestamp": "2026-02-01T00:00:00Z"},
    )

    snapshot = await client.get("/vitals", headers=headers)
    assert snapshot.json()[0]["value"] == 80

    history = await client.get("/vitals/history", headers=headers, params={"type": "heart_rate"})
    assert len(history.json()) == 3


async def test_measurement_history_filters_by_type(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "vitalsD@example.com")
    await client.post("/vitals", headers=headers, json={"type": "heart_rate", "value": 72, "unit": "bpm"})
    await client.post("/vitals", headers=headers, json={"type": "oxygen_saturation", "value": 98, "unit": "%"})

    history = await client.get("/vitals/history", headers=headers, params={"type": "oxygen_saturation"})
    assert len(history.json()) == 1
    assert history.json()[0]["type"] == "oxygen_saturation"


async def test_register_and_list_devices(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "vitalsE@example.com")

    resp = await client.post("/devices", headers=headers, json={"device_type": "manual", "label": "My notebook"})
    assert resp.status_code == 201

    listing = await client.get("/devices", headers=headers)
    assert len(listing.json()) == 1
    assert listing.json()[0]["label"] == "My notebook"


async def test_vitals_require_auth(client: AsyncClient) -> None:
    resp = await client.get("/vitals")
    assert resp.status_code in (401, 403)


async def test_sync_vitals_from_health_platform_forces_source_and_reports_per_reading(
    client: AsyncClient,
) -> None:
    headers = await _authed_headers(client, "vitalsF@example.com")
    device_id = (
        await client.post("/devices", headers=headers, json={"device_type": "health_connect", "label": "Pixel"})
    ).json()["id"]

    resp = await client.post(
        "/vitals/sync",
        headers=headers,
        json={
            "device_id": device_id,
            "readings": [
                {"type": "heart_rate", "value": 68, "unit": "bpm", "timestamp": "2026-06-01T00:00:00Z"},
                {"type": "oxygen_saturation", "value": 85, "unit": "%", "timestamp": "2026-06-01T00:01:00Z"},
                {"type": "heart_rate", "value": 68, "unit": "beats", "timestamp": "2026-06-01T00:02:00Z"},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["synced"] == 3
    assert body["accepted"] == 2
    assert body["rejected"] == 1
    assert body["results"][2]["accepted"] is False

    snapshot = {v["type"]: v for v in (await client.get("/vitals", headers=headers)).json()}
    assert snapshot["heart_rate"]["source"] == "health_platform"
    assert snapshot["oxygen_saturation"]["value"] == 85


async def test_sync_vitals_rejects_device_not_owned_by_caller(client: AsyncClient) -> None:
    headers_a = await _authed_headers(client, "vitalsG@example.com")
    headers_b = await _authed_headers(client, "vitalsH@example.com")
    device_id = (
        await client.post("/devices", headers=headers_a, json={"device_type": "health_connect"})
    ).json()["id"]

    resp = await client.post(
        "/vitals/sync",
        headers=headers_b,
        json={"device_id": device_id, "readings": [{"type": "heart_rate", "value": 70, "unit": "bpm", "timestamp": "2026-06-01T00:00:00Z"}]},
    )
    assert resp.status_code == 404
