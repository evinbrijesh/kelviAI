import logging
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Booking, BookingStatus, Calendar, Call, CallEvent, CallStatus, EventType

logger = logging.getLogger(__name__)

DEMO_TIMEZONE = ZoneInfo("Asia/Kolkata")
DEMO_CLINIC_NAME = "Nila Family Clinic (synthetic demo)"
CLINIC_SLOTS = [f"{hour:02d}:{minute:02d}" for hour in range(9, 17) for minute in (0, 30)]


def _working_day(day: date) -> date:
    while day.weekday() > 4:
        day += timedelta(days=1)
    return day


def _at(day_offset: int, hour: int, minute: int = 0) -> datetime:
    day = datetime.now(DEMO_TIMEZONE).date() + timedelta(days=day_offset)
    return datetime.combine(day, time(hour, minute), tzinfo=DEMO_TIMEZONE).astimezone(UTC)


def _slot(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=DEMO_TIMEZONE).astimezone(UTC)


def _available(*booked: str) -> list[str]:
    return [slot for slot in CLINIC_SLOTS if slot not in booked]


def seed_demo_data(session: Session) -> bool:
    """Insert synthetic clinic fixtures once. Returns True when rows were created."""
    existing = session.scalar(select(func.count()).select_from(Calendar))
    if existing:
        return False

    calendar = Calendar(
        name=DEMO_CLINIC_NAME,
        timezone="Asia/Kolkata",
        slot_minutes=30,
        open_time=time(9, 0),
        close_time=time(17, 0),
        working_days="0,1,2,3,4",
        is_active=True,
    )
    session.add(calendar)
    session.flush()

    booking_day = _working_day(datetime.now(DEMO_TIMEZONE).date() + timedelta(days=1))
    booking_date = booking_day.isoformat()
    slot_10 = _slot(booking_day, 10, 0)
    slot_1030 = _slot(booking_day, 10, 30)
    slot_12 = _slot(booking_day, 12, 0)

    booked_call = Call(
        call_sid="demo-call-0001",
        caller_phone="+919000000001",
        language="malayalam",
        channel="simulation",
        status=CallStatus.COMPLETED,
        started_at=_at(-1, 9, 30),
        ended_at=_at(-1, 9, 34),
        summary=f"Anjali Menon booked a 30 minute consultation on {booking_date} at 10:00.",
    )
    conflict_call = Call(
        call_sid="demo-call-0002",
        caller_phone="+919000000003",
        language="malayalam",
        channel="simulation",
        status=CallStatus.COMPLETED,
        started_at=_at(-1, 11, 0),
        ended_at=_at(-1, 11, 3),
        summary=(
            f"Rahul Nair requested 10:00, accepted the 10:30 alternative, "
            f"and booked a consultation on {booking_date}."
        ),
    )
    failed_call = Call(
        call_sid="demo-call-0003",
        caller_phone="+919000000002",
        language="malayalam",
        channel="simulation",
        status=CallStatus.FAILED,
        started_at=_at(-1, 14, 0),
        ended_at=_at(-1, 14, 1),
        summary="Caller hung up before the requested day could be resolved.",
    )
    transferred_call = Call(
        call_sid="demo-call-0004",
        caller_phone="+919000000004",
        language="malayalam",
        channel="simulation",
        status=CallStatus.TRANSFERRED,
        started_at=_at(-1, 15, 0),
        ended_at=_at(-1, 15, 2),
        summary="Caller asked about insurance coverage and was transferred to a human agent.",
    )
    hindi_call = Call(
        call_sid="demo-call-0005",
        caller_phone="+919000000005",
        language="hindi",
        channel="simulation",
        status=CallStatus.COMPLETED,
        started_at=_at(-1, 13, 0),
        ended_at=_at(-1, 13, 4),
        summary=f"Priya Sharma booked a 30 minute consultation on {booking_date} at 12:00.",
    )
    session.add_all([booked_call, conflict_call, failed_call, transferred_call, hindi_call])
    session.flush()

    session.add_all(
        [
            CallEvent(
                call_id=booked_call.id,
                seq=1,
                event_type=EventType.CALL_STARTED,
                payload={"channel": "simulation", "language": "malayalam"},
            ),
            CallEvent(
                call_id=booked_call.id,
                seq=2,
                event_type=EventType.USER_TURN,
                payload={"text": "നാളെ രാവിലെ 10 മണിക്ക് അപ്പോയിന്റ്മെന്റ് വേണം"},
            ),
            CallEvent(
                call_id=booked_call.id,
                seq=3,
                event_type=EventType.DATE_RESOLVED,
                payload={
                    "date": booking_date,
                    "time": "10:00",
                    "timezone": "Asia/Kolkata",
                    "confidence": 0.95,
                    "explanation": "Detected tomorrow (നാളെ); Detected time '10 മണി'",
                },
            ),
            CallEvent(
                call_id=booked_call.id,
                seq=4,
                event_type=EventType.TOOL_CALL,
                tool_name="check_availability",
                payload={"arguments": {"date": booking_date, "time_slot": "10:00"}},
            ),
            CallEvent(
                call_id=booked_call.id,
                seq=5,
                event_type=EventType.TOOL_RESULT,
                tool_name="check_availability",
                payload={
                    "status": "ok",
                    "clinic": DEMO_CLINIC_NAME,
                    "date": booking_date,
                    "timezone": "Asia/Kolkata",
                    "available": _available(),
                    "booked": [],
                },
                latency_ms=9,
            ),
            CallEvent(
                call_id=booked_call.id,
                seq=6,
                event_type=EventType.AGENT_TURN,
                payload={"text": f"{booking_date} at 10:00 is available."},
            ),
            CallEvent(
                call_id=booked_call.id,
                seq=7,
                event_type=EventType.USER_TURN,
                payload={"text": "എന്റെ പേര് അഞ്ജലി മേനോൻ."},
            ),
            CallEvent(
                call_id=booked_call.id,
                seq=8,
                event_type=EventType.AGENT_TURN,
                payload={"text": "Confirming Anjali Menon, 10:00. Shall I book it?"},
            ),
            CallEvent(
                call_id=booked_call.id,
                seq=9,
                event_type=EventType.USER_TURN,
                payload={"text": "അതെ, ബുക്ക് ചെയ്യാം."},
            ),
            CallEvent(
                call_id=booked_call.id,
                seq=10,
                event_type=EventType.TOOL_CALL,
                tool_name="book_slot",
                payload={
                    "arguments": {
                        "caller_name": "Anjali Menon",
                        "date": booking_date,
                        "time": "10:00",
                    }
                },
            ),
            CallEvent(
                call_id=booked_call.id,
                seq=11,
                event_type=EventType.TOOL_RESULT,
                tool_name="book_slot",
                payload={
                    "status": "confirmed",
                    "booking_id": "1",
                    "clinic": DEMO_CLINIC_NAME,
                    "patient_name": "Anjali Menon",
                    "slot_start": slot_10.isoformat(),
                    "slot_end": _slot(booking_day, 10, 30).isoformat(),
                    "timezone": "Asia/Kolkata",
                },
                latency_ms=21,
            ),
            CallEvent(
                call_id=booked_call.id,
                seq=12,
                event_type=EventType.CALL_ENDED,
                payload={"outcome": "booked"},
            ),
            CallEvent(
                call_id=conflict_call.id,
                seq=1,
                event_type=EventType.CALL_STARTED,
                payload={"channel": "simulation", "language": "malayalam"},
            ),
            CallEvent(
                call_id=conflict_call.id,
                seq=2,
                event_type=EventType.USER_TURN,
                payload={"text": "രാവിലെ 10 മണിക്ക് വേണം"},
            ),
            CallEvent(
                call_id=conflict_call.id,
                seq=3,
                event_type=EventType.DATE_RESOLVED,
                payload={
                    "date": booking_date,
                    "time": "10:00",
                    "timezone": "Asia/Kolkata",
                    "confidence": 0.95,
                    "explanation": "Detected tomorrow (നാളെ); Detected time '10 മണി'",
                },
            ),
            CallEvent(
                call_id=conflict_call.id,
                seq=4,
                event_type=EventType.TOOL_CALL,
                tool_name="check_availability",
                payload={"arguments": {"date": booking_date, "time_slot": "10:00"}},
            ),
            CallEvent(
                call_id=conflict_call.id,
                seq=5,
                event_type=EventType.TOOL_RESULT,
                tool_name="check_availability",
                payload={
                    "status": "ok",
                    "clinic": DEMO_CLINIC_NAME,
                    "date": booking_date,
                    "timezone": "Asia/Kolkata",
                    "available": _available("10:00"),
                    "booked": ["10:00"],
                },
                latency_ms=11,
            ),
            CallEvent(
                call_id=conflict_call.id,
                seq=6,
                event_type=EventType.AGENT_TURN,
                payload={"text": "10:00 is taken. 10:30 is the nearest open slot."},
            ),
            CallEvent(
                call_id=conflict_call.id,
                seq=7,
                event_type=EventType.USER_TURN,
                payload={"text": "10:30 ആകാം."},
            ),
            CallEvent(
                call_id=conflict_call.id,
                seq=8,
                event_type=EventType.AGENT_TURN,
                payload={"text": "Confirming Rahul Nair, 10:30. Shall I book it?"},
            ),
            CallEvent(
                call_id=conflict_call.id,
                seq=9,
                event_type=EventType.USER_TURN,
                payload={"text": "അതെ."},
            ),
            CallEvent(
                call_id=conflict_call.id,
                seq=10,
                event_type=EventType.TOOL_CALL,
                tool_name="book_slot",
                payload={
                    "arguments": {
                        "caller_name": "Rahul Nair",
                        "date": booking_date,
                        "time": "10:30",
                    }
                },
            ),
            CallEvent(
                call_id=conflict_call.id,
                seq=11,
                event_type=EventType.TOOL_RESULT,
                tool_name="book_slot",
                payload={
                    "status": "confirmed",
                    "booking_id": "2",
                    "clinic": DEMO_CLINIC_NAME,
                    "patient_name": "Rahul Nair",
                    "slot_start": slot_1030.isoformat(),
                    "slot_end": _slot(booking_day, 11, 0).isoformat(),
                    "timezone": "Asia/Kolkata",
                },
                latency_ms=18,
            ),
            CallEvent(
                call_id=conflict_call.id,
                seq=12,
                event_type=EventType.CALL_ENDED,
                payload={"outcome": "booked"},
            ),
            CallEvent(
                call_id=failed_call.id,
                seq=1,
                event_type=EventType.CALL_STARTED,
                payload={"channel": "simulation", "language": "malayalam"},
            ),
            CallEvent(
                call_id=failed_call.id,
                seq=2,
                event_type=EventType.USER_TURN,
                payload={"text": "അടുത്ത തിങ്കളാഴ്ച"},
            ),
            CallEvent(
                call_id=failed_call.id,
                seq=3,
                event_type=EventType.ERROR,
                payload={"reason": "date_unresolved", "confidence": 0.0},
            ),
            CallEvent(
                call_id=failed_call.id,
                seq=4,
                event_type=EventType.CALL_ENDED,
                payload={"outcome": "abandoned"},
            ),
            CallEvent(
                call_id=transferred_call.id,
                seq=1,
                event_type=EventType.CALL_STARTED,
                payload={"channel": "simulation", "language": "malayalam"},
            ),
            CallEvent(
                call_id=transferred_call.id,
                seq=2,
                event_type=EventType.USER_TURN,
                payload={"text": "ഇൻഷുറൻസ് കവറേജിനെപ്പറ്റി അറിയണം"},
            ),
            CallEvent(
                call_id=transferred_call.id,
                seq=3,
                event_type=EventType.TOOL_CALL,
                tool_name="transfer_to_human",
                payload={"arguments": {"reason": "caller asked about insurance coverage"}},
            ),
            CallEvent(
                call_id=transferred_call.id,
                seq=4,
                event_type=EventType.TOOL_RESULT,
                tool_name="transfer_to_human",
                payload={
                    "status": "transfer_requested",
                    "reason": "caller asked about insurance coverage",
                    "message": "A human agent will follow up. No outbound call was placed.",
                },
                latency_ms=3,
            ),
            CallEvent(
                call_id=transferred_call.id,
                seq=5,
                event_type=EventType.AGENT_TURN,
                payload={"text": "I have asked a human agent to call you back."},
            ),
            CallEvent(
                call_id=transferred_call.id,
                seq=6,
                event_type=EventType.CALL_ENDED,
                payload={"outcome": "transferred"},
            ),
            CallEvent(
                call_id=hindi_call.id,
                seq=1,
                event_type=EventType.CALL_STARTED,
                payload={"channel": "simulation", "language": "hindi"},
            ),
            CallEvent(
                call_id=hindi_call.id,
                seq=2,
                event_type=EventType.USER_TURN,
                payload={"text": "कल दोपहर 12 बजे अपॉइंटमेंट चाहिए"},
            ),
            CallEvent(
                call_id=hindi_call.id,
                seq=3,
                event_type=EventType.DATE_RESOLVED,
                payload={
                    "date": booking_date,
                    "time": "12:00",
                    "timezone": "Asia/Kolkata",
                    "confidence": 0.93,
                    "explanation": "Detected tomorrow (कल); Detected time '12 बजे'",
                },
            ),
            CallEvent(
                call_id=hindi_call.id,
                seq=4,
                event_type=EventType.TOOL_CALL,
                tool_name="check_availability",
                payload={"arguments": {"date": booking_date, "time_slot": "12:00"}},
            ),
            CallEvent(
                call_id=hindi_call.id,
                seq=5,
                event_type=EventType.TOOL_RESULT,
                tool_name="check_availability",
                payload={
                    "status": "ok",
                    "clinic": DEMO_CLINIC_NAME,
                    "date": booking_date,
                    "timezone": "Asia/Kolkata",
                    "available": _available(),
                    "booked": [],
                },
                latency_ms=10,
            ),
            CallEvent(
                call_id=hindi_call.id,
                seq=6,
                event_type=EventType.AGENT_TURN,
                payload={"text": f"{booking_date} को 12:00 उपलब्ध है।"},
            ),
            CallEvent(
                call_id=hindi_call.id,
                seq=7,
                event_type=EventType.USER_TURN,
                payload={"text": "मेरा नाम प्रिया शर्मा है।"},
            ),
            CallEvent(
                call_id=hindi_call.id,
                seq=8,
                event_type=EventType.AGENT_TURN,
                payload={"text": "प्रिया शर्मा, 12:00 की पुष्टि करें। क्या मैं बुक कर दूं?"},
            ),
            CallEvent(
                call_id=hindi_call.id,
                seq=9,
                event_type=EventType.USER_TURN,
                payload={"text": "हाँ, बुक कर दीजिए।"},
            ),
            CallEvent(
                call_id=hindi_call.id,
                seq=10,
                event_type=EventType.TOOL_CALL,
                tool_name="book_slot",
                payload={
                    "arguments": {
                        "caller_name": "Priya Sharma",
                        "date": booking_date,
                        "time": "12:00",
                    }
                },
            ),
            CallEvent(
                call_id=hindi_call.id,
                seq=11,
                event_type=EventType.TOOL_RESULT,
                tool_name="book_slot",
                payload={
                    "status": "confirmed",
                    "booking_id": "3",
                    "clinic": DEMO_CLINIC_NAME,
                    "patient_name": "Priya Sharma",
                    "slot_start": slot_12.isoformat(),
                    "slot_end": _slot(booking_day, 12, 30).isoformat(),
                    "timezone": "Asia/Kolkata",
                },
                latency_ms=19,
            ),
            CallEvent(
                call_id=hindi_call.id,
                seq=12,
                event_type=EventType.CALL_ENDED,
                payload={"outcome": "booked"},
            ),
        ]
    )

    session.add_all(
        [
            Booking(
                calendar_id=calendar.id,
                call_id=booked_call.id,
                patient_name="Anjali Menon",
                caller_phone="+919000000001",
                slot_start=slot_10,
                slot_end=_slot(booking_day, 10, 30),
                status=BookingStatus.CONFIRMED,
                notes="Synthetic demo booking",
            ),
            Booking(
                calendar_id=calendar.id,
                call_id=conflict_call.id,
                patient_name="Rahul Nair",
                caller_phone="+919000000003",
                slot_start=slot_1030,
                slot_end=_slot(booking_day, 11, 0),
                status=BookingStatus.CONFIRMED,
                notes="Synthetic demo booking",
            ),
            Booking(
                calendar_id=calendar.id,
                call_id=hindi_call.id,
                patient_name="Priya Sharma",
                caller_phone="+919000000005",
                slot_start=slot_12,
                slot_end=_slot(booking_day, 12, 30),
                status=BookingStatus.CONFIRMED,
                notes="Synthetic demo booking",
            ),
        ]
    )

    logger.info("Seeded synthetic clinic, five demo calls, and three demo bookings")
    return True
