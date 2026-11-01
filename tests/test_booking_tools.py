from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.calls.session_log import CallSessionLog, start_call
from app.config import ToolConfig
from app.db.models import Booking, BookingStatus, Calendar, CallEvent
from app.db.session import Database
from app.tools.booking import BookingTools, build_tool_registry
from app.tools.registry import ToolError, ToolRegistry

TZ = ZoneInfo("Asia/Kolkata")


def next_working_day() -> date:
    day = datetime.now(TZ).date() + timedelta(days=1)
    while day.weekday() > 4:
        day += timedelta(days=1)
    return day


def next_sunday() -> date:
    today = datetime.now(TZ).date()
    return today + timedelta(days=(6 - today.weekday()) % 7)


def tool_config(name: str, *required: str) -> ToolConfig:
    return ToolConfig(
        name=name,
        description=name.replace("_", " "),
        enabled=True,
        parameters={
            "type": "object",
            "properties": {field: {"type": "string"} for field in required},
            "required": list(required),
        },
    )


CONFIGURED_TOOLS = [
    tool_config("check_availability", "date"),
    tool_config("book_slot", "caller_name", "date", "time"),
    tool_config("cancel_booking", "booking_id"),
    tool_config("transfer_to_human", "reason"),
]


@dataclass
class Harness:
    session: Session
    log: CallSessionLog
    registry: ToolRegistry


@pytest.fixture
def harness(database: Database) -> Iterator[Harness]:
    with database.session() as session:
        session.add(
            Calendar(
                name="Test Clinic",
                timezone="Asia/Kolkata",
                slot_minutes=30,
                open_time=time(9, 0),
                close_time=time(17, 0),
                working_days="0,1,2,3,4",
                is_active=True,
            )
        )

    session = database.session_factory()
    log = start_call(
        session,
        call_sid="test-call",
        caller_phone="+919000000010",
        language="malayalam",
    )
    registry = build_tool_registry(session, CONFIGURED_TOOLS, call=log.call)

    yield Harness(session=session, log=log, registry=registry)

    session.rollback()
    session.close()


async def book(
    harness: Harness, day: date, clock: str, name: str = "Meera Krishnan"
) -> dict[str, Any]:
    result: dict[str, Any] = await harness.registry.invoke(
        "book_slot",
        {"caller_name": name, "date": day.isoformat(), "time": clock},
    )
    return result


def confirmed_bookings(session: Session) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(Booking)
            .where(Booking.status == str(BookingStatus.CONFIRMED))
        )
        or 0
    )


@pytest.mark.asyncio
async def test_check_availability_lists_open_slots(harness: Harness) -> None:
    day = next_working_day()
    result: dict[str, Any] = await harness.registry.invoke(
        "check_availability", {"date": day.isoformat()}
    )

    assert result["status"] == "ok"
    assert result["clinic"] == "Test Clinic"
    assert result["available"][0] == "09:00"
    assert result["available"][-1] == "16:30"
    assert result["booked"] == []


@pytest.mark.asyncio
async def test_check_availability_reports_a_closed_day(harness: Harness) -> None:
    result: dict[str, Any] = await harness.registry.invoke(
        "check_availability", {"date": next_sunday().isoformat()}
    )

    assert result["status"] == "closed"
    assert result["available"] == []


@pytest.mark.asyncio
async def test_check_availability_filters_by_period(harness: Harness) -> None:
    result: dict[str, Any] = await harness.registry.invoke(
        "check_availability", {"date": next_working_day().isoformat(), "time_slot": "morning"}
    )

    assert result["available"]
    assert all(slot < "12:00" for slot in result["available"])


@pytest.mark.asyncio
async def test_check_availability_rejects_a_bad_date(harness: Harness) -> None:
    result: dict[str, Any] = await harness.registry.invoke(
        "check_availability", {"date": "next monday"}
    )

    assert result["status"] == "invalid_date"


@pytest.mark.asyncio
async def test_book_slot_persists_a_confirmed_booking(harness: Harness) -> None:
    day = next_working_day()
    result = await book(harness, day, "10:00")

    assert result["status"] == "confirmed"
    assert result["clinic"] == "Test Clinic"
    assert result["slot_start"].endswith("+05:30")

    booking = harness.session.get(Booking, int(result["booking_id"]))
    assert booking is not None
    assert booking.status == str(BookingStatus.CONFIRMED)
    assert booking.patient_name == "Meera Krishnan"
    assert booking.call_id == harness.log.call.id
    slot_start = booking.slot_start
    if slot_start.tzinfo is None:
        slot_start = slot_start.replace(tzinfo=UTC)
    assert slot_start.astimezone(TZ).strftime("%H:%M") == "10:00"


