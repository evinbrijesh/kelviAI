import asyncio
import threading
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.config import ToolConfig
from app.db.models import Booking, Calendar
from app.db.session import Database
from app.tools.booking import BookingTools, build_tool_registry

TZ = ZoneInfo("Asia/Kolkata")
BOOKING_TOOL = ToolConfig(
    name="book_slot",
    description="Book a slot",
    enabled=True,
    parameters={
        "type": "object",
        "properties": {
            "caller_name": {"type": "string"},
            "date": {"type": "string"},
            "time": {"type": "string"},
        },
        "required": ["caller_name", "date", "time"],
    },
)


def next_working_day() -> date:
    day = datetime.now(TZ).date() + timedelta(days=1)
    while day.weekday() > 4:
        day += timedelta(days=1)
    return day


@pytest.fixture
def committed_clinic(database: Database) -> Iterator[Database]:
    with database.session() as session:
        session.add(
            Calendar(
                name="Race Clinic",
                timezone="Asia/Kolkata",
                slot_minutes=30,
                open_time=time(9, 0),
                close_time=time(17, 0),
                working_days="0,1,2,3,4",
                is_active=True,
            )
        )
    yield database


def test_two_callers_racing_for_one_slot(committed_clinic: Database) -> None:
    database = committed_clinic
    day = next_working_day()
    barrier = threading.Barrier(2)
    original = BookingTools._has_conflict

    def synchronized_conflict(self: BookingTools, *args: Any) -> bool:
        # Both callers must pass the soft check before either writes, which is
        # exactly the window the database-level unique index has to close.
        result = original(self, *args)
        barrier.wait(timeout=10)
        return result

    results: list[dict[str, Any]] = []
    results_lock = threading.Lock()

    def attempt(name: str) -> None:
        session = database.session_factory()
        try:
            registry = build_tool_registry(session, [BOOKING_TOOL])
            outcome: dict[str, Any] = asyncio.run(
                registry.invoke(
                    "book_slot",
                    {"caller_name": name, "date": day.isoformat(), "time": "10:00"},
                )
            )
            session.commit()
        except Exception as exc:  # pragma: no cover - only on a broken race
            session.rollback()
            outcome = {"status": "error", "error": type(exc).__name__}
        finally:
            session.close()

        with results_lock:
            results.append(outcome)

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(BookingTools, "_has_conflict", synchronized_conflict)
        threads = [
            threading.Thread(target=attempt, args=(name,))
            for name in ("Meera Krishnan", "Rahul Nair")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert not any(thread.is_alive() for thread in threads)

    assert sorted(result["status"] for result in results) == ["confirmed", "conflict"]

    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Booking)) == 1
        booking = session.scalars(select(Booking)).one()
        assert booking.patient_name in {"Meera Krishnan", "Rahul Nair"}
