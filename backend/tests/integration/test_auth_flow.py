import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_register_login_and_access_protected_route(client: AsyncClient) -> None:
    register_resp = await client.post(
        "/auth/register", json={"email": "patient@example.com", "password": "s3curePassw0rd"}
    )
    assert register_resp.status_code == 201
    tokens = register_resp.json()
    assert "access_token" in tokens and "refresh_token" in tokens

    # duplicate registration is rejected
    dup_resp = await client.post(
        "/auth/register", json={"email": "patient@example.com", "password": "s3curePassw0rd"}
    )
    assert dup_resp.status_code == 409

    login_resp = await client.post(
        "/auth/login", json={"email": "patient@example.com", "password": "s3curePassw0rd"}
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]

    headers = {"Authorization": f"Bearer {access_token}"}
    patient_resp = await client.get("/patient", headers=headers)
    assert patient_resp.status_code == 200
    assert "id" in patient_resp.json()


async def test_wrong_password_rejected(client: AsyncClient) -> None:
    await client.post("/auth/register", json={"email": "a@example.com", "password": "correcthorse1"})
    resp = await client.post("/auth/login", json={"email": "a@example.com", "password": "wrong-password"})
    assert resp.status_code == 401


async def test_protected_route_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/patient")
    assert resp.status_code in (401, 403)


async def test_refresh_flow(client: AsyncClient) -> None:
    register_resp = await client.post(
        "/auth/register", json={"email": "refresh@example.com", "password": "s3curePassw0rd"}
    )
    refresh_token = register_resp.json()["refresh_token"]

    refresh_resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()

    # an access token cannot be used as a refresh token
    access_token = register_resp.json()["access_token"]
    bad_refresh = await client.post("/auth/refresh", json={"refresh_token": access_token})
    assert bad_refresh.status_code == 401
