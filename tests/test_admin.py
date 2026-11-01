import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_index_labels_non_production(client: AsyncClient) -> None:
    response = await client.get("/admin")
    assert response.status_code == 200
    body = response.json()
    assert body["environment"] == "non-production"
    assert "/admin/calls" in body["endpoints"]


@pytest.mark.asyncio
async def test_admin_calls_are_masked(client: AsyncClient) -> None:
    response = await client.get("/admin/calls")
    assert response.status_code == 200
    calls = response.json()
    assert len(calls) == 2
    assert {call["caller_phone"] for call in calls} == {"+********0001", "+********0002"}
    assert calls[0]["started_at"] >= calls[1]["started_at"]


@pytest.mark.asyncio
async def test_admin_bookings_are_masked(client: AsyncClient) -> None:
    response = await client.get("/admin/bookings")
    assert response.status_code == 200
    bookings = response.json()
    assert len(bookings) == 2
    assert all("*" in booking["caller_phone"] for booking in bookings)
    assert all(booking["status"] == "confirmed" for booking in bookings)


@pytest.mark.asyncio
async def test_admin_status_counts(client: AsyncClient) -> None:
    response = await client.get("/admin/status")
    assert response.status_code == 200
    status = response.json()
    assert status["calls"] == 2
    assert status["bookings"] == 2
    assert status["calendars"] == 1
    assert status["phone_masking"] == "enabled"
    assert status["environment"] == "non-production"


@pytest.mark.asyncio
async def test_admin_tools_returns_declared_schemas(client: AsyncClient) -> None:
    response = await client.get("/admin/tools")
    assert response.status_code == 200
    tools = {tool["name"]: tool for tool in response.json()}
    assert set(tools) == {"check_availability", "book_slot"}
    assert tools["check_availability"]["parameters"]["required"] == ["date"]


@pytest.mark.asyncio
async def test_admin_calls_limit_is_validated(client: AsyncClient) -> None:
    response = await client.get("/admin/calls", params={"limit": 0})
    assert response.status_code == 422
