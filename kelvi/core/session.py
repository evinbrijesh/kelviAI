import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from kelvi.indic.language import DEFAULT_LANGUAGE

_AFFIRMATIVE_PATTERNS = {
    "ml-IN": re.compile(
        r"(?:^|\s|[.,!?])(?:ശരി|അതെ|ഉറപ്പാണ്|ചെയ്തോളൂ|ചെയ്തോ|ഓക്കെ|ആണ്|"
        r"റദ്ദാക്കിക്കോളൂ|yes|yeah|sure|confirm)(?:$|\s|[.,!?])",
        re.IGNORECASE,
    ),
    "hi-IN": re.compile(
        r"(?:^|\s|[.,!?])(?:हाँ|हां|हाँजी|ठीक है|कर दीजिए|ज़रूर|"
        r"sahi|theek|haan|yes|yeah|sure)(?:$|\s|[.,!?])",
        re.IGNORECASE,
    ),
    "en-IN": re.compile(
        r"\b(?:yes|yeah|yep|sure|confirm|proceed|ok|okay|do it)\b",
        re.IGNORECASE,
    ),
}

_NEGATIVE_PATTERNS = {
    "ml-IN": re.compile(
        r"(?:^|\s|[.,!?])(?:വേണ്ട|ഇല്ല|റദ്ദാക്കണ്ട|മാറ്റണ്ട|വേണ്ടതില്ല|"
        r"no|nope|cancel|stop)(?:$|\s|[.,!?])",
        re.IGNORECASE,
    ),
    "hi-IN": re.compile(
        r"(?:^|\s|[.,!?])(?:नहीं|मत करो|रहने दो|रुकिए|nahi|nahin|mat karo|"
        r"no|nope|cancel)(?:$|\s|[.,!?])",
        re.IGNORECASE,
    ),
    "en-IN": re.compile(
        r"\b(?:no|nope|don't|do not|cancel|stop|nevermind)\b",
        re.IGNORECASE,
    ),
}


@dataclass
class PendingConfirmation:
    tool_name: str
    arguments: dict[str, Any]
    prompt: str


@dataclass
class TurnResult:
    reply_text: str
    language: str
    tool_executed: str | None = None
    tool_result: Any = None
    pending_confirmation: bool = False
    xray: dict[str, Any] = field(default_factory=dict)


class Session:
    """Domain-agnostic conversational session.

    Manages turns, confirmation guardrails, and context.
    """

    def __init__(
        self,
        session_id: str,
        *,
        language: str = DEFAULT_LANGUAGE,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.session_id = session_id
        self.language = language
        self.context: dict[str, Any] = dict(context or {})
        self.history: list[dict[str, Any]] = []
        self.pending_confirmation: PendingConfirmation | None = None

    def add_turn(self, role: str, content: str) -> None:
        self.history.append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def is_confirmation_turn(self, text: str) -> tuple[bool, bool]:
        """Check if user text is answering a pending confirmation.

        Returns (is_handled, is_confirmed).
        """
        if not self.pending_confirmation:
            return False, False

        lang = self.language
        pos_re = _AFFIRMATIVE_PATTERNS.get(lang, _AFFIRMATIVE_PATTERNS["en-IN"])
        neg_re = _NEGATIVE_PATTERNS.get(lang, _NEGATIVE_PATTERNS["en-IN"])

        if pos_re.search(text):
            return True, True
        if neg_re.search(text):
            return True, False
        return False, False
