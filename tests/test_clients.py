import pytest

pytestmark = pytest.mark.asyncio


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "connected"}


async def test_create_client(client):
    resp = await client.post(
        "/api/clients", json={"name": "ABC Shipping", "code": "ABC-001"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["name"] == "ABC Shipping"
    assert body["data"]["code"] == "ABC-001"
    assert body["data"]["is_active"] is True
    assert "id" in body["data"]


async def test_create_client_missing_fields(client):
    resp = await client.post("/api/clients", json={"name": "ABC Shipping"})
    assert resp.status_code == 422


async def test_duplicate_client_code_rejected(client):
    payload = {"name": "ABC Shipping", "code": "ABC-001"}
    first = await client.post("/api/clients", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/clients", json=payload)
    assert second.status_code == 409


async def test_list_clients_returns_only_active(client):
    await client.post("/api/clients", json={"name": "Client A", "code": "A-001"})
    created = await client.post(
        "/api/clients", json={"name": "Client B", "code": "B-001"}
    )
    client_id = created.json()["data"]["id"]
    await client.delete(f"/api/clients/{client_id}")

    resp = await client.get("/api/clients")
    assert resp.status_code == 200
    codes = [c["code"] for c in resp.json()["data"]]
    assert "A-001" in codes
    assert "B-001" not in codes


async def test_get_client(client):
    created = await client.post(
        "/api/clients", json={"name": "ABC Shipping", "code": "ABC-001"}
    )
    client_id = created.json()["data"]["id"]

    resp = await client.get(f"/api/clients/{client_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == client_id


async def test_get_client_not_found(client):
    resp = await client.get("/api/clients/000000000000000000000000")
    assert resp.status_code == 404


async def test_update_client(client):
    created = await client.post(
        "/api/clients", json={"name": "ABC Shipping", "code": "ABC-001"}
    )
    client_id = created.json()["data"]["id"]

    resp = await client.put(f"/api/clients/{client_id}", json={"name": "ABC Shipping Co"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "ABC Shipping Co"


async def test_disable_and_enable_client_via_update_preserves_identity(client):
    created = await client.post(
        "/api/clients", json={"name": "ABC Shipping", "code": "ABC-001"}
    )
    original = created.json()["data"]
    client_id = original["id"]

    disabled = await client.put(
        f"/api/clients/{client_id}", json={"is_active": False}
    )
    assert disabled.status_code == 200
    assert disabled.json()["message"] == "Client updated successfully"
    assert disabled.json()["data"]["is_active"] is False
    assert disabled.json()["data"]["name"] == original["name"]
    assert disabled.json()["data"]["code"] == original["code"]
    assert disabled.json()["data"]["created_at"] == original["created_at"]

    enabled = await client.put(
        f"/api/clients/{client_id}", json={"is_active": True}
    )
    assert enabled.status_code == 200
    assert enabled.json()["data"]["is_active"] is True


async def test_update_client_invalid_and_missing_ids(client):
    invalid = await client.put("/api/clients/not-an-id", json={"is_active": False})
    assert invalid.status_code == 400
    assert invalid.json() == {"detail": "Invalid client ID"}

    missing = await client.put(
        "/api/clients/000000000000000000000000",
        json={"is_active": False},
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Client not found"}


async def test_disable_client_soft_delete(client):
    created = await client.post(
        "/api/clients", json={"name": "ABC Shipping", "code": "ABC-001"}
    )
    client_id = created.json()["data"]["id"]

    resp = await client.delete(f"/api/clients/{client_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["is_active"] is False

    get_resp = await client.get(f"/api/clients/{client_id}")
    assert get_resp.json()["data"]["is_active"] is False
