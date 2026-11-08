from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.agent.session import AgentSession, AgentState
from app.config import load_config
from app.db.models import Booking, BookingStatus, Calendar
from app.db.session import Database
from app.llm.custom_resolver import CustomDateTimeResolver

TZ = ZoneInfo("Asia/Kolkata")


def next_working_day():
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


CASES = [
    {
        "language": "ml-IN",
        "opening": "നാളെ രാവിലെ 10 മണിക്ക് അപ്പോയിന്റ്മെന്റ് വേണം",
        "name": "എന്റെ പേര് അഞ്ജലി",
        "confirm": "അതെ, ബുക്ക് ചെയ്യാം",
        "available": "സമയം ലഭ്യമാണ്",
        "booked": "ബുക്ക് ചെയ്തു",
    },
    {
        "language": "hi-IN",
        "opening": "कल सुबह 10 बजे अपॉइंटमेंट चाहिए",
        "name": "मेरा नाम आरव शर्मा",
        "confirm": "हाँ, बुक कर दीजिए",
        "available": "स्लॉट उपलब्ध है",
        "booked": "बुक हो गया है",
    },
    {
        "language": "ta-IN",
        "opening": "நாளை காலை 10 மணிக்கு வேண்டும்",
        "name": "என் பெயர் மீரா",
        "confirm": "ஆமாம், பதிவு செய்யுங்கள்",
        "available": "இடம் உள்ளது",
        "booked": "பதிவு செய்யப்பட்டது",
    },
    {
        "language": "mr-IN",
        "opening": "उद्या सकाळी 10 वाजता हवे आहे",
        "name": "माझे नाव स्नेहा",
        "confirm": "होय, बुक करा",
        "available": "स्लॉट उपलब्ध आहे",
        "booked": "बुक झाली आहे",
    },
    {
        "language": "bn-IN",
        "opening": "কাল সকাল ১০টায় অ্যাপয়েন্টমেন্ট চাই",
        "name": "আমার নাম রিয়া",
        "confirm": "হ্যাঁ, বুক করুন",
        "available": "স্লট পাওয়া যাচ্ছে",
        "booked": "বুক হয়েছে",
    },
    {
        "language": "en-IN",
        "opening": "tomorrow at 10 am please",
        "name": "My name is Asha Rao",
        "confirm": "yes, book it",
        "available": "is available",
        "booked": "has been booked",
    },
]


@pytest.mark.parametrize("case", CASES, ids=[case["language"] for case in CASES])
@pytest.mark.asyncio
async def test_agent_replies_in_the_callers_language(
    database: Database, agent_config: Any, clinic_calendar: Calendar, case: dict[str, str]
) -> None:
    from app.config import load_config

    config = load_config(agent_config)
    target_day = next_working_day()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=CustomDateTimeResolver(),
            caller_phone="+919000000020",
        )
        agent.start()

        reply1 = await agent.process_turn(case["opening"])
        assert agent.language == case["language"]
        assert agent.call.language == case["language"]
        assert case["available"] in reply1
        assert agent.state == AgentState.AWAITING_NAME

        reply2 = await agent.process_turn(case["name"])
        assert agent.state == AgentState.AWAITING_CONFIRMATION
        assert case["name"].split()[-1] in reply2

        reply3 = await agent.process_turn(case["confirm"])
        assert agent.state == AgentState.COMPLETED
        assert case["booked"] in reply3
        assert agent.booking_id is not None

        booking = session.scalar(
            select(Booking).where(Booking.id == int(agent.booking_id))
        )
        assert booking is not None
        assert booking.status == str(BookingStatus.CONFIRMED)
        assert booking.slot_start.date() == target_day


@pytest.fixture
def mixed_agent(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> Iterator[AgentSession]:
    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=load_config(agent_config),
            resolver=CustomDateTimeResolver(),
        )
        agent.start()
        yield agent


@pytest.mark.parametrize(
    ("opening", "name", "confirmation", "language", "expected_name"),
    [
        (
            "kal subah 10 baje please",
            "mera naam Aarav Sharma hai",
            "haan",
            "hi-IN",
            "Aarav Sharma",
        ),
        ("naale raavile 10 mani please", "ente peru Anjali aanu", "athe", "ml-IN", "Anjali"),
        ("naalai kaalai 10 mani please", "en peyar Meera", "aama sari", "ta-IN", "Meera"),
        ("kal shokal 10 tay please", "amar naam Riya", "hya thik ache", "bn-IN", "Riya"),
    ],
)
@pytest.mark.asyncio
async def test_code_mixed_booking_flow(
    mixed_agent: AgentSession,
    opening: str,
    name: str,
    confirmation: str,
    language: str,
    expected_name: str,
) -> None:
    await mixed_agent.process_turn(opening)
    assert mixed_agent.state == AgentState.AWAITING_NAME
    assert mixed_agent.language == language
    assert mixed_agent.requested_time == "10:00"

    reply = await mixed_agent.process_turn(name)
    assert mixed_agent.caller_name == expected_name
    assert expected_name in reply
    assert mixed_agent.state == AgentState.AWAITING_CONFIRMATION
    assert mixed_agent.language == language

    await mixed_agent.process_turn(confirmation)
    assert mixed_agent.state == AgentState.COMPLETED
    assert mixed_agent.call.language == language
    booking = mixed_agent.session.scalar(select(Booking))
    assert booking is not None
    assert booking.patient_name == expected_name
    assert booking.status == str(BookingStatus.CONFIRMED)
    assert booking.slot_start.date() == next_working_day()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mera naam Aarav Sharma hai.", "Aarav Sharma"),
        ("Mera naam Aarav he", "Aarav"),
        ("mera naam Aarav hun", "Aarav"),
        ("ente peru Anjali aanu", "Anjali"),
        ("ente per Anjali aanu", "Anjali"),
        ("en peyar Meera", "Meera"),
        ("amar naam Riya", "Riya"),
        ("मेरा नाम आरव शर्मा है", "आरव शर्मा"),
        ("मेरा नाम आरव शर्मा है।", "आरव शर्मा"),
        ("എന്റെ പേര് അഞ്ജലി ആണ്", "അഞ്ജലി"),
        ("என் பெயர் மீரா ஆகும்", "மீரா"),
        ("surname is Rao", None),
        ("xmera naam Aarav", None),
        ("ente personal appointment", None),
        ("mera naamfoo", None),
    ],
)
def test_name_prefixes_and_trailing_copulas(
    mixed_agent: AgentSession, text: str, expected: str | None
) -> None:
    assert mixed_agent._extract_name(text) == expected


