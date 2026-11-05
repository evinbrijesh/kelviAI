from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.agent.session import AgentSession, AgentState
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
