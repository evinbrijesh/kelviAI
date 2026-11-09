from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.agent.session import AgentSession, AgentState
from app.db.models import Booking, BookingStatus, Calendar
from app.db.session import Database
from app.llm.custom_resolver import CustomDateTimeResolver
from app.llm.interfaces import DateTimeResolution, DateTimeResolver
from app.tools.registry import ToolError

TZ = ZoneInfo("Asia/Kolkata")


def next_working_day() -> date:
    day = datetime.now(TZ).date() + timedelta(days=1)
    while day.weekday() > 4:
        day += timedelta(days=1)
    return day


@pytest.fixture
def clinic_calendar(database: Database) -> Calendar:
    with database.session() as session:
        calendar = Calendar(
            name="Nila Test Clinic",
            timezone="Asia/Kolkata",
            slot_minutes=30,
            open_time=datetime.strptime("09:00", "%H:%M").time(),
            close_time=datetime.strptime("17:00", "%H:%M").time(),
            working_days="0,1,2,3,4",
            is_active=True,
        )
        session.add(calendar)
        session.flush()
        session.refresh(calendar)
        return calendar


@pytest.mark.asyncio
async def test_agent_session_start_emits_greeting(
    database: Database, agent_config: Any
) -> None:
    from app.config import load_config

    config = load_config(agent_config)
    resolver = CustomDateTimeResolver()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            caller_phone="+919000000001",
        )
        greeting = agent.start()

        assert greeting == config.agent.greeting
        assert agent.state == AgentState.AWAITING_SLOT
        assert agent.call.caller_phone == "+919000000001"
        assert agent.call.status == "in_progress"


@pytest.mark.asyncio
async def test_agent_session_multi_turn_booking(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> None:
    from app.config import load_config

    config = load_config(agent_config)
    resolver = CustomDateTimeResolver()

    target_day = next_working_day()
    day_str = target_day.isoformat()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            caller_phone="+919000000001",
        )
        agent.start()

        # Turn 1: Slot request
        reply1 = await agent.process_turn(f"{day_str} 10:00-ന് വേണം")
        assert "10:00" in reply1
        assert agent.state == AgentState.AWAITING_NAME

        # Turn 2: Caller provides name
        reply2 = await agent.process_turn("എന്റെ പേര് മീര കൃഷ്ണൻ")
        assert "Confirming" in reply2 or "മീര" in reply2
        assert agent.state == AgentState.AWAITING_CONFIRMATION

        # Turn 3: Caller confirms
        reply3 = await agent.process_turn("അതെ, ബുക്ക് ചെയ്യാം")
        assert "ബുക്ക് ചെയ്തു" in reply3 or "റഫറൻസ്" in reply3
        assert agent.state == AgentState.COMPLETED
        assert agent.booking_id is not None
        assert agent.call.status == "completed"

        # Check DB booking
        booking = session.scalar(
            select(Booking).where(Booking.id == int(agent.booking_id))
        )
        assert booking is not None
        assert booking.patient_name == "മീര കൃഷ്ണൻ"
        assert booking.status == str(BookingStatus.CONFIRMED)


@pytest.mark.asyncio
async def test_agent_session_booking_conflict_ends_call_as_failed(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> None:
    from app.config import load_config

    config = load_config(agent_config)
    resolver = CustomDateTimeResolver()

    target_day = next_working_day()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            caller_phone="+919000000005",
        )
        agent.start()

        await agent.process_turn(f"{target_day.isoformat()} 10:00-ന് വേണം")
        assert agent.state == AgentState.AWAITING_NAME

        await agent.process_turn("എന്റെ പേര് മീര കൃഷ്ണൻ")
        assert agent.state == AgentState.AWAITING_CONFIRMATION

        calendar = session.scalar(select(Calendar))
        slot_start = datetime.combine(
            target_day, datetime.strptime("10:00", "%H:%M").time(), tzinfo=TZ
        ).astimezone(UTC)
        session.add(
            Booking(
                calendar_id=calendar.id,
                patient_name="Blocking Patient",
                caller_phone="+919000000099",
                slot_start=slot_start,
                slot_end=slot_start + timedelta(minutes=30),
                status=str(BookingStatus.CONFIRMED),
            )
        )
        session.flush()

        reply = await agent.process_turn("അതെ, ബുക്ക് ചെയ്യാം")

        assert "ഉറപ്പാക്കാൻ കഴിഞ്ഞില്ല" in reply
        assert agent.state == AgentState.FAILED
        assert agent.call.status == "failed"


