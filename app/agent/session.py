import logging
import re
from datetime import date, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.agent.replies import ReplyTemplates, templates_for
from app.calls.session_log import CallSessionLog, invoke_tool, start_call
from app.config import AppConfig
from app.db.models import Call, CallStatus, EventType
from app.llm.interfaces import DateTimeResolver
from app.llm.language import detect_language, normalize_language, resolve_language
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
    AWAITING_CANCELLATION = "awaiting_cancellation"
    AWAITING_RESCHEDULE = "awaiting_reschedule"
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

        self.language: str = resolve_language(
            hint=config.agent.language, default=config.model.stt.language
        )
        self.templates: ReplyTemplates = templates_for(self.language)
        self._language_locked = False

        self.state: AgentState = AgentState.IDLE
        self.clarification_count: int = 0
        self.resolved_date: date | None = None
        self.requested_time: str | None = None
        self.chosen_date: date | None = None
        self.chosen_time: str | None = None
        self.clinic_name: str = "the clinic"
        self.booking_id: str | None = None
        self.booking_result: dict[str, Any] | None = None
        self.reschedule_ref: str | None = None
        self.last_resolved: dict[str, Any] | None = None
        self.last_tool_invoked: dict[str, Any] | None = None

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
            language=self.language,
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

    async def process_turn(
        self, user_utterance: str, language: str | None = None
    ) -> str:
        """Process one conversational turn from the user and return the agent's reply."""
        if self.state in (AgentState.COMPLETED, AgentState.FAILED, AgentState.TRANSFERRED):
            return self._t("concluded")

        if self.call_log is None or self.tools is None:
            self.start()
            assert self.call_log is not None and self.tools is not None

        self._set_language(user_utterance, language)
        self.call_log.user_turn(user_utterance, language=self.language)

        if self.state in (AgentState.AWAITING_SLOT, AgentState.CLARIFYING):
            if self._is_cancellation_intent(user_utterance):
                return await self._handle_cancellation_step(user_utterance)
            if self._is_reschedule_intent(user_utterance):
                return await self._handle_reschedule_step(user_utterance)
            return await self._handle_slot_request(user_utterance)

        if self.state == AgentState.AWAITING_CANCELLATION:
            return await self._handle_cancellation_step(user_utterance)

        if self.state == AgentState.AWAITING_RESCHEDULE:
            return await self._handle_reschedule_step(user_utterance)

        if self.state == AgentState.AWAITING_NAME:
            return await self._handle_name_step(user_utterance)

        if self.state == AgentState.AWAITING_CONFIRMATION:
            return await self._handle_confirmation_step(user_utterance)

        return await self._transfer("unsupported_state")

    def message(self, key: str, **kwargs: Any) -> str:
        """Return a localized caller-facing message by template key."""
        return self._t(key, **kwargs)

    def _t(self, key: str, **kwargs: Any) -> str:
        template: str = getattr(self.templates, key)
        return template.format(**kwargs) if kwargs else template

    def _set_language(self, text: str, hint: str | None = None) -> None:
        hinted = normalize_language(hint)
        detected = hinted or (
            detect_language(text)
            if not self._language_locked
            and self.state in (AgentState.AWAITING_SLOT, AgentState.CLARIFYING)
            else None
        )
        if detected is None:
            return
        self.language = detected
        self.templates = templates_for(detected)
        self._language_locked = True
        if self.call_log is not None:
            self.session.add(self.call_log.call)
            self.call_log.call.language = detected

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
            user_utterance, language=self.language
        )
        logger.info(
            "Resolved utterance to date=%s time=%s confidence=%.2f (%s)",
            resolution.date,
            resolution.time,
            resolution.confidence,
            resolution.explanation,
        )
        if resolution.date is not None or resolution.time is not None:
            self.last_resolved = {
                "date": resolution.date.isoformat() if resolution.date else None,
                "time": resolution.time.strftime("%H:%M") if resolution.time else None,
                "confidence": round(resolution.confidence, 2),
                "explanation": resolution.explanation,
            }

        # Low-confidence or unparseable input: offer clarification
        if (
            resolution.date is None
            or resolution.time is None
            or resolution.confidence < 0.60
        ):
            if self.clarification_count < self.max_clarifications:
                self.clarification_count += 1
                self.state = AgentState.CLARIFYING
                reply = self._t("clarification")
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
            reply = self._t("unresolved")
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
            message = self._t("no_open_day")
            self.call_log.agent_turn(message)
            self._finish(CallStatus.FAILED, message, "no_availability")
            self.state = AgentState.FAILED
            return message

        slots = [str(s) for s in availability.get("available") or []]
        if not slots:
            message = self._t("all_taken", date=day.isoformat())
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
            reply = self._t(
                "confirming",
                name=self.caller_name,
                date=day.isoformat(),
                time=chosen,
                clinic=self.clinic_name,
            )
        else:
            self.state = AgentState.AWAITING_NAME
            if chosen == self.requested_time:
                reply = self._t(
                    "available", date=day.isoformat(), time=self.requested_time
                )
            else:
                reply = self._t(
                    "nearest",
                    date=day.isoformat(),
                    time=self.requested_time,
                    slot=chosen,
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
            if self._is_positive_confirmation(user_utterance):
                # Caller accepted the suggested slot, but has not provided their name yet
                reply = self._t("ask_name")
                self.call_log.agent_turn(reply)
                return reply

            clean_candidate = user_utterance.strip().split(".")[0].strip()
            if (
                len(clean_candidate) >= 2
                and not self._is_positive_confirmation(clean_candidate)
                and not clean_candidate.isdigit()
            ):
                self.caller_name = clean_candidate
            else:
                reply = self._t("ask_name")
                self.call_log.agent_turn(reply)
                return reply

        self.state = AgentState.AWAITING_CONFIRMATION
        reply = self._t(
            "confirming",
            name=self.caller_name,
            date=self.chosen_date.isoformat(),
            time=self.chosen_time,
            clinic=self.clinic_name,
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

        if self._is_positive_confirmation(user_utterance):
            return await self._execute_booking()

        # If caller rejects or asks for changes
        reply = self._t("rejected")
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
            message = self._t("booking_failed", status=booking.get("status"))
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
        reply = self._t(
            "booked",
            name=name,
            clinic=self.clinic_name,
            slot=booking.get("slot_start"),
            reference=self.booking_id,
        )
        self._finish(CallStatus.COMPLETED, summary, "booked")
        self.state = AgentState.COMPLETED
        return reply

    async def _transfer(self, reason: str) -> str:
        assert self.call_log is not None
        if "transfer_to_human" in self._enabled_tools:
            await self._safe_invoke_tool("transfer_to_human", {"reason": reason})
        message = self._t("transfer")
        self.call_log.agent_turn(message)
        self._finish(
            CallStatus.TRANSFERRED, "Transferred to a human operator.", "transferred"
        )
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
        result = await invoke_tool(self.tools, self.call_log, tool_name, arguments)
        self.last_tool_invoked = {
            "name": tool_name,
            "status": result.get("status"),
            "arguments": arguments,
            "result": result,
        }
        return result

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
                self._t("closed_day", date=day.isoformat())
            )
            day += timedelta(days=1)
        return None, result

    def _nearest_slot(self, slots: list[str], requested: str) -> str:
        if requested in slots:
            return requested
        later = [slot for slot in slots if slot > requested]
        return later[0] if later else slots[0]

    def _extract_name(self, text: str) -> str | None:
        prefixes = (
            r"എന്റെ\s+പേര്",
            r"പേര്",
            r"मेरा\s+नाम",
            r"माझे\s+नाव",
            r"माझं\s+नाव",
            r"आमचे\s+नाव",
            r"नाम",
            r"नाव",
            r"আমার\s+নাম",
            r"নাম",
            r"என்\s+பெயர்",
            r"பெயர்",
            r"నా\s+పేరు",
            r"పేరు",
            r"ನನ್ನ\s+ಹೆಸರು",
            r"ಹೆಸರು",
            r"મારું\s+નામ",
            r"નામ",
            r"ਮੇਰਾ\s+ਨਾਮ",
            r"ਨਾਮ",
            r"mera\s+naam",
            r"ente\s+(?:peru|per)",
            r"en\s+peyar",
            r"amar\s+naam",
            r"name\s+is",
            r"I\s+am",
            r"this\s+is",
        )
        name_chars = (
            r"A-Za-z"
            r"\u0900-\u097F"
            r"\u0980-\u09FF"
            r"\u0A00-\u0A7F"
            r"\u0A80-\u0AFF"
            r"\u0B80-\u0BFF"
            r"\u0C00-\u0C7F"
            r"\u0C80-\u0CFF"
            r"\u0D00-\u0D7F"
        )
        pattern = (
            rf"(?<![{name_chars}])(?:{'|'.join(prefixes)})(?![{name_chars}])"
            rf"\s*[:=]?\s*([{name_chars}\s]+)"
        )
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = re.split(r"[.,\n;।॥!?]", match.group(1).strip())[0].strip()
            candidate = re.sub(
                r"(?:\s+(?:hai|he|hun|hoon|aanu|anu|ആണ്|ആണു|है|हूँ|हूं|आहे|"
                r"হয়|ஆகும்|છે|ਹੈ))+$",
                "",
                candidate,
                flags=re.IGNORECASE,
            ).strip()
            if len(candidate) >= 2:
                return candidate
        return None

    def _is_positive_confirmation(self, text: str) -> bool:
        negations = (
            "no", "not", "don't", "do not", "dont", "never", "cancel",
            "nahi", "nahin", "mat", "venda", "vendam", "illa", "illai",
            "വേണ്ട", "വേണ്ടാ", "വേണ്ടാം", "അല്ല", "ഇല്ല",
            "नहीं", "नही", "मत", "ना", "नाही", "नको", "না",
            "வேண்டாம்", "இல்லை", "వద్దు", "కాదు", "ಬೇಡ", "ಇಲ್ಲ",
            "ના", "નહીં", "ਨਹੀਂ", "ਨਾ",
        )
        text_lower = text.lower().replace("’", "'")
        boundary = r"\w\u0900-\u0D7F"
        negative_pattern = "|".join(re.escape(term) for term in negations)
        if re.search(rf"(?<![{boundary}])(?:{negative_pattern})(?![{boundary}])", text_lower):
            return False

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
            "book",
            "proceed",
            "haan",
            "han",
            "ji",
            "theek",
            "thik",
            "athe",
            "athey",
            "sheri",
            "shari",
            "aam",
            "aama",
            "aamam",
            "sari",
            "hya",
            "hyan",
            "thik ache",
            "हाँ",
            "हां",
            "जी",
            "ठीक",
            "बुक",
            "बुकिंग",
            "कर दीजिए",
            "होय",
            "हो",
            "निश्चित",
            "হ্যাঁ",
            "হাঁ",
            "ঠিক",
            "বুক",
            "নিশ্চিত",
            "ஆம்",
            "ஆமாம்",
            "சரி",
            "பதிவு",
            "உறுதி",
            "అవును",
            "సరే",
            "బుక్",
            "నిర్ధారించు",
            "ആയിക്കോട്ടെ",
            "അപ്പം മതി",
            "അപ്പോ മതി",
            "മതി",
            "ശരിയാ",
            "ശരിയാണ്",
            "ഉറപ്പിക്കാം",
            "പാക്കിക്കോ",
            "ഓക്കെ",
            "തീർച്ചയായും",
            "ആണ്",
            "ആവട്ടെ",
            "aayikkotte",
            "appam mathi",
            "mathi",
            "urappikkam",
            "sheriyaa",
            "ഹൗദു",
            "സരി",
            "ಬುಕ್",
            "ದೃಢೀಕರಿಸು",
            "હા",
            "બરાબર",
            "બુક",
            "નિશ્ચિત",
            "ਹਾਂ",
            "ਠੀਕ",
            "ਬੁੱਕ",
            "ਪੱਕੀ",
        ]
        positive_pattern = "|".join(re.escape(term) for term in keywords)
        return re.search(
            rf"(?<![{boundary}])(?:{positive_pattern})(?![{boundary}])", text_lower
        ) is not None

    def _is_cancellation_intent(self, text: str) -> bool:
        cancel_terms = (
            "റദ്ദാക്ക",
            "റദ്ദാക്കണം",
            "ക്യാൻസൽ",
            "ക്യാന്സല്",
            "cancel",
            "cancellation",
            "cancelling",
            "रद्द",
            "कैंसल",
            "कैंसिल",
        )
        text_lower = text.lower()
        return any(term in text_lower for term in cancel_terms)

    def _extract_reference(self, text: str) -> str | None:
        match = re.search(
            r"(?:റഫറൻസ്|റഫറന്സ്|reference|ref|booking|നമ്പർ|number|no\.?)\s*[:#-]?\s*(\d+)",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)
        numbers = re.findall(r"\b\d+\b", text)
        return numbers[0] if numbers else None

    async def _handle_cancellation_step(self, user_utterance: str) -> str:
        assert self.call_log is not None
        ref = self._extract_reference(user_utterance)
        if not ref:
            self.state = AgentState.AWAITING_CANCELLATION
            reply = self._t("ask_cancel_ref")
            self.call_log.agent_turn(reply)
            return reply

        result = await self._safe_invoke_tool("cancel_booking", {"booking_id": ref})
        status = result.get("status")
        if status == "cancelled":
            self.state = AgentState.COMPLETED
            summary = f"Booking #{ref} was cancelled by caller."
            reply = self._t("cancelled", clinic=self.clinic_name, reference=ref)
            self.call_log.agent_turn(reply)
            self._finish(CallStatus.COMPLETED, summary, "cancelled")
            return reply

        if status == "already_cancelled":
            self.state = AgentState.COMPLETED
            summary = f"Booking #{ref} was already cancelled."
            reply = (
                f"റഫറൻസ് {ref} ഇതിനകം റദ്ദാക്കിയതാണ്. നന്ദി!"
                if self.language.startswith("ml")
                else f"Booking #{ref} is already cancelled."
            )
            self.call_log.agent_turn(reply)
            self._finish(CallStatus.COMPLETED, summary, "already_cancelled")
            return reply

        reply = self._t("cancel_not_found")
        self.call_log.agent_turn(reply)
        return reply

    def _is_reschedule_intent(self, text: str) -> bool:
        reschedule_terms = (
            "മാറ്റണം",
            "മാറ്റാൻ",
            "മാറ്റാമോ",
            "പുതുക്കണം",
            "മാറ്റിവെക്കണം",
            "reschedule",
            "postpone",
            "prepone",
            "change appointment",
            "change time",
            "change date",
            "change slot",
            "बदलना",
            "रीशेड्यूल",
            "रीशिड्यूल",
        )
        text_lower = text.lower()
        return any(term in text_lower for term in reschedule_terms)

    async def _handle_reschedule_step(self, user_utterance: str) -> str:
        assert self.call_log is not None
        ref = self._extract_reference(user_utterance) or self.reschedule_ref
        if not ref:
            self.state = AgentState.AWAITING_RESCHEDULE
            reply = self._t("ask_reschedule_ref")
            self.call_log.agent_turn(reply)
            return reply

        self.reschedule_ref = ref

        resolution = await self.resolver.resolve(
            user_utterance, language=self.language
        )
        if (
            resolution.date is None
            or resolution.time is None
            or resolution.confidence < 0.60
        ):
            self.state = AgentState.AWAITING_RESCHEDULE
            reply = self._t("ask_reschedule_slot", reference=ref)
            self.call_log.agent_turn(reply)
            return reply

        self.last_resolved = {
            "date": resolution.date.isoformat(),
            "time": resolution.time.strftime("%H:%M"),
            "confidence": round(resolution.confidence, 2),
            "explanation": resolution.explanation,
        }

        result = await self._safe_invoke_tool(
            "reschedule_booking",
            {
                "booking_id": ref,
                "date": resolution.date.isoformat(),
                "time_slot": resolution.time.strftime("%H:%M"),
            },
        )
        status = result.get("status")
        if status == "rescheduled":
            self.state = AgentState.COMPLETED
            new_slot = result.get("new_slot_start") or f"{resolution.date} {resolution.time}"
            summary = f"Booking #{ref} was rescheduled to {new_slot}."
            reply = self._t(
                "rescheduled",
                clinic=self.clinic_name,
                reference=ref,
                slot=new_slot,
            )
            self.call_log.agent_turn(reply)
            self._finish(CallStatus.COMPLETED, summary, "rescheduled")
            return reply

        if status == "conflict":
            available = result.get("available", [])
            alt_str = ", ".join(available) if available else "no slots"
            reply = (
                f"{resolution.time.strftime('%H:%M')} ലഭ്യമല്ല; അടുത്ത സമയം {alt_str} ആണ്."
                if self.language.startswith("ml")
                else f"That slot is taken; nearest alternative is {alt_str}."
            )
            self.call_log.agent_turn(reply)
            return reply

        if status == "closed":
            reply = self._t("closed_day", date=resolution.date.isoformat())
            self.call_log.agent_turn(reply)
            return reply

        reply = self._t("reschedule_not_found")
        self.call_log.agent_turn(reply)
        return reply

    def _finish(self, status: CallStatus, summary: str, outcome: str) -> None:
        assert self.call_log is not None
        self.call_log.finish(status, summary, outcome)
        logger.info(
            "Call %s ended: %s (%s)", self.call_log.call.call_sid, outcome, status
        )
