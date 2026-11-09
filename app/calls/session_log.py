from collections.abc import Mapping
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Call, CallEvent, CallStatus, EventType, utcnow
from app.tools.registry import ToolError, ToolRegistry


class CallSessionLog:
    """Writes the chronological event log for one call in the caller's transaction."""

    def __init__(self, session: Session, call: Call) -> None:
        self.session = session
        self.call = call
        self._seq = 0

    @property
    def recorded_events(self) -> int:
        return self._seq

    def record(
        self,
        event_type: EventType,
        payload: Mapping[str, Any] | None = None,
        *,
        tool_name: str | None = None,
        latency_ms: int | None = None,
    ) -> CallEvent:
        self.session.add(self.call)
        self._seq += 1
        event = CallEvent(
            call_id=self.call.id,
            seq=self._seq,
            event_type=str(event_type),
            tool_name=tool_name,
            payload=dict(payload or {}),
            latency_ms=latency_ms,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def user_turn(self, text: str, *, language: str | None = None) -> CallEvent:
        from app.llm.transliteration import transliterate_indic

        payload: dict[str, Any] = {"text": text}
        translit = transliterate_indic(text, language)
        if translit and translit != text:
            payload["transliteration"] = translit
        if language:
            payload["language"] = language
        return self.record(EventType.USER_TURN, payload)

    def agent_turn(self, text: str, *, language: str | None = None) -> CallEvent:
        from app.llm.transliteration import transliterate_indic

        payload: dict[str, Any] = {"text": text}
        lang = language or getattr(self.call, "language", None)
        translit = transliterate_indic(text, lang)
        if translit and translit != text:
            payload["transliteration"] = translit
        return self.record(EventType.AGENT_TURN, payload)

    def tool_call(self, tool_name: str, arguments: Mapping[str, Any]) -> CallEvent:
        return self.record(
            EventType.TOOL_CALL,
            {"arguments": dict(arguments)},
            tool_name=tool_name,
        )

    def tool_result(
        self,
        tool_name: str,
        result: Mapping[str, Any],
        *,
        latency_ms: int | None = None,
    ) -> CallEvent:
        return self.record(
            EventType.TOOL_RESULT,
            dict(result),
            tool_name=tool_name,
            latency_ms=latency_ms,
        )

    def error(self, reason: str, **details: Any) -> CallEvent:
        return self.record(EventType.ERROR, {"reason": reason, **details})

    def finish(self, status: CallStatus, summary: str, outcome: str) -> None:
        self.session.add(self.call)
        self.call.status = str(status)
        self.call.ended_at = utcnow()
        self.call.summary = summary
        self.record(EventType.CALL_ENDED, {"outcome": outcome})
        self.session.flush()


def start_call(
    session: Session,
    *,
    call_sid: str,
    caller_phone: str,
    language: str,
    channel: str = "simulation",
) -> CallSessionLog:
    call = Call(
        call_sid=call_sid,
        caller_phone=caller_phone,
        language=language,
        channel=channel,
        status=str(CallStatus.IN_PROGRESS),
    )
    session.add(call)
    session.flush()

    log = CallSessionLog(session, call)
    log.record(EventType.CALL_STARTED, {"channel": channel, "language": language})
    return log


async def invoke_tool(
    registry: ToolRegistry,
    log: CallSessionLog,
    name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Run a declared tool and record both sides of the exchange with its latency."""
    log.tool_call(name, arguments)
    started = perf_counter()
    try:
        result: Any = await registry.invoke(name, arguments)
    except ToolError as exc:
        log.error("tool_failed", tool=name, message=str(exc))
        raise

    latency_ms = int((perf_counter() - started) * 1000)
    payload: dict[str, Any] = result if isinstance(result, dict) else {"result": result}
    log.tool_result(name, payload, latency_ms=latency_ms)
    return payload
