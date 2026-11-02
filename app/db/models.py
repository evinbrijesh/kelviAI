from datetime import UTC, datetime, time
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class CallStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TRANSFERRED = "transferred"


class BookingStatus(StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class EventType(StrEnum):
    CALL_STARTED = "call_started"
    DATE_RESOLVED = "date_resolved"
    USER_TURN = "user_turn"
    AGENT_TURN = "agent_turn"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    CALL_ENDED = "call_ended"
    ERROR = "error"


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_sid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    caller_phone: Mapped[str] = mapped_column(String(24))
    language: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16), default="simulation")
    status: Mapped[str] = mapped_column(String(20), default=CallStatus.IN_PROGRESS)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    events: Mapped[list["CallEvent"]] = relationship(
        back_populates="call",
        cascade="all, delete-orphan",
        order_by="CallEvent.seq",
    )
    bookings: Mapped[list["Booking"]] = relationship(back_populates="call")


class CallEvent(Base):
    __tablename__ = "call_events"
    __table_args__ = (UniqueConstraint("call_id", "seq", name="uq_call_events_call_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(24))
    tool_name: Mapped[str | None] = mapped_column(String(64), default=None)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    call: Mapped[Call] = relationship(back_populates="events")


class Calendar(Base):
    __tablename__ = "calendars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(40), default="Asia/Kolkata")
    slot_minutes: Mapped[int] = mapped_column(Integer, default=30)
    open_time: Mapped[time] = mapped_column(Time, default=time(9, 0))
    close_time: Mapped[time] = mapped_column(Time, default=time(17, 0))
    working_days: Mapped[str] = mapped_column(String(24), default="0,1,2,3,4")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="calendar")


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        Index(
            "uq_bookings_confirmed_slot",
            "calendar_id",
            "slot_start",
            unique=True,
            postgresql_where=text("status = 'confirmed'"),
            sqlite_where=text("status = 'confirmed'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calendar_id: Mapped[int] = mapped_column(ForeignKey("calendars.id"), index=True)
    call_id: Mapped[int | None] = mapped_column(
        ForeignKey("calls.id", ondelete="SET NULL"), default=None, index=True
    )
    patient_name: Mapped[str] = mapped_column(String(120))
    caller_phone: Mapped[str] = mapped_column(String(24))
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default=BookingStatus.CONFIRMED)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    calendar: Mapped[Calendar] = relationship(back_populates="bookings")
    call: Mapped[Call | None] = relationship(back_populates="bookings")
