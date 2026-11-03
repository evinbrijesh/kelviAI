from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IncomingCall:
    call_sid: str
    caller_phone: str
    channel: str = "telephony"
    metadata: dict[str, Any] = field(default_factory=dict)


class TelephonyProvider(ABC):
    """Abstract interface for telephony platforms (Twilio, Exotel, or generic webhooks)."""

    @abstractmethod
    def parse_incoming_call(self, payload: dict[str, Any]) -> IncomingCall:
        """Parse platform-specific webhook payload into a normalized IncomingCall."""

    @abstractmethod
    def format_response(
        self,
        text_message: str,
        *,
        audio_url: str | None = None,
        listen_for_input: bool = True,
        action_url: str | None = None,
    ) -> str | dict[str, Any]:
        """Format an outbound response payload or markup (e.g. TwiML)."""