@pytest.mark.asyncio
async def test_agent_session_clarification_on_ambiguous_turn(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> None:
    from app.config import load_config

    config = load_config(agent_config)

    class LowConfidenceResolver(DateTimeResolver):
        def __init__(self) -> None:
            self.calls = 0

        async def resolve(
            self, text: str, language: str, context: dict[str, Any] | None = None
        ) -> DateTimeResolution:
            self.calls += 1
            if self.calls == 1:
                return DateTimeResolution(
                    date=None,
                    time=None,
                    timezone="Asia/Kolkata",
                    confidence=0.3,
                    explanation="Ambiguous utterance",
                )
            target = next_working_day()
            return DateTimeResolution(
                date=target,
                time=datetime.strptime("10:00", "%H:%M").time(),
                timezone="Asia/Kolkata",
                confidence=0.95,
                explanation="Resolved after clarification",
            )

    resolver = LowConfidenceResolver()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            caller_phone="+919000000002",
        )
        agent.start()

        # Turn 1: Ambiguous utterance -> Should ask clarification
        reply1 = await agent.process_turn("ഒരു അപ്പോയിന്റ്മെന്റ് വേണം")
        assert agent.state == AgentState.CLARIFYING
        assert "വ്യക്തമാക്കാമോ" in reply1 or "clarify" in reply1.lower()

        # Turn 2: Clarified utterance -> Should resolve
        await agent.process_turn("നാളെ രാവിലെ 10 മണിക്ക്")
        assert agent.state in (AgentState.AWAITING_NAME, AgentState.AWAITING_CONFIRMATION)


@pytest.mark.asyncio
async def test_agent_session_fails_after_max_clarifications(
    database: Database, agent_config: Any
) -> None:
    from app.config import load_config

    config = load_config(agent_config)

    class BrokenResolver(DateTimeResolver):
        async def resolve(
            self, text: str, language: str, context: dict[str, Any] | None = None
        ) -> DateTimeResolution:
            return DateTimeResolution(
                date=None,
                time=None,
                timezone="Asia/Kolkata",
                confidence=0.1,
                explanation="Failed",
            )

    resolver = BrokenResolver()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            caller_phone="+919000000003",
            max_clarifications=1,
        )
        agent.start()

        # Attempt 1: Clarification asked
        await agent.process_turn("gibberish 1")
        assert agent.state == AgentState.CLARIFYING

        # Attempt 2: Exceeds max clarifications -> Should fail cleanly
        await agent.process_turn("gibberish 2")
        assert agent.state == AgentState.FAILED
        assert agent.call.status == "failed"


@pytest.mark.asyncio
async def test_agent_session_no_availability_ends_call(
    database: Database, agent_config: Any
) -> None:
    from app.config import load_config

    config = load_config(agent_config)
    resolver = CustomDateTimeResolver()

    with database.session() as session:
        session.add(
            Calendar(
                name="Closed Test Clinic",
                timezone="Asia/Kolkata",
                slot_minutes=30,
                open_time=datetime.strptime("09:00", "%H:%M").time(),
                close_time=datetime.strptime("17:00", "%H:%M").time(),
                working_days="",
                is_active=True,
            )
        )
        session.flush()

        agent = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            caller_phone="+919000000005",
        )
        agent.start()

        reply = await agent.process_turn(f"{next_working_day().isoformat()} 10:00-ന് വേണം")

        assert "ഓപ്പൺ ക്ലിനിക്" in reply
        assert agent.state == AgentState.FAILED
        assert agent.call.status == "failed"
        assert await agent.process_turn("ഹലോ") == "ഈ കോൾ അവസാനിച്ചു."


@pytest.mark.asyncio
async def test_agent_session_all_slots_taken_ends_call(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> None:
    from app.config import load_config

    config = load_config(agent_config)
    target_day = next_working_day()

    with database.session() as session:
        for hour in range(9, 17):
            for minute in (0, 30):
                slot_start = datetime.combine(
                    target_day, datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time(),
                    tzinfo=TZ,
                ).astimezone(UTC)
                session.add(
                    Booking(
                        calendar_id=clinic_calendar.id,
                        patient_name="Synthetic Blocking Patient",
                        caller_phone="+919000000098",
                        slot_start=slot_start,
                        slot_end=slot_start + timedelta(minutes=30),
                        status=str(BookingStatus.CONFIRMED),
                    )
                )
        session.flush()

        agent = AgentSession(
            session=session,
            config=config,
            resolver=CustomDateTimeResolver(),
            caller_phone="+919000000007",
        )
        agent.start()

        reply = await agent.process_turn(f"{target_day.isoformat()} 10:00-ന് വേണം")

        assert "എല്ലാ അപ്പോയിന്റ്മെന്റുകളും" in reply
        assert agent.state == AgentState.FAILED
        assert agent.call.status == "failed"


@pytest.mark.asyncio
async def test_agent_session_transfer_sets_transferred_status(
    database: Database, agent_config: Any
) -> None:
    from app.config import load_config

    config = load_config(agent_config)

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=CustomDateTimeResolver(),
            caller_phone="+919000000006",
        )
        agent.start()

        await agent._transfer("caller asked for insurance details")

        assert agent.state == AgentState.TRANSFERRED
        assert agent.call.status == "transferred"
        ended = agent.call.events[-1]
        assert ended.event_type == "call_ended"
        assert ended.payload["outcome"] == "transferred"


