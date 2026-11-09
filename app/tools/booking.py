from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import ToolConfig
from app.db.models import Booking, BookingStatus, Calendar, Call, utcnow
from app.tools.registry import ToolError, ToolHandler, ToolRegistry, ToolSpec

PERIODS = {"morning", "afternoon", "evening"}


def _timezone(calendar: Calendar) -> ZoneInfo:
    return ZoneInfo(calendar.timezone)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _local_iso(value: datetime, tz: ZoneInfo) -> str:
    return _as_utc(value).astimezone(tz).isoformat()


def _slot_times(calendar: Calendar) -> list[time]:
    step = timedelta(minutes=calendar.slot_minutes)
    cursor = datetime.combine(date.min, calendar.open_time)
    close = datetime.combine(date.min, calendar.close_time)
    slots: list[time] = []
    while cursor + step <= close:
        slots.append(cursor.time())
        cursor += step
    return slots


def _is_working_day(calendar: Calendar, day: date) -> bool:
    working_days = {
        int(part) for part in calendar.working_days.split(",") if part.strip()
    }
    return day.weekday() in working_days


def _day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(0), tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def _matches_period(clock: time, period: str) -> bool:
    if period == "morning":
        return clock.hour < 12
    if period == "afternoon":
        return 12 <= clock.hour < 17
    return clock.hour >= 17