@pytest.mark.parametrize(
    "confirmation",
    [
        "no, book another time", "not now, yes", "don't book", "do not book",
        "DON'T confirm", "don’t book", "dont book", "yes but never book",
        "yes, cancel", "nahi book", "nahin, haan", "mat book karo",
        "venda, book", "illa, athe", "vendam sari", "illai aama",
        "வேண்டாம், சரி", "இல்லை, பதிவு", "വേണ്ട, ബുക്ക്", "അതെ, വേണ്ടാ",
        "ഇല്ല, ശരി", "नहीं, बुक", "मत बुक", "না, বুক", "नको, बुक",
        "వద్దు బుక్", "ಬೇಡ ಬುಕ್", "ના બુક", "ਨਹੀਂ ਬੁੱਕ",
        "callback", "calendar", "notebook", "booking reference", "yesterday", "smoking",
    ],
)
@pytest.mark.asyncio
async def test_rejection_never_books(mixed_agent: AgentSession, confirmation: str) -> None:
    await mixed_agent.process_turn("kal subah 10 baje")
    await mixed_agent.process_turn("mera naam Aarav hai")
    assert mixed_agent.state == AgentState.AWAITING_CONFIRMATION

    await mixed_agent.process_turn(confirmation)

    assert mixed_agent.state == AgentState.AWAITING_SLOT
    assert mixed_agent.booking_id is None
    assert mixed_agent.session.scalar(select(Booking)) is None
    assert mixed_agent.call_log is not None
    assert all(
        event.tool_name != "book_slot"
        for event in mixed_agent.call_log.call.events
    )


@pytest.mark.parametrize("name", ["Asha Rao", "Kal Rao", "Mani"])
@pytest.mark.asyncio
async def test_bare_names_do_not_change_reply_language(
    mixed_agent: AgentSession, name: str
) -> None:
    await mixed_agent.process_turn("kal subah 10 baje")
    await mixed_agent.process_turn(name)
    assert mixed_agent.language == "hi-IN"
    assert mixed_agent.call.language == "hi-IN"
    assert mixed_agent.caller_name == name


@pytest.mark.asyncio
async def test_provider_language_hint_remains_authoritative(mixed_agent: AgentSession) -> None:
    await mixed_agent.process_turn("kal subah 10 baje", language="ta-IN")
    assert mixed_agent.language == "ta-IN"
    assert mixed_agent.state == AgentState.AWAITING_NAME
    await mixed_agent.process_turn("ente peru Anjali aanu", language="bn-IN")
    assert mixed_agent.language == "bn-IN"
    assert mixed_agent.call.language == "bn-IN"
    assert mixed_agent.caller_name == "Anjali"


@pytest.mark.parametrize("name", ["Asha Rao", "Kal Rao", "Mani", "மீரா"])
@pytest.mark.asyncio
async def test_bare_names_after_numeric_slot_do_not_flip_language(
    mixed_agent: AgentSession, name: str
) -> None:
    initial_language = mixed_agent.language
    await mixed_agent.process_turn(f"{next_working_day().isoformat()} 10:00")
    assert mixed_agent.state == AgentState.AWAITING_NAME
    await mixed_agent.process_turn(name)
    assert mixed_agent.language == initial_language
    assert mixed_agent.call.language == initial_language
    assert mixed_agent.caller_name == name


@pytest.mark.asyncio
async def test_embedded_romanized_name_skips_name_step(mixed_agent: AgentSession) -> None:
    await mixed_agent.process_turn("kal subah 10 baje, mera naam Aarav Sharma hai.")
    assert mixed_agent.language == "hi-IN"
    assert mixed_agent.caller_name == "Aarav Sharma"
    assert mixed_agent.state == AgentState.AWAITING_CONFIRMATION
    await mixed_agent.process_turn("haan, nahi book")
    assert mixed_agent.state == AgentState.AWAITING_SLOT
    assert mixed_agent.session.scalar(select(Booking)) is None
