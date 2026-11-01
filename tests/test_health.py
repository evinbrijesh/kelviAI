import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Trigger startup lifespan
        async with app.router.lifespan_context(app):
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["message"] == "Service healthy"


@pytest.mark.asyncio
async def test_health_endpoint_when_unhealthy() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        app.state.is_healthy = False
        response = await client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "error"
        assert data["message"] == "Service unavailable"