@pytest.mark.asyncio
async def test_duplicate_booking_is_rejected(harness: Harness) -> None:
    day = next_working_day()

    first = await book(harness, day, "10:00")
    second = await book(harness, day, "10:00", name="Rahul Nair")

    assert first["status"] == "confirmed"
    assert second["status"] == "conflict"
    assert second["available"][0] == "10:30"
    assert confirmed_bookings(harness.session) == 1


@pytest.mark.asyncio
async def test_unaligned_time_is_not_bookable(harness: Harness) -> None:
    result = await book(harness, next_working_day(), "10:15")

    assert result["status"] == "invalid_slot"
    assert confirmed_bookings(harness.session) == 0


@pytest.mark.asyncio
async def test_closed_day_is_not_bookable(harness: Harness) -> None:
    result = await book(harness, next_sunday(), "10:00")

    assert result["status"] == "closed"
    assert confirmed_bookings(harness.session) == 0


@pytest.mark.asyncio
async def test_racing_duplicate_is_caught_by_the_unique_index(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    day = next_working_day()
    first = await book(harness, day, "10:00")
    assert first["status"] == "confirmed"

    monkeypatch.setattr(BookingTools, "_has_conflict", lambda self, *args: False)
    second = await book(harness, day, "10:00", name="Rahul Nair")

    assert second["status"] == "conflict"
    assert confirmed_bookings(harness.session) == 1

    harness.log.agent_turn("The event log is still writable after the conflict")
    assert harness.session.scalar(select(func.count()).select_from(CallEvent)) == 2


@pytest.mark.asyncio
async def test_cancel_frees_the_slot(harness: Harness) -> None:
    day = next_working_day()
    booked = await book(harness, day, "10:00")

    cancelled: dict[str, Any] = await harness.registry.invoke(
        "cancel_booking", {"booking_id": booked["booking_id"]}
    )
    assert cancelled["status"] == "cancelled"

    availability: dict[str, Any] = await harness.registry.invoke(
        "check_availability", {"date": day.isoformat()}
    )
    assert "10:00" in availability["available"]

    rebooked = await book(harness, day, "10:00", name="Anjali Menon")
    assert rebooked["status"] == "confirmed"


@pytest.mark.asyncio
async def test_cancelling_twice_reports_the_existing_cancellation(harness: Harness) -> None:
    booked = await book(harness, next_working_day(), "10:00")
    await harness.registry.invoke("cancel_booking", {"booking_id": booked["booking_id"]})

    again: dict[str, Any] = await harness.registry.invoke(
        "cancel_booking", {"booking_id": booked["booking_id"]}
    )

    assert again["status"] == "already_cancelled"


@pytest.mark.asyncio
async def test_cancel_unknown_booking_is_rejected(harness: Harness) -> None:
    missing: dict[str, Any] = await harness.registry.invoke(
        "cancel_booking", {"booking_id": "9999"}
    )
    malformed: dict[str, Any] = await harness.registry.invoke(
        "cancel_booking", {"booking_id": "not-a-number"}
    )

    assert missing["status"] == "not_found"
    assert malformed["status"] == "not_found"


@pytest.mark.asyncio
async def test_transfer_to_human_places_no_booking(harness: Harness) -> None:
    result: dict[str, Any] = await harness.registry.invoke(
        "transfer_to_human", {"reason": "caller asked for a doctor"}
    )

    assert result["status"] == "transfer_requested"
    assert result["reason"] == "caller asked for a doctor"
    assert confirmed_bookings(harness.session) == 0


def test_disabled_tool_is_not_registered(harness: Harness) -> None:
    disabled = ToolConfig(
        name="book_slot", description="Book a slot", enabled=False, parameters={}
    )
    registry = build_tool_registry(harness.session, [disabled], call=harness.log.call)

    assert registry.names() == []


def test_declared_tool_without_a_handler_is_rejected(harness: Harness) -> None:
    unknown = ToolConfig(name="send_sms", description="Send a message", enabled=True, parameters={})

    with pytest.raises(ToolError, match="no handler"):
        build_tool_registry(harness.session, [unknown], call=harness.log.call)
