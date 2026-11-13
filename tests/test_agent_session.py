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
async def test_agent_session_confirm_with_urappakkikko_and_variants(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> None:
    from app.config import load_config

    config = load_config(agent_config)
    resolver = CustomDateTimeResolver()
    target_day = next_working_day()

    for phrase in ("ഉറപ്പാക്കിക്കോ.", "പുറപ്പാക്കിക്കോ.", "ഉറപ്പിച്ചോളൂ"):
        with database.session() as session:
            agent = AgentSession(
                session=session,
                config=config,
                resolver=resolver,
                caller_phone="+919000000088",
            )
            agent.start()
            await agent.process_turn(f"{target_day.isoformat()} 14:00-ന് വേണം")
            await agent.process_turn("ജോൺസൺ എന്നുള്ള പേരിൽ ബുക്ക് ചെയ്തേക്കാമോ?")
            assert agent.state == AgentState.AWAITING_CONFIRMATION
            reply = await agent.process_turn(phrase)
            assert agent.state == AgentState.COMPLETED
            assert "റഫറൻസ്" in reply or "ബുക്ക് ചെയ്തു" in reply


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


@pytest.mark.asyncio
async def test_agent_session_reschedule_flow(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> None:
    from app.config import ToolConfig, load_config

    config = load_config(agent_config)
    config.tools.append(
        ToolConfig(
            name="reschedule_booking",
            description="Reschedule a booking",
            enabled=True,
        )
    )
    target_date = next_working_day()

    booking_id: int
    with database.session() as session:
        booking = Booking(
            calendar_id=clinic_calendar.id,
            patient_name="Priya Thomas",
            caller_phone="+919000000012",
            slot_start=datetime.combine(
                target_date, datetime.strptime("11:00", "%H:%M").time(), tzinfo=TZ
            ).astimezone(UTC),
            slot_end=datetime.combine(
                target_date, datetime.strptime("11:30", "%H:%M").time(), tzinfo=TZ
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
            caller_phone="+919000000012",
        )
        agent.start()

        # Turn 1: Ask to reschedule without reference
        r1 = await agent.process_turn("എന്റെ അപ്പോയിന്റ്മെന്റ് മാറ്റണം")
        assert agent.state == AgentState.AWAITING_RESCHEDULE
        assert "റഫറൻസ്" in r1

        # Turn 2: Provide reference and new date/time
        utterance = f"റഫറൻസ് {booking_id} {target_date.isoformat()} ഉച്ചയ്ക്ക് 2 മണിക്ക് മാറ്റണം"
        r2 = await agent.process_turn(utterance)
        assert agent.state == AgentState.COMPLETED
        assert "മാറ്റി" in r2

    # Verify rescheduled slot in database
    with database.session() as session:
        updated = session.get(Booking, booking_id)
        assert updated is not None
        assert updated.status == str(BookingStatus.CONFIRMED)
        slot_utc = (
            updated.slot_start.replace(tzinfo=UTC)
            if updated.slot_start.tzinfo is None
            else updated.slot_start.astimezone(UTC)
        )
        assert slot_utc.astimezone(TZ).strftime("%H:%M") == "14:00"


@pytest.mark.asyncio
async def test_malayalam_name_extraction_patterns(
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
            caller_phone="+919000000015",
        )
        # Suffix pattern
        n1 = agent._extract_name("മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ് എന്ന പേരിൽ ബുക്ക് ചെയ്തോളൂ.")
        assert n1 == "മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ്"

        # Chillu-n and compound correction with filler rejection
        n2 = agent._extract_name(
            "ഞാൻ എൻ്റെ പേര് ഓൾറെഡി പറഞ്ഞല്ലോ, എൻ്റെ പേര് മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ്, അതിൽ ബുക്ക് ചെയ്തോ?"
        )
        assert n2 == "മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ്"

        # Disallowed conversational words must never be names
        assert agent._is_disallowed_name("ഓൾറെഡി പറഞ്ഞല്ലോ") is True
        assert agent._is_disallowed_name("ഇഷ്യൂ ഇല്ല") is True
        assert agent._is_disallowed_name("ബുക്ക് ചെയ്തോളൂ") is True


@pytest.mark.asyncio
async def test_conversational_name_query_and_retention(
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
            caller_phone="+919000000016",
        )
        agent.start()

        # Turn 1: Slot request
        r1 = await agent.process_turn(f"{day_str} രാവിലെ 10 മണിക്ക് അപ്പോയിൻമെൻറ്റ് വേണം")
        assert agent.state == AgentState.AWAITING_NAME
        assert "10:00" in r1

        # Turn 2: User provides name using suffix pattern
        r2 = await agent.process_turn("മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ് എന്ന പേരിൽ ബുക്ക് ചെയ്തോളൂ.")
        assert agent.state == AgentState.AWAITING_CONFIRMATION
        assert agent.caller_name == "മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ്"
        assert "മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ്" in r2

        # Turn 3: User asks what name is saved
        r3 = await agent.process_turn("എൻ്റെ പേരായിട്ടെന്താ സേവ് ചെയ്തേക്കുന്നത്, അത് പറയാൻ പറ്റുമോ?")
        assert agent.state == AgentState.AWAITING_CONFIRMATION
        assert "മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ്" in r3

        # Turn 4: User confirms with colloquial retention phrase
        r4 = await agent.process_turn("വേണ്ട, അപ്പോഴത്തേക്കിന് ബുക്ക് ചെയ്തോ? ഇഷ്യൂ ഇല്ല.")
        assert agent.state == AgentState.COMPLETED
        assert "ബുക്ക് ചെയ്തു" in r4 or "റഫറൻസ്" in r4
        assert agent.booking_id is not None

        # Verify booking in database has the accurate patient name
        b = session.get(Booking, int(agent.booking_id))
        assert b is not None
        assert b.patient_name == "മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ്"


@pytest.mark.asyncio
async def test_agent_session_identity_and_purpose_query(
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
            caller_phone="+919000000017",
        )
        agent.start()

        # Turn 1: User asks what this call is for and who is calling in Malayalam
        reply = await agent.process_turn(
            "ഹലോ, ഇത് എന്തിനുവേണ്ടി യൂസ് ചെയ്യുക എന്ന് എനിക്ക് മനസ്സിലായില്ല. ഹു ഇസ് കോളിംഗ്?"
        )
        # Should explain clinic assistant purpose instead of giving clarification error
        assert "നിലാ ഫാമിലി ക്ലിനിക്കിന്റെ" in reply and "കേൾവി AI അസിസ്റ്റന്റ്" in reply
        assert agent.state == AgentState.AWAITING_SLOT
        assert agent.clarification_count == 0

        # Turn 2: Exact colloquial phrasing from user test screenshot
        reply2 = await agent.process_turn(
            "ആ, ഇതാരാ വിളിക്കുന്നത്? ഇതെന്താ സംഗതി?"
        )
        assert "നിലാ ഫാമിലി ക്ലിനിക്കിന്റെ" in reply2 and "കേൾവി AI അസിസ്റ്റന്റ്" in reply2
        assert agent.state == AgentState.AWAITING_SLOT
        assert agent.clarification_count == 0

        # Turn 3: Transliterated / Romanized query
        reply3 = await agent.process_turn(
            "a, ithara vilikkunnath? ithentha samgathi?"
        )
        assert "നിലാ ഫാമിലി ക്ലിനിക്കിന്റെ" in reply3 and "കേൾവി AI അസിസ്റ്റന്റ്" in reply3
        assert agent.state == AgentState.AWAITING_SLOT
        assert agent.clarification_count == 0


@pytest.mark.asyncio
async def test_ennulla_name_suffix_and_language_lock_protection(
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
            caller_phone="+919000000018",
        )
        agent.start()

        # Turn 1: Slot requested in Malayalam
        await agent.process_turn(f"{day_str} രാവിലെ 10 മണിക്ക് അപ്പോയിൻമെൻറ്റ് വേണം")
        assert agent.state == AgentState.AWAITING_NAME
        assert agent.language == "ml-IN"

        # Turn 2: Caller provides name using 'എന്നുള്ള പേരിൽ'
        r2 = await agent.process_turn("ജോൺസൺ എന്നുള്ള പേരിൽ ബുക്ക് ചെയ്തോളൂ.")
        assert agent.caller_name == "ജോൺസൺ"
        assert agent.state == AgentState.AWAITING_CONFIRMATION
        assert "ജോൺസൺ" in r2
        assert agent.language == "ml-IN"

        # Turn 3: Confirmation turn in Malayalam
        r3 = await agent.process_turn("അതെ, ബുക്ക് ചെയ്തോളൂ")
        assert agent.state == AgentState.COMPLETED
        assert agent.language == "ml-IN"
        assert "ബുക്ക് ചെയ്തു" in r3


@pytest.mark.asyncio
async def test_discourse_marker_ennaatto_stripped_from_name(
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
            caller_phone="+919000000019",
        )
        agent.start()

        # Turn 1: Slot requested
        await agent.process_turn(f"{day_str} രാവിലെ 10 മണിക്ക് അപ്പോയിൻമെൻറ്റ് വേണം")
        assert agent.state == AgentState.AWAITING_NAME

        # Turn 2: User provides name with colloquial discourse marker "എന്നാട്ടോ"
        r2 = await agent.process_turn(
            "എങ്കിൽ പിന്നെ ആ സ്ലോട്ട് ബുക്ക് ചെയ്തേക്കാമോ? എന്റെ പേര് ജോൺസൺ എന്നാട്ടോ."
        )
        assert agent.caller_name == "ജോൺസൺ"
        assert "എന്നാട്ടോ" not in agent.caller_name
        assert agent.state == AgentState.AWAITING_CONFIRMATION
        assert "ജോൺസൺ" in r2
        assert "ജോൺസൺ എന്നാട്ടോ" not in r2





