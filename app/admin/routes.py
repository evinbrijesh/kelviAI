from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.schemas import (
    AdminIndex,
    AdminStatus,
    BookingSummary,
    CallSummary,
    ConfiguredTool,
)
from app.config import AppConfig
from app.db.models import Booking, Call, Calendar
from app.privacy import mask_phone

router = APIRouter(prefix="/admin", tags=["admin"])

ENVIRONMENT = "non-production"


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


@router.get("", response_model=AdminIndex)
def admin_index() -> AdminIndex:
    return AdminIndex(
        environment=ENVIRONMENT,
        notice="VaaniKit demo admin API. Synthetic data only; not production secure.",
        endpoints=["/admin/calls", "/admin/bookings", "/admin/status", "/admin/tools"],
    )


@router.get("/calls", response_model=list[CallSummary])
def list_calls(session: SessionDep, limit: int = Query(default=50, ge=1, le=200)) -> list[CallSummary]:
    calls = session.scalars(select(Call).order_by(Call.started_at.desc()).limit(limit)).all()
    return [
        CallSummary(
            id=call.id,
            call_sid=call.call_sid,
            caller_phone=mask_phone(call.caller_phone),
            language=call.language,
            channel=call.channel,
            status=call.status,
            started_at=call.started_at,
            ended_at=call.ended_at,
            summary=call.summary,
        )
        for call in calls
    ]


@router.get("/bookings", response_model=list[BookingSummary])
def list_bookings(
    session: SessionDep, limit: int = Query(default=50, ge=1, le=200)
) -> list[BookingSummary]:
    bookings = session.scalars(select(Booking).order_by(Booking.slot_start).limit(limit)).all()
    return [
        BookingSummary(
            id=booking.id,
            calendar_id=booking.calendar_id,
            patient_name=booking.patient_name,
            caller_phone=mask_phone(booking.caller_phone),
            slot_start=booking.slot_start,
            slot_end=booking.slot_end,
            status=booking.status,
            notes=booking.notes,
        )
        for booking in bookings
    ]


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
