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
    outcome: str | None
    booking_count: int
    started_at: datetime
    ended_at: datetime | None
    summary: str | None


class BookingSummary(BaseModel):
    id: int
    calendar_id: int
    clinic: str
    call_id: int | None
    call_sid: str | None
    patient_name: str
    caller_phone: str
    slot_start: datetime
    slot_end: datetime
    status: str
    notes: str | None


class CallEventDetail(BaseModel):
    seq: int
    event_type: str
    tool_name: str | None
    payload: dict[str, Any]
    latency_ms: int | None
    created_at: datetime


class ResolvedDateTime(BaseModel):
    date: str
    time: str
    timezone: str
    confidence: float
    explanation: str


class CallDetail(CallSummary):
    resolved: ResolvedDateTime | None
    bookings: list[BookingSummary]
    events: list[CallEventDetail]


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
