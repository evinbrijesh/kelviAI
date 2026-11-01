from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CallSummary(BaseModel):
    id: int
    call_sid: str
    caller_phone: str
    language: str
    channel: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    summary: str | None


class BookingSummary(BaseModel):
    id: int
    calendar_id: int
    patient_name: str
    caller_phone: str
    slot_start: datetime
    slot_end: datetime
    status: str
    notes: str | None


class AdminStatus(BaseModel):
    environment: str
    calls: int
    bookings: int
    calendars: int
    phone_masking: str


class ConfiguredTool(BaseModel):
    name: str
    description: str
    enabled: bool
    parameters: dict[str, Any]


class AdminIndex(BaseModel):
    environment: str
    notice: str
    endpoints: list[str]
