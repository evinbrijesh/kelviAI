from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

import secrets

from app.admin.schemas import (
    AdminIndex,
    AdminStatus,
    BookingSummary,
    CallDetail,
    CallEventDetail,
    CallSummary,
    ConfiguredTool,
    ResolvedDateTime,
)
from app.config import AppConfig, Settings
from app.db.models import Booking, Call, CallEvent, Calendar, EventType
from app.privacy import mask_phone


def verify_admin_access(request: Request) -> None:
    settings = Settings()
    if not settings.admin_api_key:
        return
    provided = request.headers.get("X-Admin-Key") or request.query_params.get("api_key")
    if not provided or not secrets.compare_digest(provided, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin access requires a valid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_admin_access)])


ENVIRONMENT = "non-production"
RECORDINGS = "disabled"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def get_session(request: Request) -> Iterator[Session]:
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not initialised",
        )
    with session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _call_summary(call: Call, outcome: str | None, booking_count: int) -> CallSummary:
    return CallSummary(
        id=call.id,
        call_sid=call.call_sid,
        caller_phone=mask_phone(call.caller_phone),
        language=call.language,
        channel=call.channel,
        status=call.status,
        outcome=outcome,
        booking_count=booking_count,
        started_at=_utc(call.started_at),
        ended_at=_utc(call.ended_at) if call.ended_at else None,
        summary=call.summary,
    )


def _booking_summary(booking: Booking) -> BookingSummary:
    return BookingSummary(
        id=booking.id,
        calendar_id=booking.calendar_id,
        clinic=booking.calendar.name,
        call_id=booking.call.id if booking.call else None,
        call_sid=booking.call.call_sid if booking.call else None,
        patient_name=booking.patient_name,
        caller_phone=mask_phone(booking.caller_phone),
        slot_start=_utc(booking.slot_start),
        slot_end=_utc(booking.slot_end),
        status=booking.status,
        notes=booking.notes,
    )


def _event_detail(event: CallEvent) -> CallEventDetail:
    return CallEventDetail(
        seq=event.seq,
        event_type=event.event_type,
        tool_name=event.tool_name,
        payload=event.payload,
        latency_ms=event.latency_ms,
        created_at=_utc(event.created_at),
    )


def _outcome(event: CallEvent) -> str | None:
    value = event.payload.get("outcome")
    return str(value) if value else None


def _call_outcome(events: Sequence[CallEvent]) -> str | None:
    for event in reversed(events):
        if event.event_type == str(EventType.CALL_ENDED):
            return _outcome(event)
    return None


def _outcomes(session: Session, call_ids: Sequence[int]) -> dict[int, str]:
    if not call_ids:
        return {}

    events = session.scalars(
        select(CallEvent).where(
            CallEvent.call_id.in_(call_ids),
            CallEvent.event_type == str(EventType.CALL_ENDED),
        )
    ).all()
    return {
        event.call_id: outcome
        for event in events
        if (outcome := _outcome(event)) is not None
    }


def _resolved(events: Sequence[CallEvent]) -> ResolvedDateTime | None:
    for event in reversed(events):
        if event.event_type != str(EventType.DATE_RESOLVED):
            continue
        payload: dict[str, Any] = event.payload
        return ResolvedDateTime(
            date=str(payload.get("date") or ""),
            time=str(payload.get("time") or ""),
            timezone=str(payload.get("timezone") or "Asia/Kolkata"),
            confidence=float(payload.get("confidence") or 0.0),
            explanation=str(payload.get("explanation") or ""),
        )
    return None


@router.get("", response_model=AdminIndex)
def admin_index() -> AdminIndex:
    return AdminIndex(
        environment=ENVIRONMENT,
        notice="VaaniKit demo admin API. Synthetic data only; not production secure.",
        endpoints=[
            "/admin/ui",
            "/admin/calls",
            "/admin/calls/{id}",
            "/admin/bookings",
            "/admin/status",
            "/admin/tools",
        ],
    )


@router.get("/ui", include_in_schema=False)
def admin_ui() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html", media_type="text/html")


@router.get("/calls", response_model=list[CallSummary])
def list_calls(
    session: SessionDep, limit: int = Query(default=50, ge=1, le=200)
) -> list[CallSummary]:
    rows = session.execute(
        select(Call, func.count(Booking.id))
        .outerjoin(Booking, Booking.call_id == Call.id)
        .group_by(Call.id)
        .order_by(Call.started_at.desc(), Call.id.desc())
        .limit(limit)
    ).all()
    outcomes = _outcomes(session, [call.id for call, _ in rows])
    return [
        _call_summary(call, outcomes.get(call.id), booking_count)
        for call, booking_count in rows
    ]


@router.get("/calls/{call_id}", response_model=CallDetail)
def get_call(call_id: int, session: SessionDep) -> CallDetail:
    call = session.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    events = sorted(call.events, key=lambda event: event.seq)
    bookings = sorted(call.bookings, key=lambda booking: booking.slot_start)
    summary = _call_summary(call, _call_outcome(events), len(bookings))

    return CallDetail(
        **summary.model_dump(),
        resolved=_resolved(events),
        bookings=[_booking_summary(booking) for booking in bookings],
        events=[_event_detail(event) for event in events],
    )


@router.get("/bookings", response_model=list[BookingSummary])
def list_bookings(
    session: SessionDep, limit: int = Query(default=50, ge=1, le=200)
) -> list[BookingSummary]:
    bookings = session.scalars(
        select(Booking)
        .options(joinedload(Booking.calendar), joinedload(Booking.call))
        .order_by(Booking.slot_start)
        .limit(limit)
    ).all()
    return [_booking_summary(booking) for booking in bookings]


@router.get("/status", response_model=AdminStatus)
def admin_status(session: SessionDep) -> AdminStatus:
    calls = session.scalar(select(func.count()).select_from(Call)) or 0
    bookings = session.scalar(select(func.count()).select_from(Booking)) or 0
    calendars = session.scalar(select(func.count()).select_from(Calendar)) or 0
    return AdminStatus(
        environment=ENVIRONMENT,
        calls=calls,
        bookings=bookings,
        calendars=calendars,
        phone_masking="enabled",
        recordings=RECORDINGS,
    )


@router.get("/tools", response_model=list[ConfiguredTool])
def list_configured_tools(request: Request) -> list[ConfiguredTool]:
    config: AppConfig | None = getattr(request.app.state, "config", None)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent configuration is not loaded",
        )
    return [
        ConfiguredTool(
            name=tool.name,
            description=tool.description,
            enabled=tool.enabled,
            parameters=tool.parameters,
        )
        for tool in config.tools
    ]
