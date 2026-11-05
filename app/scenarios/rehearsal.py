"""Deterministic three-call Malayalam rehearsal.

Runs the three joint integration scenarios against an isolated SQLite database so
the demo path never depends on the live Gnani API:

1. Successful booking.
2. Requested slot unavailable, nearest alternative accepted.
3. Ambiguous request clarified, then caller hangs up.
"""

import asyncio
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.agent.session import AgentSession, AgentState
from app.config import AppConfig, load_config
from app.db.models import Booking, BookingStatus
from app.db.seed import DEMO_CLINIC_NAME, seed_demo_data
from app.db.session import Database
from app.llm.custom_resolver import CustomDateTimeResolver
from app.llm.interfaces import DateTimeResolver

TZ = ZoneInfo("Asia/Kolkata")
CALLER_PHONES = ("+919000000021", "+919000000022", "+919000000023")
HANGUP_SUMMARY = "Caller hung up before completing the request."


class RehearsalError(AssertionError):
    """Raised when a scripted call does not reach its expected state."""


def _next_working_day() -> date:
    day = datetime.now(TZ).date() + timedelta(days=1)
    while day.weekday() > 4:
        day += timedelta(days=1)
    return day


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise RehearsalError(message)


async def _successful_booking(
    session: Session, config: AppConfig, resolver: DateTimeResolver, day: date
) -> None:
    agent = AgentSession(
        session=session,
        config=config,
        resolver=resolver,
        call_sid="rehearsal-success",
        caller_phone=CALLER_PHONES[0],
    )
    agent.start()

    reply = await agent.process_turn(f"{day.isoformat()} 14:00-ന് വേണം")
    _check(agent.state == AgentState.AWAITING_NAME, "expected the agent to ask for a name")
    _check("14:00" in reply, "expected the requested slot to be offered")

    await agent.process_turn("എന്റെ പേര് മീര കൃഷ്ണൻ")
    _check(
        agent.state == AgentState.AWAITING_CONFIRMATION,
        "expected the agent to ask for confirmation",
    )

    reply = await agent.process_turn("അതെ, ബുക്ക് ചെയ്യാം")
    _check(agent.state == AgentState.COMPLETED, "expected the call to complete")
    _check(agent.chosen_time == "14:00", "expected the requested 14:00 slot")
    _check("ബുക്ക് ചെയ്തു" in reply, "expected a booking confirmation reply")
    result = agent.booking_result
    _check(result is not None, "expected a booking result")
    assert result is not None
    _check(result["status"] == "confirmed", "expected a confirmed booking result")

    booking = session.get(Booking, int(agent.booking_id or 0))
    _check(booking is not None, "expected the booking to exist in the database")
    assert booking is not None
    _check(booking.status == str(BookingStatus.CONFIRMED), "expected a confirmed booking row")
    _check(booking.patient_name == "മീര കൃഷ്ണൻ", "expected the caller name on the booking")


async def _unavailable_slot_with_alternative(
    session: Session, config: AppConfig, resolver: DateTimeResolver, day: date
) -> None:
    agent = AgentSession(
        session=session,
        config=config,
        resolver=resolver,
        call_sid="rehearsal-conflict",
        caller_phone=CALLER_PHONES[1],
    )
    agent.start()

    reply = await agent.process_turn(f"{day.isoformat()} 10:00-ന് വേണം")
    _check(agent.state == AgentState.AWAITING_NAME, "expected the agent to ask for a name")
    _check(
        "10:00-ന് സമയം ലഭ്യമല്ല" in reply,
        "expected the agent to report the conflict",
    )
    _check("11:00" in reply, "expected the nearest open slot in the reply")

    await agent.process_turn("എന്റെ പേര് രാഹുൽ നായർ")
    reply = await agent.process_turn("അതെ, ബുക്ക് ചെയ്യാം")

    _check(agent.state == AgentState.COMPLETED, "expected the call to complete")
    _check(agent.chosen_time == "11:00", "expected the 11:00 alternative, not 10:00")
    _check("ബുക്ക് ചെയ്തു" in reply, "expected a booking confirmation reply")


async def _ambiguous_request_then_hangup(
    session: Session, config: AppConfig, resolver: DateTimeResolver, _day: date
) -> None:
    agent = AgentSession(
        session=session,
        config=config,
        resolver=resolver,
        call_sid="rehearsal-ambiguous",
        caller_phone=CALLER_PHONES[2],
    )
    agent.start()

    reply = await agent.process_turn("ഒരു അപ്പോയിന്റ്മെന്റ് വേണം")
    _check(agent.state == AgentState.CLARIFYING, "expected a clarification request")
    _check("വ്യക്തമാക്കാമോ" in reply, "expected the Malayalam clarification prompt")

    agent.hangup()

    _check(agent.state == AgentState.FAILED, "expected the call to end after the hangup")
    _check(agent.call.status == "failed", "expected a failed call status")
    _check(agent.call.summary == HANGUP_SUMMARY, "expected the abandoned call summary")


async def run_rehearsal(config_path: str | Path | None = None) -> int:
    config = load_config(config_path)
    resolver = CustomDateTimeResolver()
    day = _next_working_day()
    checks = (
        ("successful booking", _successful_booking),
        ("unavailable slot with alternative", _unavailable_slot_with_alternative),
        ("ambiguous time and hangup", _ambiguous_request_then_hangup),
    )

    with tempfile.TemporaryDirectory() as directory:
        database = Database(f"sqlite:///{(Path(directory) / 'rehearsal.db').as_posix()}")
        try:
            database.create_schema()
            with database.session() as session:
                _check(
                    seed_demo_data(session),
                    "expected the demo seed to populate an empty database",
                )

            for index, (label, rehearsal) in enumerate(checks, start=1):
                with database.session() as session:
                    try:
                        await rehearsal(session, config, resolver, day)
                    except RehearsalError as exc:
                        print(f"[{index}/3] {label}: FAIL - {exc}")
                        return 1
                print(f"[{index}/3] {label}: PASS")

            print(f"Rehearsal passed for {day.isoformat()} at {DEMO_CLINIC_NAME}.")
            return 0
        finally:
            database.dispose()


def main() -> None:
    raise SystemExit(asyncio.run(run_rehearsal()))


if __name__ == "__main__":
    main()
