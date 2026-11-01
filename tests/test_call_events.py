from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calls.session_log import invoke_tool, start_call
from app.db.models import CallEvent, CallStatus, EventType
from app.db.session import Database
from app.tools.registry import ToolError, ToolRegistry


def events_for(session: Session) -> list[CallEvent]:
    return list(session.scalars(select(CallEvent).order_by(CallEvent.seq)).all())


def echo_registry() -> ToolRegistry:
    registry = ToolRegistry()

    @registry.tool(name="echo", description="Echo the text")
    async def echo(args: dict[str, Any]) -> dict[str, Any]:
        return {"echo": args["text"]}

    return registry


@pytest.mark.asyncio
async def test_start_call_records_the_first_event(database: Database) -> None:
    with database.session() as session:
        log = start_call(
            session,
            call_sid="call-1",
            caller_phone="+919000000001",
            language="malayalam",
        )

        events = events_for(session)
        assert log.call.id is not None
        assert [event.event_type for event in events] == [str(EventType.CALL_STARTED)]
        assert events[0].payload == {"channel": "simulation", "language": "malayalam"}
        assert events[0].seq == 1


@pytest.mark.asyncio
async def test_event_sequence_is_contiguous(database: Database) -> None:
    with database.session() as session:
        log = start_call(
            session,
            call_sid="call-2",
            caller_phone="+919000000002",
            language="malayalam",
        )
        log.user_turn("നാളെ രാവിലെ പത്ത് മണി", language="malayalam")
        log.agent_turn("ഞാൻ പരിശോധിക്കട്ടെ")
        log.error("date_unresolved", confidence=0.0)

        assert [event.seq for event in events_for(session)] == [1, 2, 3, 4]
        assert log.recorded_events == 4


@pytest.mark.asyncio
async def test_tool_invocation_records_call_and_result(database: Database) -> None:
    with database.session() as session:
        log = start_call(
            session,
            call_sid="call-3",
            caller_phone="+919000000003",
            language="malayalam",
        )

        result = await invoke_tool(echo_registry(), log, "echo", {"text": "namaskaram"})

        assert result == {"echo": "namaskaram"}
        events = events_for(session)
        assert [event.event_type for event in events] == [
            str(EventType.CALL_STARTED),
            str(EventType.TOOL_CALL),
            str(EventType.TOOL_RESULT),
        ]
        assert events[1].tool_name == "echo"
        assert events[1].payload == {"arguments": {"text": "namaskaram"}}
        assert events[2].tool_name == "echo"
        assert events[2].payload == {"echo": "namaskaram"}
        assert events[2].latency_ms is not None


@pytest.mark.asyncio
async def test_tool_failure_is_recorded_before_reraising(database: Database) -> None:
    registry = ToolRegistry()

    @registry.tool(name="explode", description="Always fails")
    async def explode(args: dict[str, Any]) -> dict[str, Any]:
        raise ToolError("boom")

    with database.session() as session:
        log = start_call(
            session,
            call_sid="call-4",
            caller_phone="+919000000004",
            language="malayalam",
        )

        with pytest.raises(ToolError, match="boom"):
            await invoke_tool(registry, log, "explode", {})

        events = events_for(session)
        assert [event.event_type for event in events] == [
            str(EventType.CALL_STARTED),
            str(EventType.TOOL_CALL),
            str(EventType.ERROR),
        ]
        assert events[2].payload["reason"] == "tool_failed"
        assert events[2].payload["tool"] == "explode"


@pytest.mark.asyncio
async def test_finish_closes_the_call(database: Database) -> None:
    with database.session() as session:
        log = start_call(
            session,
            call_sid="call-5",
            caller_phone="+919000000005",
            language="malayalam",
        )

        log.finish(CallStatus.COMPLETED, "Rangith booked 10:00.", "booked")

        assert log.call.status == "completed"
        assert log.call.ended_at is not None
        assert log.call.summary == "Rangith booked 10:00."
        assert events_for(session)[-1].payload == {"outcome": "booked"}
