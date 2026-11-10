from collections.abc import Callable
from typing import Any
from uuid import uuid4

from kelvi.core.events import XRayTrace
from kelvi.core.session import PendingConfirmation, Session, TurnResult
from kelvi.indic.discourse import clean_discourse_markers
from kelvi.indic.language import DEFAULT_LANGUAGE, detect_language, normalize_language
from kelvi.tools.decorator import tool
from kelvi.tools.registry import ToolRegistry, ToolSpec

IntentMatcher = tuple[
    Callable[[str, Session], bool],
    str,
    Callable[[dict[str, Any], Session], str],
]


class KelviEngine:
    """The central orchestrator for an Indian-language action-taking voice agent."""

    def __init__(
        self,
        *,
        name: str = "KelviAgent",
        default_language: str = DEFAULT_LANGUAGE,
        tools: ToolRegistry | None = None,
    ) -> None:
        self.name = name
        self.default_language = normalize_language(default_language) or DEFAULT_LANGUAGE
        self.tools = tools or ToolRegistry()
        self._intent_matchers: list[IntentMatcher] = []

    def tool(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        requires_confirmation: bool = False,
        confirmation_prompt: dict[str, str] | None = None,
    ) -> Callable[[Callable[..., Any]], Any]:
        """Convenience decorator to register tools directly on this engine."""
        dec = tool(
            name=name,
            description=description,
            requires_confirmation=requires_confirmation,
            confirmation_prompt=confirmation_prompt,
        )

        def wrapper(func: Callable[..., Any]) -> Any:
            wrapped = dec(func)
            self.tools.register(wrapped)
            return wrapped

        return wrapper

    def register_tool(self, tool_or_spec: Any) -> ToolSpec:
        return self.tools.register(tool_or_spec)

    def on_intent(
        self,
        matcher: Callable[[str, Session], bool],
        tool_name: str,
        formatter: Callable[[dict[str, Any], Session], str],
    ) -> None:
        """Register a fast-path regex or rule matcher to invoke a tool."""
        self._intent_matchers.append((matcher, tool_name, formatter))

    async def process_turn(
        self,
        session: Session,
        transcript: str,
    ) -> TurnResult:
        turn_id = str(uuid4())[:8]
        xray = XRayTrace(turn_id=turn_id)
        xray.add_event("transcript_received", text=transcript)

        # 1. Clean discourse markers
        cleaned = clean_discourse_markers(transcript, session.language)
        xray.add_event("discourse_cleaned", raw=transcript, cleaned=cleaned)

        # 2. Detect language
        detected = detect_language(transcript)
        if detected:
            session.language = detected
        xray.add_event(
            "language_resolved",
            language=session.language,
            detected_from_turn=detected,
        )

        session.add_turn("user", transcript)

        # 3. Check pending confirmation
        if session.pending_confirmation:
            is_handled, is_confirmed = session.is_confirmation_turn(transcript)
            if is_handled:
                pending = session.pending_confirmation
                session.pending_confirmation = None
                xray.add_event(
                    "confirmation_response",
                    confirmed=is_confirmed,
                    tool=pending.tool_name,
                )

                if is_confirmed:
                    tool_result = await self.tools.invoke(
                        pending.tool_name, pending.arguments, confirmed=True
                    )
                    xray.add_event(
                        "tool_executed",
                        tool=pending.tool_name,
                        result=tool_result,
                    )
                    formatter = self._find_formatter(pending.tool_name)
                    if formatter:
                        reply = formatter(tool_result, session)
                    else:
                        reply = self._format_confirmation_success(
                            pending.tool_name, tool_result, session.language
                        )
                else:
                    tool_result = {"status": "cancelled"}
                    reply = self._format_cancellation(session.language)

                session.add_turn("assistant", reply)
                xray.finish()
                return TurnResult(
                    reply_text=reply,
                    language=session.language,
                    tool_executed=pending.tool_name if is_confirmed else None,
                    tool_result=tool_result,
                    xray=xray.summary(),
                )

        # 4. Match fast-path intents or registered tools
        for matcher, tool_name, formatter in self._intent_matchers:
            if matcher(cleaned, session):
                xray.add_event("intent_matched", tool=tool_name, method="fast_path")
                spec = self.tools.get(tool_name)

                # Extract arguments if matcher stored them in session.context or defaults
                props = spec.parameters.get("properties", {})
                args = {k: session.context[k] for k in props if k in session.context}

                if spec.requires_confirmation:
                    prompt = spec.confirmation_prompt.get(
                        session.language,
                        f"Are you sure you want to execute {tool_name}?",
                    )
                    session.pending_confirmation = PendingConfirmation(
                        tool_name=tool_name,
                        arguments=args,
                        prompt=prompt,
                    )
                    xray.add_event(
                        "confirmation_requested",
                        tool=tool_name,
                        prompt=prompt,
                    )
                    session.add_turn("assistant", prompt)
                    xray.finish()
                    return TurnResult(
                        reply_text=prompt,
                        language=session.language,
                        pending_confirmation=True,
                        xray=xray.summary(),
                    )

                tool_result = await self.tools.invoke(tool_name, args, confirmed=False)
                xray.add_event(
                    "tool_executed",
                    tool=tool_name,
                    result=tool_result,
                )
                reply = formatter(tool_result, session)
                session.add_turn("assistant", reply)
                xray.finish()
                return TurnResult(
                    reply_text=reply,
                    language=session.language,
                    tool_executed=tool_name,
                    tool_result=tool_result,
                    xray=xray.summary(),
                )

        # Default fallback
        fallback_replies = {
            "ml-IN": "ക്ഷമിക്കണം, എനിക്ക് അത് മനസ്സിലായില്ല. ഒന്നുകൂടി പറയാമോ?",
            "hi-IN": "माफ़ कीजिए, मुझे समझ नहीं आया। क्या आप दोहरा सकते हैं?",
            "en-IN": "Sorry, I didn't quite catch that. Could you please repeat?",
        }
        reply = fallback_replies.get(session.language, fallback_replies["en-IN"])
        xray.add_event("fallback_triggered", reason="no_intent_matched")
        session.add_turn("assistant", reply)
        xray.finish()

        return TurnResult(
            reply_text=reply,
            language=session.language,
            xray=xray.summary(),
        )

    def _find_formatter(
        self, tool_name: str
    ) -> Callable[[dict[str, Any], Session], str] | None:
        for _, name, formatter in self._intent_matchers:
            if name == tool_name:
                return formatter
        return None

    def _format_confirmation_success(
        self, tool_name: str, result: Any, language: str
    ) -> str:
        if language.startswith("ml"):
            return "ശരി, നിങ്ങളുടെ ആവശ്യം വിജയകരമായി പൂർത്തിയാക്കിയിട്ടുണ്ട്."
        if language.startswith("hi"):
            return "ठीक है, आपका अनुरोध सफलतापूर्वक पूरा कर दिया गया है।"
        return "Sure, your request has been successfully completed."

    def _format_cancellation(self, language: str) -> str:
        if language.startswith("ml"):
            return "ശരി, ആ നടപടി റദ്ദാക്കിയിട്ടുണ്ട്."
        if language.startswith("hi"):
            return "ठीक है, अनुरोध रद्द कर दिया गया है।"
        return "Understood, that action has been cancelled."
