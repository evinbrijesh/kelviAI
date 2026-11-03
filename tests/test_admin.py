import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_index_labels_non_production(client: AsyncClient) -> None:
    response = await client.get("/admin")
    assert response.status_code == 200
    body = response.json()
    assert body["environment"] == "non-production"
    assert "/admin/calls" in body["endpoints"]
    assert "/admin/ui" in body["endpoints"]


@pytest.mark.asyncio
async def test_admin_calls_are_masked(client: AsyncClient) -> None:
    response = await client.get("/admin/calls")
    assert response.status_code == 200
    calls = response.json()
    assert len(calls) == 4
    assert {call["caller_phone"] for call in calls} == {
        "+********0001",
        "+********0002",
        "+********0003",
        "+********0004",
    }
    assert calls[0]["started_at"] >= calls[-1]["started_at"]


@pytest.mark.asyncio
async def test_admin_calls_report_outcome_and_booking_count(client: AsyncClient) -> None:
    response = await client.get("/admin/calls")
    assert response.status_code == 200
    calls = {call["call_sid"]: call for call in response.json()}
    assert calls["demo-call-0001"]["outcome"] == "booked"
    assert calls["demo-call-0001"]["booking_count"] == 1
    assert calls["demo-call-0002"]["booking_count"] == 1
    assert calls["demo-call-0003"]["status"] == "failed"
    assert calls["demo-call-0003"]["outcome"] == "abandoned"
    assert calls["demo-call-0003"]["booking_count"] == 0
    assert calls["demo-call-0004"]["outcome"] == "transferred"


@pytest.mark.asyncio
async def test_admin_bookings_are_masked(client: AsyncClient) -> None:
    response = await client.get("/admin/bookings")
    assert response.status_code == 200
    bookings = response.json()
    assert len(bookings) == 2
    assert all("*" in booking["caller_phone"] for booking in bookings)
    assert all(booking["status"] == "confirmed" for booking in bookings)
    assert all(booking["clinic"].startswith("Nila Family Clinic") for booking in bookings)
    assert all(booking["call_sid"] for booking in bookings)
    assert [booking["patient_name"] for booking in bookings] == ["Anjali Menon", "Rahul Nair"]


@pytest.mark.asyncio
async def test_admin_call_detail_has_ordered_events_and_resolution(client: AsyncClient) -> None:
    response = await client.get("/admin/calls/1")
    assert response.status_code == 200
    detail = response.json()

    assert detail["call_sid"] == "demo-call-0001"
    assert detail["outcome"] == "booked"
    assert detail["summary"]
    assert detail["resolved"]["date"]
    assert detail["resolved"]["time"] == "10:00"
    assert detail["resolved"]["timezone"] == "Asia/Kolkata"
    assert detail["resolved"]["confidence"] > 0

    seqs = [event["seq"] for event in detail["events"]]
    assert seqs == list(range(1, len(seqs) + 1))
    assert detail["events"][0]["event_type"] == "call_started"
    assert detail["events"][-1]["event_type"] == "call_ended"

    tool_calls = [
        event["tool_name"] for event in detail["events"] if event["event_type"] == "tool_call"
    ]
    assert tool_calls == ["check_availability", "book_slot"]
    book_args = next(
        event["payload"]["arguments"]
        for event in detail["events"]
        if event["event_type"] == "tool_call" and event["tool_name"] == "book_slot"
    )
    assert book_args["time"] == "10:00"
    latency = next(
        event["latency_ms"]
        for event in detail["events"]
        if event["event_type"] == "tool_result" and event["tool_name"] == "book_slot"
    )
    assert latency is not None

    assert len(detail["bookings"]) == 1
    assert "*" in detail["bookings"][0]["caller_phone"]


@pytest.mark.asyncio
async def test_admin_failed_call_detail_shows_error(client: AsyncClient) -> None:
    response = await client.get("/admin/calls/3")
    assert response.status_code == 200
    detail = response.json()
    assert detail["status"] == "failed"
    assert detail["resolved"] is None
    errors = [event for event in detail["events"] if event["event_type"] == "error"]
    assert errors and errors[0]["payload"]["reason"] == "date_unresolved"


@pytest.mark.asyncio
async def test_admin_unknown_call_returns_404(client: AsyncClient) -> None:
    response = await client.get("/admin/calls/9999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Call not found"


@pytest.mark.asyncio
async def test_admin_status_counts(client: AsyncClient) -> None:
    response = await client.get("/admin/status")
    assert response.status_code == 200
    status = response.json()
    assert status["calls"] == 4
    assert status["bookings"] == 2
    assert status["calendars"] == 1
    assert status["phone_masking"] == "enabled"
    assert status["recordings"] == "disabled"
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


@pytest.mark.asyncio
async def test_admin_ui_serves_dashboard(client: AsyncClient) -> None:
    response = await client.get("/admin/ui")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "VaaniKit" in response.text
    assert "non-production" in response.text
    assert "data-asciify-background" in response.text
    assert "/admin/static/asciify.bundle.js" in response.text
    assert "family=Redaction+50" in response.text


@pytest.mark.asyncio
async def test_admin_background_bundle_is_served(client: AsyncClient) -> None:
    response = await client.get("/admin/static/asciify.bundle.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert "swell" in response.text


@pytest.mark.asyncio
async def test_root_redirects_to_admin_ui(client: AsyncClient) -> None:
    response = await client.get("/", follow_redirects=False)
    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/admin/ui"