class BookingTools:
    """Handlers for the appointment tools declared in agent.yaml."""

    def __init__(self, session: Session, *, call: Call | None = None) -> None:
        self.session = session
        self.call = call

    def handlers(self) -> dict[str, ToolHandler]:
        return {
            "check_availability": self.check_availability,
            "book_slot": self.book_slot,
            "cancel_booking": self.cancel_booking,
            "reschedule_booking": self.reschedule_booking,
            "transfer_to_human": self.transfer_to_human,
        }

    async def check_availability(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            day = date.fromisoformat(str(arguments.get("date", "")))
        except ValueError:
            return {"status": "invalid_date", "message": "Date must use YYYY-MM-DD."}

        calendar = self._active_calendar()
        if calendar is None:
            return {"status": "no_calendar", "message": "No active clinic calendar is configured."}

        if not _is_working_day(calendar, day):
            return {
                "status": "closed",
                "clinic": calendar.name,
                "date": day.isoformat(),
                "timezone": calendar.timezone,
                "available": [],
                "booked": [],
            }

        tz = _timezone(calendar)
        booked = self._booked_times(calendar, day, tz)
        available = [slot for slot in _slot_times(calendar) if slot not in booked]

        preference = str(arguments.get("time_slot") or "").strip().lower()
        if preference in PERIODS:
            available = [slot for slot in available if _matches_period(slot, preference)]

        return {
            "status": "ok",
            "clinic": calendar.name,
            "date": day.isoformat(),
            "timezone": calendar.timezone,
            "available": [slot.strftime("%H:%M") for slot in available],
            "booked": [slot.strftime("%H:%M") for slot in sorted(booked)],
        }

    async def book_slot(self, arguments: dict[str, Any]) -> dict[str, Any]:
        caller_name = str(arguments.get("caller_name") or "").strip()
        try:
            day = date.fromisoformat(str(arguments.get("date", "")))
            clock = time.fromisoformat(str(arguments.get("time", "")))
        except ValueError:
            return {
                "status": "invalid_slot",
                "message": "Date must use YYYY-MM-DD and time HH:MM.",
            }

        if not caller_name:
            return {"status": "invalid_name", "message": "The caller name is required."}

        calendar = self._active_calendar()
        if calendar is None:
            return {"status": "no_calendar", "message": "No active clinic calendar is configured."}

        if not _is_working_day(calendar, day):
            return {
                "status": "closed",
                "date": day.isoformat(),
                "message": "The clinic is closed that day.",
            }

        if clock not in _slot_times(calendar):
            return {
                "status": "invalid_slot",
                "message": (
                    "Requested time is not one of the "
                    f"{calendar.slot_minutes} minute slots between "
                    f"{calendar.open_time:%H:%M} and {calendar.close_time:%H:%M}."
                ),
            }

        tz = _timezone(calendar)
        slot_start = datetime.combine(day, clock, tzinfo=tz).astimezone(UTC)
        slot_end = slot_start + timedelta(minutes=calendar.slot_minutes)

        if slot_start <= datetime.now(UTC):
            return {"status": "in_past", "message": "That slot is in the past."}

        if self._has_conflict(calendar, slot_start, slot_end):
            return self._conflict(calendar, day, clock, tz)

        booking = Booking(
            calendar_id=calendar.id,
            call_id=self.call.id if self.call else None,
            patient_name=caller_name,
            caller_phone=self.call.caller_phone if self.call else "",
            slot_start=slot_start,
            slot_end=slot_end,
            status=str(BookingStatus.CONFIRMED),
        )

        try:
            # SAVEPOINT keeps the call event log alive if two calls race for one slot.
            with self.session.begin_nested():
                self.session.add(booking)
                self.session.flush()
        except IntegrityError:
            return self._conflict(calendar, day, clock, tz)

        return {
            "status": "confirmed",
            "booking_id": str(booking.id),
            "clinic": calendar.name,
            "patient_name": booking.patient_name,
            "slot_start": _local_iso(slot_start, tz),
            "slot_end": _local_iso(slot_end, tz),
            "timezone": calendar.timezone,
        }

    async def cancel_booking(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            booking_id = int(str(arguments.get("booking_id", "")).strip())
        except ValueError:
            return {"status": "not_found", "message": "Booking reference was not recognised."}

        booking = self.session.get(Booking, booking_id)
        if booking is None:
            return {"status": "not_found", "message": "No booking matches that reference."}

        # Check caller authorization: only allow cancellation if phone matches
        current_phone = (self.call.caller_phone if self.call else "").strip()
        arg_phone = str(arguments.get("caller_phone") or "").strip()
        auth_phone = current_phone or arg_phone
        if auth_phone and booking.caller_phone and booking.caller_phone.strip() != auth_phone:
            return {
                "status": "unauthorized",
                "message": "Cannot cancel booking belonging to another caller.",
            }

        if booking.status == BookingStatus.CANCELLED:
            return {
                "status": "already_cancelled",
                "booking_id": str(booking.id),
                "message": "That booking is already cancelled.",
            }

        booking.status = str(BookingStatus.CANCELLED)
        booking.cancelled_at = utcnow()
        self.session.flush()

        return {
            "status": "cancelled",
            "booking_id": str(booking.id),
            "patient_name": booking.patient_name,
            "slot_start": _local_iso(booking.slot_start, _timezone(booking.calendar)),
        }

    async def reschedule_booking(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            booking_id = int(str(arguments.get("booking_id", "")).strip())
        except ValueError:
            return {"status": "not_found", "message": "Booking reference was not recognised."}

        booking = self.session.get(Booking, booking_id)
        if booking is None:
            return {"status": "not_found", "message": "No booking matches that reference."}

        if booking.status == str(BookingStatus.CANCELLED):
            return {
                "status": "already_cancelled",
                "booking_id": str(booking.id),
                "message": "Cannot reschedule a cancelled booking.",
            }

        try:
            day = date.fromisoformat(str(arguments.get("date", "")))
        except ValueError:
            return {"status": "invalid_date", "message": "Date must use YYYY-MM-DD."}

        calendar = booking.calendar or self._active_calendar()
        if calendar is None:
            return {"status": "no_calendar", "message": "No active clinic calendar is configured."}

        if not _is_working_day(calendar, day):
            return {"status": "closed", "clinic": calendar.name, "date": day.isoformat()}

        time_str = str(arguments.get("time_slot", "")).strip()
        try:
            clock = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            return {"status": "invalid_time", "message": "Time must use HH:MM."}

        if clock not in _slot_times(calendar):
            return {"status": "invalid_slot", "message": "Time is outside working hours."}

        tz = _timezone(calendar)
        slot_start = datetime.combine(day, clock, tzinfo=tz).astimezone(UTC)
        slot_end = slot_start + timedelta(minutes=calendar.slot_minutes)

        conflict = self.session.scalar(
            select(Booking.id)
            .where(
                Booking.calendar_id == calendar.id,
                Booking.id != booking.id,
                Booking.status == str(BookingStatus.CONFIRMED),
                Booking.slot_start < slot_end,
                Booking.slot_end > slot_start,
            )
            .limit(1)
        )
        if conflict is not None:
            return self._conflict(calendar, day, clock, tz)

        previous_slot = _local_iso(booking.slot_start, tz)
        booking.slot_start = slot_start
        booking.slot_end = slot_end
        booking.status = str(BookingStatus.CONFIRMED)
        self.session.flush()

        return {
            "status": "rescheduled",
            "booking_id": str(booking.id),
            "patient_name": booking.patient_name,
            "clinic": calendar.name,
            "previous_slot": previous_slot,
            "new_slot_start": _local_iso(slot_start, tz),
        }

    async def transfer_to_human(self, arguments: dict[str, Any]) -> dict[str, Any]:
        reason = str(arguments.get("reason") or "").strip()
        return {
            "status": "transfer_requested",
            "reason": reason or "unspecified",
            "message": "A human agent will follow up. No outbound call was placed.",
        }

    def _active_calendar(self) -> Calendar | None:
        return self.session.scalars(
            select(Calendar).where(Calendar.is_active.is_(True)).order_by(Calendar.id)
        ).first()

    def _booked_times(self, calendar: Calendar, day: date, tz: ZoneInfo) -> set[time]:
        start, end = _day_bounds(day, tz)
        rows = self.session.scalars(
            select(Booking.slot_start).where(
                Booking.calendar_id == calendar.id,
                Booking.status == str(BookingStatus.CONFIRMED),
                Booking.slot_start >= start,
                Booking.slot_start < end,
            )
        ).all()
        return {_as_utc(value).astimezone(tz).time() for value in rows}

    def _has_conflict(self, calendar: Calendar, slot_start: datetime, slot_end: datetime) -> bool:
        existing = self.session.scalar(
            select(Booking.id)
            .where(
                Booking.calendar_id == calendar.id,
                Booking.status == str(BookingStatus.CONFIRMED),
                Booking.slot_start < slot_end,
                Booking.slot_end > slot_start,
            )
            .limit(1)
        )
        return existing is not None

    def _conflict(
        self, calendar: Calendar, day: date, clock: time, tz: ZoneInfo
    ) -> dict[str, Any]:
        booked = self._booked_times(calendar, day, tz)
        available = [
            slot for slot in _slot_times(calendar) if slot not in booked and slot > clock
        ]
        return {
            "status": "conflict",
            "message": "That slot is already booked.",
            "available": [slot.strftime("%H:%M") for slot in available[:3]],
        }


def build_tool_registry(
    session: Session,
    tools: Iterable[ToolConfig],
    *,
    call: Call | None = None,
) -> ToolRegistry:
    """Register the handlers that the agent.yaml tool list actually enables."""
    handlers = BookingTools(session, call=call).handlers()
    registry = ToolRegistry()

    for tool_config in tools:
        if not tool_config.enabled:
            continue
        handler = handlers.get(tool_config.name)
        if handler is None:
            raise ToolError(f"Tool '{tool_config.name}' has no handler in this build")
        registry.register(
            ToolSpec(
                name=tool_config.name,
                description=tool_config.description,
                parameters=tool_config.parameters or {"type": "object"},
                handler=handler,
            )
        )

    return registry
