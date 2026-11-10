from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class XRayEvent:
    event_type: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class XRayTrace:
    turn_id: str
    events: list[XRayEvent] = field(default_factory=list)
    start_time: float = field(default_factory=lambda: datetime.now(UTC).timestamp())
    end_time: float | None = None
    total_latency_ms: float = 0.0

    def add_event(self, event_type: str, **kwargs: Any) -> XRayEvent:
        event = XRayEvent(event_type=event_type, data=kwargs)
        self.events.append(event)
        return event

    def finish(self) -> "XRayTrace":
        now = datetime.now(UTC).timestamp()
        self.end_time = now
        self.total_latency_ms = round((now - self.start_time) * 1000, 2)
        return self

    def summary(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "latency_ms": self.total_latency_ms,
            "events": [asdict(ev) for ev in self.events],
        }
