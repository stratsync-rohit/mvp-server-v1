import pytest


@pytest.mark.asyncio
async def test_local_frontend_on_port_3001_can_call_api(client):
    response = await client.options(
        "/api/clients",
        headers={
            "Origin": "http://localhost:3001",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:3001"
    )
