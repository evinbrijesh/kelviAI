from __future__ import annotations

import re
from collections.abc import Iterable

SUPPORTED_LANGUAGES: dict[str, str] = {
    "bn-IN": "Bengali",
    "en-IN": "English",
    "gu-IN": "Gujarati",
    "hi-IN": "Hindi",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "pa-IN": "Punjabi",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
}

SUPPORTED_LANGUAGE_CODES: tuple[str, ...] = tuple(SUPPORTED_LANGUAGES)
DEFAULT_LANGUAGE = "ml-IN"

AUTO_LANGUAGE_VALUES = {
    "auto",
    "indic-auto",
    "indic_auto",
    "autodetect",
    "automatic",
    "any",
}

DEFAULT_TTS_VOICES: dict[str, str] = {
    "bn-IN": "Kirra",
    "en-IN": "Kaveri",
    "gu-IN": "Falak",
    "hi-IN": "Nalini",
    "kn-IN": "Saanvi",
    "ml-IN": "Reshma",
    "mr-IN": "Zahira",
    "pa-IN": "Mehuli",
    "ta-IN": "Asmita",
    "te-IN": "Suhana",
}

# Script ranges ordered by strongest signal first. Devanagari is shared by Hindi
# and Marathi, so it is refined with keyword hints in _detect_devanagari.
_SCRIPT_RANGES: tuple[tuple[str, int, int], ...] = (
    ("ml-IN", 0x0D00, 0x0D7F),
    ("ta-IN", 0x0B80, 0x0BFF),
    ("te-IN", 0x0C00, 0x0C7F),
    ("kn-IN", 0x0C80, 0x0CFF),
    ("bn-IN", 0x0980, 0x09FF),
    ("gu-IN", 0x0A80, 0x0AFF),
    ("pa-IN", 0x0A00, 0x0A7F),
    ("hi-IN", 0x0900, 0x097F),
)

_MARATHI_HINTS = (
    "आहे",
    "उद्या",
    "वाजता",
    "हवे",
    "मला",
    "माझे",
    "माझं",
    "नाही",
    "होय",
    "नाव",
    "सकाळी",
    "दुपारी",
    "संध्याकाळी",
)

_LATIN_RE = re.compile(r"[A-Za-z]")
_ROMANIZED_PATTERNS = {
    "hi-IN": re.compile(
        r"(?<!\w)(?:mera\s+naam|"
        r"(?:aaj|kal|parso|parson)\s+(?:subah|dopahar|shaam|sham|raat)|"
        r"(?:subah|dopahar|shaam|sham|raat)\s+(?:\d{1,2}|saadhe|sadhe|das|paanch)|"
        r"(?:\d{1,2}|ek|do|teen|char|paanch|panch|chhe|saat|aath|nau|das|gyarah|barah)"
        r"\s+baje)(?!\w)",
        re.IGNORECASE,
    ),
    "ml-IN": re.compile(
        r"(?<!\w)(?:ente\s+(?:peru|per)|"
        r"(?:innu|naale|nale|mattannal)\s+(?:raavile|ravile|uchakku|vaikunneram|raathri)|"
        r"(?:innu|naale|nale|mattannal)\s+(?:at\s+)?\d{1,2}|"
        r"(?:raavile|ravile|uchakku|vaikunneram|raathri)"
        r"\s+(?:\d{1,2}|pathu|pathara|randu|anchu)|"
        r"(?:pathu|randu|anchu)\s+mani|"
        r"ithara|ithentha|samgathi|vilikkunnath)(?!\w)",
        re.IGNORECASE,
    ),
    "ta-IN": re.compile(
        r"(?<!\w)(?:en\s+peyar|"
        r"(?:indru|naalai)\s+(?:kaalai|mathiyam|maalai|iravu)|"
        r"(?:indru|naalai)\s+(?:at\s+)?\d{1,2}|"
        r"(?:kaalai|mathiyam|maalai|iravu)\s+(?:\d{1,2}|pathu|ainthu)|"
        r"(?:pathu|ainthu)\s+(?:mani|arai))(?!\w)",
        re.IGNORECASE,
    ),
    "bn-IN": re.compile(
        r"(?<!\w)(?:amar\s+naam|"
        r"(?:aaj|aj|kal|porshu)\s+(?:shokal|sokal|dupur|bikel|shondha|raat)|"
        r"(?:shokal|sokal|dupur|bikel|shondha)\s+(?:\d{1,2}|sare|saare|dosh|panch)|"
        r"(?:\d{1,2}|dosh|panch)\s+(?:tay|tae))(?!\w)",
        re.IGNORECASE,
    ),
}


def _build_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for code, name in SUPPORTED_LANGUAGES.items():
        aliases[code.lower()] = code
        aliases[code.replace("-IN", "").lower()] = code
        aliases[name.lower()] = code
    aliases.update(
        {
            "bangla": "bn-IN",
            "bengali": "bn-IN",
            "gujrati": "gu-IN",
            "panjabi": "pa-IN",
            "punjabi": "pa-IN",
            "hinglish": "hi-IN",
            "manglish": "ml-IN",
            "tanglish": "ta-IN",
            "benglish": "bn-IN",
        }
    )
    return aliases


_LANGUAGE_ALIASES = _build_aliases()


def normalize_language(value: str | None) -> str | None:
    """Map a language code, English name, or short alias to a canonical code."""
    if not value:
        return None
    key = value.strip().lower().replace("_", "-")
    if key in AUTO_LANGUAGE_VALUES:
        return None
    return _LANGUAGE_ALIASES.get(key)


def is_supported_language(value: str | None) -> bool:
    return normalize_language(value) is not None


def language_name(value: str | None) -> str:
    code = normalize_language(value)
    return SUPPORTED_LANGUAGES.get(code or "", "Unknown")


def default_voice(language: str | None) -> str | None:
    return DEFAULT_TTS_VOICES.get(normalize_language(language) or "")


def _script_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for char in text:
        point = ord(char)
        for code, start, end in _SCRIPT_RANGES:
            if start <= point <= end:
                counts[code] = counts.get(code, 0) + 1
                break
    return counts


def _detect_devanagari(text: str) -> str:
    return "mr-IN" if any(hint in text for hint in _MARATHI_HINTS) else "hi-IN"


def detect_language(text: str | None, *, default: str | None = None) -> str | None:
    """Detect native scripts and a small set of romanized booking phrases."""
    if not text or not text.strip():
        return normalize_language(default)

    counts = _script_counts(text)
    if counts:
        code = max(counts, key=lambda item: counts[item])
        if code == "hi-IN":
            return _detect_devanagari(text)
        return code

    scores = {code: len(pattern.findall(text)) for code, pattern in _ROMANIZED_PATTERNS.items()}
    strongest = max(scores.values())
    matches = [code for code, score in scores.items() if score == strongest and score > 0]
    if len(matches) == 1:
        return matches[0]

    if _LATIN_RE.search(text):
        return "en-IN"

    return normalize_language(default)


def resolve_language(
    text: str | None = None,
    *,
    hint: str | None = None,
    default: str | None = DEFAULT_LANGUAGE,
) -> str:
    """Pick the reply language: explicit hint, then script detection, then default."""
    return (
        normalize_language(hint)
        or detect_language(text)
        or normalize_language(default)
        or DEFAULT_LANGUAGE
    )


def language_codes() -> Iterable[str]:
    return SUPPORTED_LANGUAGE_CODES
