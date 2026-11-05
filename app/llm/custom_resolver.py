import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.llm.interfaces import DateTimeResolution, DateTimeResolver
from app.llm.language import DEFAULT_LANGUAGE, normalize_language

DEFAULT_TIMEZONE = "Asia/Kolkata"

# Relative days keyed by offset from today (0 = today, 1 = tomorrow, 2 = day after).
RELATIVE_DATE_TERMS: dict[str, dict[int, tuple[str, ...]]] = {
    "ml-IN": {0: ("ഇന്ന്",), 1: ("നാളെ",), 2: ("മറ്റന്നാൾ",)},
    "hi-IN": {0: ("आज",), 1: ("कल",), 2: ("परसों",)},
    "mr-IN": {0: ("आज",), 1: ("उद्या",), 2: ("परवा",)},
    "bn-IN": {0: ("আজ",), 1: ("কাল",), 2: ("পরশু",)},
    "ta-IN": {0: ("இன்று",), 1: ("நாளை",), 2: ("நாளை மறுநாள்", "நாளைமறுநாள்")},
    "te-IN": {0: ("ఈరోజు",), 1: ("రేపు",), 2: ("ఎల్లుండి",)},
    "kn-IN": {0: ("ಇಂದು",), 1: ("ನಾಳೆ",), 2: ("ನಾಡಿದ್ದು",)},
    "gu-IN": {0: ("આજે",), 1: ("કાલે",), 2: ("પરમ દિવસે", "પરમદિવસે")},
    "pa-IN": {0: ("ਅੱਜ",), 1: ("ਕੱਲ੍ਹ", "ਕੱਲ"), 2: ("ਪਰਸੋਂ",)},
    "en-IN": {
        0: ("today",),
        1: ("tomorrow",),
        2: ("day after tomorrow",),
    },
}

MORNING_TERMS = (
    "morning",
    "രാവിലെ",
    "सुबह",
    "সকাল",
    "காலை",
    "ఉదయం",
    "ಬೆಳಗ್ಗೆ",
    "સવારે",
    "ਸਵੇਰੇ",
    "सकाळी",
)

AFTERNOON_TERMS = (
    "afternoon",
    "ഉച്ചയ്ക്ക്",
    "दोपहर",
    "দুপুর",
    "மதியம்",
    "మధ్యాహ్నం",
    "ಮಧ್ಯಾಹ್ನ",
    "બપોરે",
    "ਦੁਪਹਿਰ",
    "दुपारी",
)

EVENING_TERMS = (
    "evening",
    "വൈകുന്നേരം",
    "വൈകിട്ട്",
    "शाम",
    "সন্ধ্যা",
    "বিকেল",
    "மாலை",
    "సాయంత్రం",
    "ಸಂಜೆ",
    "સાંજે",
    "ਸ਼ਾਮ",
    "संध्याकाळी",
)

NIGHT_TERMS = (
    "night",
    "രാത്രി",
    "रात",
    "রাত",
    "இரவு",
    "రాత్రి",
    "ರಾತ್ರಿ",
    "રાત્રે",
    "ਰਾਤ",
)

NUMBER_WORDS: dict[str, dict[str, int]] = {
    "ml-IN": {
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
    },
    "hi-IN": {
        "एक": 1,
        "दो": 2,
        "तीन": 3,
        "चार": 4,
        "पांच": 5,
        "पाँच": 5,
        "छह": 6,
        "छः": 6,
        "सात": 7,
        "आठ": 8,
        "नौ": 9,
        "दस": 10,
        "ग्यारह": 11,
        "बारह": 12,
    },
    "mr-IN": {
        "एक": 1,
        "दोन": 2,
        "तीन": 3,
        "चार": 4,
        "पाच": 5,
        "सहा": 6,
        "सात": 7,
        "आठ": 8,
        "नऊ": 9,
        "दहा": 10,
        "अकरा": 11,
        "बारा": 12,
    },
    "bn-IN": {
        "এক": 1,
        "দুই": 2,
        "তিন": 3,
        "চার": 4,
        "পাঁচ": 5,
        "ছয়": 6,
        "সাত": 7,
        "আট": 8,
        "নয়": 9,
        "দশ": 10,
        "এগারো": 11,
        "বারো": 12,
    },
    "ta-IN": {
        "ஒன்று": 1,
        "ஒரு": 1,
        "இரண்டு": 2,
        "மூன்று": 3,
        "நான்கு": 4,
        "ஐந்து": 5,
        "ஆறு": 6,
        "ஏழு": 7,
        "எட்டு": 8,
        "ஒன்பது": 9,
        "பத்து": 10,
        "பதினொன்று": 11,
        "பன்னிரண்டு": 12,
    },
    "te-IN": {
        "ఒకటి": 1,
        "ఒక": 1,
        "రెండు": 2,
        "మూడు": 3,
        "నాలుగు": 4,
        "ఐదు": 5,
        "ఆరు": 6,
        "ఏడు": 7,
        "ఎనిమిది": 8,
        "తొమ్మిది": 9,
        "పది": 10,
        "పదకొండు": 11,
        "పన్నెండు": 12,
    },
    "kn-IN": {
        "ಒಂದು": 1,
        "ಎರಡು": 2,
        "ಮೂರು": 3,
        "ನಾಲ್ಕು": 4,
        "ಐದು": 5,
        "ಆರು": 6,
        "ಏಳು": 7,
        "ಎಂಟು": 8,
        "ಒಂಬತ್ತು": 9,
        "ಹತ್ತು": 10,
        "ಹನ್ನೊಂದು": 11,
        "ಹನ್ನೆರಡು": 12,
    },
    "gu-IN": {
        "એક": 1,
        "બે": 2,
        "ત્રણ": 3,
        "ચાર": 4,
        "પાંચ": 5,
        "છ": 6,
        "સાત": 7,
        "આઠ": 8,
        "નવ": 9,
        "દસ": 10,
        "અગિયાર": 11,
        "બાર": 12,
    },
    "pa-IN": {
        "ਇੱਕ": 1,
        "ਦੋ": 2,
        "ਤਿੰਨ": 3,
        "ਚਾਰ": 4,
        "ਪੰਜ": 5,
        "ਛੇ": 6,
        "ਸੱਤ": 7,
        "ਅੱਠ": 8,
        "ਨੌਂ": 9,
        "ਦਸ": 10,
        "ਗਿਆਰਾਂ": 11,
        "ਬਾਰਾਂ": 12,
    },
    "en-IN": {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
    },
}

