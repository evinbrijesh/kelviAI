from typing import Any
from xml.sax.saxutils import escape

from app.providers.base import IncomingCall, TelephonyProvider


class GenericProvider(TelephonyProvider):
    """Generic JSON telephony provider for REST and webhook integrations."""

    def parse_incoming_call(self, payload: dict[str, Any]) -> IncomingCall:
        call_sid = str(payload.get("call_sid") or payload.get("id") or "call-anon")
        caller_phone = str(payload.get("caller_phone") or payload.get("from") or "")
        return IncomingCall(
            call_sid=call_sid,
            caller_phone=caller_phone,
            channel="generic",
            metadata=payload,
        )

    def format_response(
        self,
        text_message: str,
        *,
        audio_url: str | None = None,
        listen_for_input: bool = True,
        action_url: str | None = None,
    ) -> dict[str, Any]:
        return {
            "reply": text_message,
            "audio_url": audio_url,
            "listen_for_input": listen_for_input,
            "action_url": action_url,
        }


class TwilioProvider(TelephonyProvider):
    """Twilio Voice webhook provider rendering standard TwiML."""

    def parse_incoming_call(self, payload: dict[str, Any]) -> IncomingCall:
        call_sid = str(payload.get("CallSid") or payload.get("call_sid") or "call-anon")
        caller_phone = str(payload.get("From") or payload.get("caller_phone") or "")
        return IncomingCall(
            call_sid=call_sid,
            caller_phone=caller_phone,
            channel="twilio",
            metadata=payload,
        )

    def format_response(
        self,
        text_message: str,
        *,
        audio_url: str | None = None,
        listen_for_input: bool = True,
        action_url: str | None = None,
    ) -> str:
        escaped_text = escape(text_message)
        xml_parts: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>', "<Response>"]

        if audio_url:
            content = f"<Play>{escape(audio_url)}</Play>"
        else:
            content = f'<Say language="ml-IN">{escaped_text}</Say>'

        if listen_for_input and action_url:
            gather_tag = (
                f'<Gather input="speech" action="{escape(action_url)}" '
                'method="POST" speechTimeout="auto" language="ml-IN">'
            )
            xml_parts.append(gather_tag)
            xml_parts.append(f"  {content}")
            xml_parts.append("</Gather>")
        else:
            xml_parts.append(f"  {content}")
            if not listen_for_input:
                xml_parts.append("  <Hangup/>")

        xml_parts.append("</Response>")
        return "\n".join(xml_parts)
