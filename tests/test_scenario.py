from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.config import load_config
from app.db.models import Booking, BookingStatus, Call, CallEvent, EventType
from app.db.session import Database
from app.scenarios.appointment_malayalam import run_scenario


def simulation_calls(database: Database) -> list[Call]:
    with database.session() as session:
        return list(
            session.scalars(
                select(Call).where(Call.call_sid.like("sim-%")).order_by(Call.id)
            ).all()
        )


def confirmed_bookings(database: Database) -> int:
    with database.session() as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(Booking)
                .where(Booking.status == str(BookingStatus.CONFIRMED))
            )
            or 0
        )


@pytest.mark.asyncio
async def test_scenario_books_exactly_one_slot(agent_config: Path) -> None:
    assert await run_scenario() == 0

    database = Database(load_config(agent_config).database.url)
    try:
        calls = simulation_calls(database)
        assert len(calls) == 1

        call = calls[0]
        assert call.status == "completed"
        assert call.summary is not None
        assert "reference" in call.summary
        assert confirmed_bookings(database) == 4

        with database.session() as session:
            bookings = list(
                session.scalars(select(Booking).where(Booking.call_id == call.id)).all()
            )
            assert len(bookings) == 1
            assert bookings[0].status == str(BookingStatus.CONFIRMED)

            events = list(
                session.scalars(
                    select(CallEvent)
                    .where(CallEvent.call_id == call.id)
                    .order_by(CallEvent.seq)
                ).all()
            )

        assert [event.seq for event in events] == list(range(1, len(events) + 1))
        assert events[0].event_type == str(EventType.CALL_STARTED)
        assert events[-1].event_type == str(EventType.CALL_ENDED)

        tool_calls = [event for event in events if event.event_type == str(EventType.TOOL_CALL)]
        tool_results = [
            event for event in events if event.event_type == str(EventType.TOOL_RESULT)
        ]
        tool_call_names = [event.tool_name for event in tool_calls]
        tool_result_names = [event.tool_name for event in tool_results]
        assert tool_call_names[-1] == "book_slot", "last tool call must be book_slot"
        assert all(
            name == "check_availability" for name in tool_call_names[:-1]
        ), "all calls before book_slot must be check_availability"
        assert tool_result_names[-1] == "book_slot", "last tool result must be book_slot"
        assert all(
            name == "check_availability" for name in tool_result_names[:-1]
        ), "all results before book_slot must be check_availability"
        assert len(tool_call_names) >= 2, "expected at least one check_availability and book_slot"
    finally:
        database.dispose()


@pytest.mark.asyncio
async def test_scenario_is_repeatable(agent_config: Path) -> None:
    assert await run_scenario() == 0
    assert await run_scenario() == 0

    database = Database(load_config(agent_config).database.url)
    try:
        assert len(simulation_calls(database)) == 2
        assert confirmed_bookings(database) == 5
    finally:
        database.dispose()