@pytest.mark.asyncio
async def test_agent_session_hangup_ends_call_as_abandoned(
    database: Database, agent_config: Any
) -> None:
    from app.config import load_config

    config = load_config(agent_config)
    resolver = CustomDateTimeResolver()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            caller_phone="+919000000006",
        )
        agent.start()

        await agent.process_turn("ഒരു അപ്പോയിന്റ്മെന്റ് വേണം")
        assert agent.state == AgentState.CLARIFYING

        agent.hangup()

        assert agent.state == AgentState.FAILED
        assert agent.call.status == "failed"
        assert agent.call.summary == "Caller hung up before completing the request."
        assert await agent.process_turn("ശരി") == "ഈ കോൾ അവസാനിച്ചു."


@pytest.mark.asyncio
async def test_agent_session_tool_permission_enforcement(
    database: Database, agent_config: Any
) -> None:
    from app.config import load_config

    config = load_config(agent_config)
    # Disable book_slot in config tools
    for tool in config.tools:
        if tool.name == "book_slot":
            tool.enabled = False

    resolver = CustomDateTimeResolver()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            caller_phone="+919000000004",
        )
        agent.start()

        with pytest.raises(ToolError, match="Tool 'book_slot' is not declared or enabled"):
            await agent._safe_invoke_tool("book_slot", {})


@pytest.mark.asyncio
async def test_agent_session_alternative_slot_acceptance_prompts_for_name(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> None:
    from app.config import load_config

    config = load_config(agent_config)
    target_date = next_working_day()

    # Pre-book 10:00 to force nearest slot alternative
    with database.session() as session:
        booking = Booking(
            calendar_id=clinic_calendar.id,
            patient_name="Existing Patient",
            caller_phone="+919000000099",
            slot_start=datetime.combine(
                target_date, datetime.strptime("10:00", "%H:%M").time(), tzinfo=TZ
            ).astimezone(UTC),
            slot_end=datetime.combine(
                target_date, datetime.strptime("10:30", "%H:%M").time(), tzinfo=TZ
            ).astimezone(UTC),
            status=str(BookingStatus.CONFIRMED),
        )
        session.add(booking)
        session.commit()

    resolver = CustomDateTimeResolver()
    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            caller_phone="+919000000007",
        )
        agent.start()

        # Turn 1: Request 10:00 AM (which is taken)
        r1 = await agent.process_turn("നാളെ രാവിലെ 10 മണിക്ക്")
        assert "10:00" in r1 and "10:30" in r1 or "11:00" in r1
        assert agent.state == AgentState.AWAITING_NAME

        # Turn 2: Accept the alternative slot colloquially
        r2 = await agent.process_turn("ആയിക്കോട്ടെ, അപ്പം മതി")
        assert agent.state == AgentState.AWAITING_NAME
        assert "പേരിലാണ്" in r2 or "പേര്" in r2  # Explicitly asks for name
        assert agent.caller_name is None  # Does NOT save "ആയിക്കോട്ടെ, അപ്പം മതി" as name

        # Turn 3: Provide name
        r3 = await agent.process_turn("എന്റെ പേര് രാഹുൽ")
        assert agent.state == AgentState.AWAITING_CONFIRMATION
        assert agent.caller_name == "രാഹുൽ"
        assert "രാഹുൽ" in r3

        # Turn 4: Confirm
        r4 = await agent.process_turn("യെസ്, അത് പാക്കിക്കോ")
        assert agent.state == AgentState.COMPLETED
        assert "റഫറൻസ്" in r4


@pytest.mark.asyncio
async def test_agent_session_cancellation_flow(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> None:
    from app.config import ToolConfig, load_config

    config = load_config(agent_config)
    config.tools.append(
        ToolConfig(name="cancel_booking", description="Cancel a booking", enabled=True)
    )
    target_date = next_working_day()

    booking_id: int
    with database.session() as session:
        booking = Booking(
            calendar_id=clinic_calendar.id,
            patient_name="Rahul Nair",
            caller_phone="+919000000008",
            slot_start=datetime.combine(
                target_date, datetime.strptime("14:00", "%H:%M").time(), tzinfo=TZ
            ).astimezone(UTC),
            slot_end=datetime.combine(
                target_date, datetime.strptime("14:30", "%H:%M").time(), tzinfo=TZ
            ).astimezone(UTC),
            status=str(BookingStatus.CONFIRMED),
        )
        session.add(booking)
        session.commit()
        session.refresh(booking)
        booking_id = booking.id

    resolver = CustomDateTimeResolver()
    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            caller_phone="+919000000008",
        )
        agent.start()

        # Turn 1: Ask for cancellation without reference number
        r1 = await agent.process_turn("എനിക്ക് എന്റെ ബുക്കിംഗ് റദ്ദാക്കണം")
        assert agent.state == AgentState.AWAITING_CANCELLATION
        assert "റഫറൻസ്" in r1

        # Turn 2: Provide reference number
        r2 = await agent.process_turn(f"റഫറൻസ് {booking_id}")
        assert agent.state == AgentState.COMPLETED
        assert "റദ്ദാക്കി" in r2

    # Verify booking status in database
    with database.session() as session:
        updated = session.get(Booking, booking_id)
        assert updated is not None
        assert updated.status == str(BookingStatus.CANCELLED)
