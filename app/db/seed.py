import logging
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Booking, BookingStatus, Calendar, Call, CallEvent, CallStatus, EventType

logger = logging.getLogger(__name__)

DEMO_TIMEZONE = ZoneInfo("Asia/Kolkata")
DEMO_CLINIC_NAME = "Nila Family Clinic (synthetic demo)"


def _slot_utc(day_offset: int, hour: int, minute: int = 0) -> datetime:
    day = datetime.now(DEMO_TIMEZONE).date() + timedelta(days=day_offset)
    local = datetime.combine(day, time(hour, minute), tzinfo=DEMO_TIMEZONE)
    return local.astimezone(UTC)


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

    completed_call = Call(
        call_sid="demo-call-0001",
        caller_phone="+919000000001",
        language="malayalam",
        channel="simulation",
        status=CallStatus.COMPLETED,
        started_at=_slot_utc(-1, 9, 30),
        ended_at=_slot_utc(-1, 9, 34),
        summary="Caller booked a 30 minute consultation for tomorrow at 10:00.",
    )
    failed_call = Call(
        call_sid="demo-call-0002",
        caller_phone="+919000000002",
        language="malayalam",
        channel="simulation",
        status=CallStatus.FAILED,
        started_at=_slot_utc(-1, 11, 0),
        ended_at=_slot_utc(-1, 11, 1),
        summary="Caller hung up before the requested time was confirmed.",
    )
    session.add_all([completed_call, failed_call])
    session.flush()

    session.add_all(
        [
            CallEvent(
                call_id=completed_call.id,
                seq=1,
                event_type=EventType.CALL_STARTED,
                payload={"channel": "simulation", "language": "malayalam"},
            ),
            CallEvent(
                call_id=completed_call.id,
                seq=2,
                event_type=EventType.USER_TURN,
                payload={"text": "നാളെ രാവിലെ 10 മണിക്ക് അപ്പോയിന്റ്മെന്റ് വേണം"},
            ),
            CallEvent(
                call_id=completed_call.id,
                seq=3,
                event_type=EventType.TOOL_CALL,
                tool_name="check_availability",
                payload={"arguments": {"date": "tomorrow", "time_slot": "10:00"}},
                latency_ms=12,
            ),
            CallEvent(
                call_id=completed_call.id,
                seq=4,
                event_type=EventType.TOOL_RESULT,
                tool_name="check_availability",
                payload={"available": True, "slots": ["10:00"]},
                latency_ms=12,
            ),
            CallEvent(
                call_id=completed_call.id,
                seq=5,
                event_type=EventType.TOOL_CALL,
                tool_name="book_slot",
                payload={
                    "arguments": {
                        "caller_name": "Anjali Menon",
                        "date": "tomorrow",
                        "time": "10:00",
                    }
                },
                latency_ms=21,
            ),
            CallEvent(
                call_id=completed_call.id,
                seq=6,
                event_type=EventType.TOOL_RESULT,
                tool_name="book_slot",
                payload={"booking_id": "1", "status": "confirmed"},
                latency_ms=21,
            ),
            CallEvent(
                call_id=completed_call.id,
                seq=7,
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
        ]
    )

    session.add_all(
        [
            Booking(
                calendar_id=calendar.id,
                call_id=completed_call.id,
                patient_name="Anjali Menon",
                caller_phone="+919000000001",
                slot_start=_slot_utc(1, 10, 0),
                slot_end=_slot_utc(1, 10, 30),
                status=BookingStatus.CONFIRMED,
                notes="Synthetic demo booking",
            ),
            Booking(
                calendar_id=calendar.id,
                call_id=None,
                patient_name="Rahul Nair",
                caller_phone="+919000000003",
                slot_start=_slot_utc(1, 11, 0),
                slot_end=_slot_utc(1, 11, 30),
                status=BookingStatus.CONFIRMED,
                notes="Synthetic demo booking",
            ),
        ]
    )

    logger.info("Seeded synthetic clinic, demo calls, and demo bookings")
    return True
