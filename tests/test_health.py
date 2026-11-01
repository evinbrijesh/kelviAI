import pytest
from httpx import AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


@pytest.mark.asyncio
async def test_health_endpoint_when_unhealthy(client: AsyncClient) -> None:
    app.state.is_healthy = False
    response = await client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["message"] == "Service unavailable"