CLOCK_MARKERS: dict[str, tuple[str, ...]] = {
    "ml-IN": ("മണി",),
    "hi-IN": ("बजे",),
    "mr-IN": ("वाजता", "वाजले"),
    "bn-IN": ("টায়", "টার", "টা"),
    "ta-IN": ("மணி",),
    "te-IN": ("గంటలకు", "గంటకు", "గంటల"),
    "kn-IN": ("ಗಂಟೆಗೆ", "ಗಂಟೆ"),
    "gu-IN": ("વાગ્યે", "વાગે"),
    "pa-IN": ("ਵਜੇ",),
    "en-IN": ("o'clock", "oclock"),
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

HALF_HOUR_PREFIXES: dict[str, tuple[str, ...]] = {
    "hi-IN": ("साढ़े", "साढे"),
    "mr-IN": ("साडे",),
    "bn-IN": ("সাড়ে",),
    "gu-IN": ("સાડા",),
    "pa-IN": ("ਸਾਢੇ",),
    "en-IN": ("half past",),
}

_NATIVE_DIGITS = {
    "०": "0",
    "१": "1",
    "२": "2",
    "३": "3",
    "४": "4",
    "५": "5",
    "६": "6",
    "७": "7",
    "८": "8",
    "९": "9",
    "০": "0",
    "১": "1",
    "২": "2",
    "৩": "3",
    "৪": "4",
    "৫": "5",
    "৬": "6",
    "৭": "7",
    "৮": "8",
    "৯": "9",
    "੦": "0",
    "੧": "1",
    "੨": "2",
    "੩": "3",
    "੪": "4",
    "੫": "5",
    "੬": "6",
    "੭": "7",
    "੮": "8",
    "੯": "9",
    "૦": "0",
    "૧": "1",
    "૨": "2",
    "૩": "3",
    "૪": "4",
    "૫": "5",
    "૬": "6",
    "૭": "7",
    "૮": "8",
    "૯": "9",
    "௦": "0",
    "௧": "1",
    "௨": "2",
    "௩": "3",
    "௪": "4",
    "௫": "5",
    "௬": "6",
    "௭": "7",
    "௮": "8",
    "௯": "9",
    "౦": "0",
    "౧": "1",
    "౨": "2",
    "౩": "3",
    "౪": "4",
    "౫": "5",
    "౬": "6",
    "౭": "7",
    "౮": "8",
    "౯": "9",
    "೦": "0",
    "೧": "1",
    "೨": "2",
    "೩": "3",
    "೪": "4",
    "೫": "5",
    "೬": "6",
    "೭": "7",
    "೮": "8",
    "೯": "9",
    "൦": "0",
    "൧": "1",
    "൨": "2",
    "൩": "3",
    "൪": "4",
    "൫": "5",
    "൬": "6",
    "൭": "7",
    "൮": "8",
    "൯": "9",
}

_DIGIT_TABLE = str.maketrans(_NATIVE_DIGITS)
_CLOCK_MARKER_PATTERN = "|".join(
    re.escape(marker) for markers in CLOCK_MARKERS.values() for marker in markers
)


def _normalize_digits(text: str) -> str:
    return text.translate(_DIGIT_TABLE)


def _ordered_languages(preferred: str | None) -> list[str]:
    order = list(RELATIVE_DATE_TERMS)
    code = normalize_language(preferred)
    if code in order:
        order.remove(code)
        order.insert(0, code)
    return order


class CustomDateTimeResolver(DateTimeResolver):
    def __init__(self, timezone_str: str = DEFAULT_TIMEZONE) -> None:
        self.tz = ZoneInfo(timezone_str)
        self.timezone_str = timezone_str

    async def resolve(
        self, text: str, language: str, context: dict[str, Any] | None = None
    ) -> DateTimeResolution:
        now = datetime.now(self.tz)
        clean_text = text.strip()
        normalized_text = _normalize_digits(clean_text)
        text_lower = normalized_text.lower()
        languages = _ordered_languages(language)

        resolved_date, date_expl = self._extract_date(
            normalized_text, text_lower, now, languages
        )
        resolved_time, time_expl = self._extract_time(
            normalized_text, text_lower, languages
        )

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
        self,
        text: str,
        text_lower: str,
        now: datetime,
        languages: list[str],
    ) -> tuple[date | None, str]:
        iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if iso_match:
            try:
                parsed_date = date.fromisoformat(iso_match.group(1))
                return parsed_date, f"Detected date '{iso_match.group(1)}'"
            except ValueError:
                pass

        dmy_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
        if dmy_match:
            try:
                parsed_date = date(
                    int(dmy_match.group(3)),
                    int(dmy_match.group(2)),
                    int(dmy_match.group(1)),
                )
                return parsed_date, f"Detected date '{dmy_match.group(0)}'"
            except ValueError:
                pass

        labels = {0: "today", 1: "tomorrow", 2: "day after tomorrow"}
        for offset in (2, 1, 0):
            for code in languages:
                for term in RELATIVE_DATE_TERMS.get(code, {}).get(offset, ()):
                    if term.lower() in text_lower:
                        target = now + timedelta(days=offset)
                        return target.date(), f"Detected {labels[offset]} ({term})"
        return None, ""

    def _extract_time(
        self, text: str, text_lower: str, languages: list[str]
    ) -> tuple[time | None, str]:
        is_morning = any(term in text_lower for term in MORNING_TERMS)
        is_pm = any(
            term in text_lower
            for term in (*AFTERNOON_TERMS, *EVENING_TERMS, *NIGHT_TERMS)
        )
        is_pm = is_pm and not is_morning

        for word, (hour, minute) in MALAYALAM_HALF_HOURS.items():
            if word in text:
                return self._clock(hour, minute, is_morning, is_pm), (
                    f"Detected time '{word}'"
                )

        for code in languages:
            for prefix in HALF_HOUR_PREFIXES.get(code, ()):
                match = re.search(
                    rf"{re.escape(prefix)}\s*(\d{{1,2}}|[^\s,.;]+)\s*"
                    rf"(?:{_CLOCK_MARKER_PATTERN})?",
                    text_lower,
                )
                if match is None:
                    continue
                parsed_hour = self._as_hour(match.group(1))
                if parsed_hour is not None:
                    return self._clock(parsed_hour, 30, is_morning, is_pm), (
                        f"Detected half-hour '{match.group(0).strip()}'"
                    )

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

        for code in languages:
            for word, number in NUMBER_WORDS.get(code, {}).items():
                match = re.search(
                    rf"{re.escape(word)}\s*(?:{_CLOCK_MARKER_PATTERN})",
                    text_lower,
                )
                if match:
                    return self._clock(number, 0, is_morning, is_pm), (
                        f"Detected time '{match.group(0).strip()}'"
                    )

        clock_match = re.search(
            rf"(?<!\d)(\d{{1,2}})\s*(?:{_CLOCK_MARKER_PATTERN})", text_lower
        )
        if clock_match:
            h = int(clock_match.group(1))
            if 1 <= h <= 12:
                return self._clock(h, 0, is_morning, is_pm), (
                    f"Detected time '{clock_match.group(0).strip()}'"
                )

        ampm_match = re.search(r"(?<![a-z])(\d{1,2})\s*(am|pm)\b", text_lower)
        if ampm_match:
            h = int(ampm_match.group(1))
            if ampm_match.group(2) == "pm" and h < 12:
                h += 12
            elif ampm_match.group(2) == "am" and h == 12:
                h = 0
            return time(h, 0), f"Detected time '{ampm_match.group(0)}'"

        at_match = re.search(r"\bat\s+(\d{1,2})\b", text_lower)
        if at_match:
            h = int(at_match.group(1))
            if 1 <= h <= 12:
                return self._clock(h, 0, is_morning, is_pm), (
                    f"Detected time '{at_match.group(0)}'"
                )

        return None, ""

    def _as_hour(self, token: str) -> int | None:
        if token.isdigit():
            hour = int(token)
            return hour if 1 <= hour <= 12 else None
        for words in NUMBER_WORDS.values():
            if token in words:
                return words[token]
        return None

    @staticmethod
    def _clock(hour: int, minute: int, is_morning: bool, is_pm: bool) -> time:
        final_hour = hour
        if is_pm and final_hour < 12:
            final_hour += 12
        elif not is_morning and final_hour in range(1, 7):
            final_hour += 12
        return time(final_hour, minute)


__all__ = ["CustomDateTimeResolver", "DEFAULT_LANGUAGE"]
