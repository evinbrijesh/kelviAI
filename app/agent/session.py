import logging
import re
from datetime import date, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.calls.session_log import CallSessionLog, invoke_tool, start_call
from app.config import AppConfig
from app.db.models import Call, CallStatus, EventType
from app.llm.interfaces import DateTimeResolver
from app.tools.booking import build_tool_registry
from app.tools.registry import ToolError, ToolRegistry

logger = logging.getLogger(__name__)


class AgentState(str, Enum):
    IDLE = "idle"
    GREETED = "greeted"
    AWAITING_SLOT = "awaiting_slot"
    CLARIFYING = "clarifying"
    AWAITING_NAME = "awaiting_name"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    TRANSFERRED = "transferred"


class AgentSession:
    """Conversational agent session driving appointment booking dialogues."""

    def __init__(
        self,
        session: Session,
        config: AppConfig,
        resolver: DateTimeResolver,
        *,
        call_sid: str | None = None,
        caller_phone: str = "",
        channel: str = "simulation",
        caller_name: str | None = None,
        max_clarifications: int = 2,
    ) -> None:
        self.session = session
        self.config = config
        self.resolver = resolver
        self.call_sid = call_sid or f"call-{uuid4().hex[:12]}"
        self.caller_phone = caller_phone
        self.channel = channel
        self.caller_name = caller_name
        self.max_clarifications = max_clarifications

        self.state: AgentState = AgentState.IDLE
        self.clarification_count: int = 0
        self.resolved_date: date | None = None
        self.requested_time: str | None = None
        self.chosen_date: date | None = None
        self.chosen_time: str | None = None
        self.clinic_name: str = "the clinic"
        self.booking_id: str | None = None
        self.booking_result: dict[str, Any] | None = None

        self.call_log: CallSessionLog | None = None
        self.tools: ToolRegistry | None = None
        self._enabled_tools: set[str] = {
            tool.name for tool in config.tools if tool.enabled
        }

    @property
    def call(self) -> Call:
        if self.call_log is None:
            raise RuntimeError("AgentSession has not been started yet")
        return self.call_log.call

    def start(self, *, emit_greeting: bool = True) -> str:
        """Initialize the call in the database, optionally record greeting, and set ready state."""
        self.call_log = start_call(
            self.session,
            call_sid=self.call_sid,
            caller_phone=self.caller_phone,
            language=self.config.agent.language,
            channel=self.channel,
        )
        self.tools = build_tool_registry(
            self.session, self.config.tools, call=self.call_log.call
        )

        greeting = self.config.agent.greeting
        if emit_greeting:
            self.call_log.agent_turn(greeting)
        self.state = AgentState.AWAITING_SLOT
        return greeting

    async def process_turn(self, user_utterance: str) -> str:
        """Process one conversational turn from the user and return the agent's reply."""
        if self.state in (AgentState.COMPLETED, AgentState.FAILED, AgentState.TRANSFERRED):
            return "This call has already concluded."

        if self.call_log is None or self.tools is None:
            self.start()
            assert self.call_log is not None and self.tools is not None

        language = self.config.agent.language
        self.call_log.user_turn(user_utterance, language=language)

        if self.state in (AgentState.AWAITING_SLOT, AgentState.CLARIFYING):
            return await self._handle_slot_request(user_utterance)

        if self.state == AgentState.AWAITING_NAME:
            return await self._handle_name_step(user_utterance)

        if self.state == AgentState.AWAITING_CONFIRMATION:
            return await self._handle_confirmation_step(user_utterance)

        return await self._transfer("unsupported_state")

    def hangup(self, reason: str = "Caller hung up before completing the request.") -> str:
        """End an in-progress call when the caller disconnects."""
        if self.state in (AgentState.COMPLETED, AgentState.FAILED, AgentState.TRANSFERRED):
            return "This call has already concluded."
        assert self.call_log is not None
        self._finish(CallStatus.FAILED, reason, "abandoned")
        self.state = AgentState.FAILED
        return reason

    async def _handle_slot_request(self, user_utterance: str) -> str:
        assert self.call_log is not None
        resolution = await self.resolver.resolve(
            user_utterance, language=self.config.agent.language
        )
        logger.info(
            "Resolved utterance to date=%s time=%s confidence=%.2f (%s)",
            resolution.date,
            resolution.time,
            resolution.confidence,
            resolution.explanation,
        )

        # Low-confidence or unparseable input: offer clarification
        if (
            resolution.date is None
            or resolution.time is None
            or resolution.confidence < 0.60
        ):
            if self.clarification_count < self.max_clarifications:
                self.clarification_count += 1
                self.state = AgentState.CLARIFYING
                reply = (
                    "ക്ഷമിക്കണം, ഏത് തീയതിയും സമയവുമാണ് ഉദ്ദേശിച്ചത് എന്ന് വ്യക്തമാക്കാമോ?"
                    if self.config.agent.language == "malayalam"
                    else "Sorry, could you please clarify which date and time you prefer?"
                )
                self.call_log.agent_turn(reply)
                return reply

            self.call_log.error(
                "date_unresolved",
                confidence=resolution.confidence,
                explanation=resolution.explanation,
            )
            msg = "The caller's date and time could not be understood."
            self._finish(CallStatus.FAILED, msg, "unresolved")
            self.state = AgentState.FAILED
            reply = (
                "ക്ഷമിക്കണം, സമയം മനസ്സിലാക്കാൻ കഴിഞ്ഞില്ല. ഒരു ഹ്യൂമൻ അസിസ്റ്റന്റിലേക്ക് മാറ്റാം."
                if self.config.agent.language == "malayalam"
                else (
                    "Sorry, I could not understand the requested date and time. "
                    "Transferring to an assistant."
                )
            )
            self.call_log.agent_turn(reply)
            return reply

        self.resolved_date = resolution.date
        self.requested_time = resolution.time.strftime("%H:%M")

        self.call_log.record(
            EventType.DATE_RESOLVED,
            {
                "date": resolution.date.isoformat(),
                "time": self.requested_time,
                "timezone": resolution.timezone,
                "confidence": resolution.confidence,
                "explanation": resolution.explanation,
            },
        )

        day, availability = await self._find_open_day(resolution.date)
        if day is None:
            message = str(
                availability.get("message")
                or "No open clinic day was found in the next week."
            )
            self.call_log.agent_turn(message)
            self._finish(CallStatus.FAILED, message, "no_availability")
            self.state = AgentState.FAILED
            return message

        slots = [str(s) for s in availability.get("available") or []]
        if not slots:
            message = f"All appointments are taken on {day.isoformat()}."
            self.call_log.agent_turn(message)
            self._finish(CallStatus.FAILED, message, "no_availability")
            self.state = AgentState.FAILED
            return message

        chosen = self._nearest_slot(slots, self.requested_time)
        self.chosen_date = day
        self.chosen_time = chosen
        self.clinic_name = str(availability.get("clinic") or "the clinic")

        # Check if caller name is already embedded in user utterance
        extracted_name = self._extract_name(user_utterance)
        if extracted_name:
            self.caller_name = extracted_name

        if self.caller_name:
            self.state = AgentState.AWAITING_CONFIRMATION
            reply = (
                f"Confirming {self.caller_name}, {day.isoformat()} at {chosen}, "
                f"{self.clinic_name}. Shall I book it?"
            )
        else:
            self.state = AgentState.AWAITING_NAME
            if chosen == self.requested_time:
                reply = f"{day.isoformat()} at {self.requested_time} is available."
            else:
                reply = (
                    f"{day.isoformat()} at {self.requested_time} is taken; "
                    f"the nearest open slot is {chosen}."
                )

        self.call_log.agent_turn(reply)
        return reply

    async def _handle_name_step(self, user_utterance: str) -> str:
        assert self.call_log is not None
        assert self.chosen_date is not None and self.chosen_time is not None

        extracted = self._extract_name(user_utterance)
        if extracted:
            self.caller_name = extracted
        elif not self.caller_name:
            self.caller_name = user_utterance.strip().split(".")[0]

        self.state = AgentState.AWAITING_CONFIRMATION
        reply = (
            f"Confirming {self.caller_name}, {self.chosen_date.isoformat()} at {self.chosen_time}, "
            f"{self.clinic_name}. Shall I book it?"
        )
        self.call_log.agent_turn(reply)
        return reply

    async def _handle_confirmation_step(self, user_utterance: str) -> str:
        assert self.call_log is not None
        # Check if caller name was provided here
        if not self.caller_name:
            extracted = self._extract_name(user_utterance)
            if extracted:
                self.caller_name = extracted

        if self._is_positive_confirmation(user_utterance) or "book" in user_utterance.lower():
            return await self._execute_booking()

        # If caller rejects or asks for changes
        reply = "Booking was not confirmed. Would you like to check a different date or time?"
        self.state = AgentState.AWAITING_SLOT
        self.call_log.agent_turn(reply)
        return reply

    async def _execute_booking(self) -> str:
        assert self.call_log is not None and self.tools is not None
        assert self.chosen_date is not None and self.chosen_time is not None
        name = self.caller_name or "Valued Patient"

        booking = await self._safe_invoke_tool(
            "book_slot",
            {
                "caller_name": name,
                "date": self.chosen_date.isoformat(),
                "time": self.chosen_time,
            },
        )

        if booking.get("status") != "confirmed":
            message = f"The booking could not be confirmed ({booking.get('status')})."
            self.call_log.agent_turn(message)
            self._finish(CallStatus.FAILED, message, "booking_failed")
            self.state = AgentState.FAILED
            return message

        self.booking_id = str(booking.get("booking_id"))
        self.booking_result = booking
        summary = (
            f"{name} booked an appointment at {self.clinic_name} on "
            f"{booking.get('slot_start')} (reference {self.booking_id})."
        )
        reply = (
            f"{name}, an appointment at {self.clinic_name} has been booked on "
            f"{booking.get('slot_start')} (reference {self.booking_id}). Thank you!"
        )
        self._finish(CallStatus.COMPLETED, summary, "booked")
        self.state = AgentState.COMPLETED
        return reply

    async def _transfer(self, reason: str) -> str:
        assert self.call_log is not None
        if "transfer_to_human" in self._enabled_tools:
            await self._safe_invoke_tool("transfer_to_human", {"reason": reason})
        message = "Transferring to a human operator."
        self.call_log.agent_turn(message)
        self._finish(CallStatus.TRANSFERRED, message, "transferred")
        self.state = AgentState.TRANSFERRED
        return message

    async def _safe_invoke_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Invoke a tool only if enabled in agent.yaml configuration."""
        if tool_name not in self._enabled_tools:
            raise ToolError(
                f"Tool '{tool_name}' is not declared or enabled in agent.yaml"
            )
        assert self.tools is not None and self.call_log is not None
        return await invoke_tool(self.tools, self.call_log, tool_name, arguments)

    async def _find_open_day(
        self, start_day: date
    ) -> tuple[date | None, dict[str, Any]]:
        day = start_day
        result: dict[str, Any] = {}
        for _ in range(7):
            result = await self._safe_invoke_tool(
                "check_availability", {"date": day.isoformat()}
            )
            status = result.get("status")
            if status == "ok":
                return day, result
            if status != "closed":
                logger.warning("Availability check returned %s", status)
                return None, result
            assert self.call_log is not None
            self.call_log.agent_turn(
                f"The clinic is closed on {day.isoformat()}; checking the next day."
            )
            day += timedelta(days=1)
        return None, result

    def _nearest_slot(self, slots: list[str], requested: str) -> str:
        if requested in slots:
            return requested
        later = [slot for slot in slots if slot > requested]
        return later[0] if later else slots[0]

    def _extract_name(self, text: str) -> str | None:
        patterns = [
            r"(?:എന്റെ\s+പേര്|പേര്|name\s+is|I am|this is)\s*[:=]?\s*([A-Za-z\u0D00-\u0D7F\s]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                # Stop at sentence boundary
                candidate = re.split(r"[.,\n;]", candidate)[0].strip()
                if len(candidate) >= 2:
                    return candidate
        return None

    def _is_positive_confirmation(self, text: str) -> bool:
        keywords = [
            "അതെ",
            "ശരി",
            "ശരിയാണ്",
            "ബുക്ക്",
            "ബുക്ക് ചെയ്യാം",
            "യെസ്",
            "yes",
            "confirm",
            "ok",
            "okay",
            "sure",
        ]
        text_lower = text.lower()
        return any(k in text_lower for k in keywords)

    def _finish(self, status: CallStatus, summary: str, outcome: str) -> None:
        assert self.call_log is not None
        self.call_log.finish(status, summary, outcome)
        logger.info(
            "Call %s ended: %s (%s)", self.call_log.call.call_sid, outcome, status
        )
