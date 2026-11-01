import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.llm.interfaces import DateTimeResolution, DateTimeResolver

DEFAULT_TIMEZONE = "Asia/Kolkata"

MALAYALAM_NUMBERS = {
    "ഒന്ന്": 1,
    "രണ്ട്": 2,
    "മൂന്ന്": 3,
    "നാല്": 4,
    "അഞ്ച്": 5,
    "ആറ്": 6,
    "ഏഴ്": 7,
    "എട്ട്": 8,
    "ഒൻപത്": 9,
    "പത്ത്": 10,
    "പതിനൊന്ന്": 11,
    "പന്ത്രണ്ട്": 12,
}

MALAYALAM_HALF_HOURS = {
    "ഒന്നര": (1, 30),
    "രണ്ടര": (2, 30),
    "മൂന്നര": (3, 30),
    "നാലര": (4, 30),
    "അഞ്ചര": (5, 30),
    "ആറര": (6, 30),
    "ഏഴര": (7, 30),
    "എട്ടര": (8, 30),
    "ഒൻപതര": (9, 30),
    "പത്തര": (10, 30),
    "പതിനൊന്നര": (11, 30),
    "പന്ത്രണ്ടര": (12, 30),
}


class CustomDateTimeResolver(DateTimeResolver):
    def __init__(self, timezone_str: str = DEFAULT_TIMEZONE) -> None:
        self.tz = ZoneInfo(timezone_str)
        self.timezone_str = timezone_str

    async def resolve(
        self, text: str, language: str, context: dict[str, Any] | None = None
    ) -> DateTimeResolution:
        now = datetime.now(self.tz)
        clean_text = text.strip()
        text_lower = clean_text.lower()

        resolved_date, date_expl = self._extract_date(clean_text, text_lower, now)
        resolved_time, time_expl = self._extract_time(clean_text, text_lower)

        explanations: list[str] = []
        if date_expl:
            explanations.append(date_expl)
        if time_expl:
            explanations.append(time_expl)

        if resolved_date and resolved_time:
            confidence = 0.95
            explanation = "; ".join(explanations)
        elif resolved_date:
            confidence = 0.85
            explanation = date_expl
        elif resolved_time:
            confidence = 0.75
            explanation = time_expl
        else:
            confidence = 0.0
            explanation = "No date/time pattern detected"

        return DateTimeResolution(
            date=resolved_date,
            time=resolved_time,
            timezone=self.timezone_str,
            confidence=confidence,
            explanation=explanation,
        )

    def _extract_date(
        self, text: str, text_lower: str, now: datetime
    ) -> tuple[date | None, str]:
        if "മറ്റന്നാൾ" in text or "day after tomorrow" in text_lower:
            target = now + timedelta(days=2)
            return target.date(), "Detected day after tomorrow (മറ്റന്നാൾ)"
        if "നാളെ" in text or "tomorrow" in text_lower:
            target = now + timedelta(days=1)
            return target.date(), "Detected tomorrow (നാളെ)"
        if "ഇന്ന്" in text or "today" in text_lower:
            return now.date(), "Detected today (ഇന്ന്)"
        return None, ""

    def _extract_time(self, text: str, text_lower: str) -> tuple[time | None, str]:
        is_pm = False
        is_morning = False
        if (
            "രാവിലെ" in text
            or re.search(r"(?<![a-z])am(?![a-z])", text_lower)
            or "morning" in text_lower
        ):
            is_morning = True
        elif (
            any(k in text for k in ["ഉച്ചയ്ക്ക്", "വൈകുന്നേരം", "വൈകിട്ട്", "രാത്രി"])
            or re.search(r"(?<![a-z])pm(?![a-z])", text_lower)
            or "afternoon" in text_lower
            or "evening" in text_lower
        ):
            is_pm = True

        for word, (hour, minute) in MALAYALAM_HALF_HOURS.items():
            if word in text:
                final_hour = hour
                if is_pm and final_hour < 12:
                    final_hour += 12
                elif not is_morning and final_hour in range(1, 7):
                    final_hour += 12
                return time(final_hour, minute), f"Detected time '{word}'"

        colon_match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
        if colon_match:
            h = int(colon_match.group(1))
            m = int(colon_match.group(2))
            if 0 <= h < 24 and 0 <= m < 60:
                if is_pm and h < 12:
                    h += 12
                elif is_morning and h == 12:
                    h = 0
                return time(h, m), f"Detected time '{colon_match.group(0)}'"

        for word, num in MALAYALAM_NUMBERS.items():
            if f"{word} മണി" in text or f"{word}മണി" in text:
                h = num
                if is_pm and h < 12:
                    h += 12
                elif not is_morning and h in range(1, 7):
                    h += 12
                return time(h, 0), f"Detected time '{word} മണി'"

        mani_match = re.search(r"(\d{1,2})\s*മണി", text)
        if mani_match:
            h = int(mani_match.group(1))
            if 1 <= h <= 12:
                if is_pm and h < 12:
                    h += 12
                elif not is_morning and h in range(1, 7):
                    h += 12
                return time(h, 0), f"Detected time '{mani_match.group(0)}'"

        ampm_match = re.search(r"(?<!\d)(\d{1,2})\s*(am|pm)\b", text_lower)
        if ampm_match:
            h = int(ampm_match.group(1))
            ampm = ampm_match.group(2)
            if ampm == "pm" and h < 12:
                h += 12
            elif ampm == "am" and h == 12:
                h = 0
            return time(h, 0), f"Detected time '{ampm_match.group(0)}'"

        return None, ""
