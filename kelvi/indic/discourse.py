import re

# Conversational discourse markers common in spoken Malayalam, Hindi, and code-mixed speech
_MALAYALAM_DISCOURSE_MARKERS = [
    r"എന്നാട്ടോ",
    r"ആണട്ടോ",
    r"ആട്ടോ",
    r"കേട്ടോ",
    r"എന്നേ",
    r"ആണേ",
    r"തന്നെയാട്ടോ",
    r"ennatto\b",
    r"ennato\b",
    r"aanatto\b",
    r"aatto\b",
    r"ketto\b",
    r"thanneyatto\b",
]

_HINDI_DISCOURSE_MARKERS = [
    r"है\s*ना\b",
    r"(?:\s+|^)जी(?:\s+|$)",
    r"सुनो\b",
    r"bhaiya\b",
    r"yaar\b",
]

_DISCOURSE_PATTERNS = {
    "ml-IN": re.compile("|".join(_MALAYALAM_DISCOURSE_MARKERS), re.IGNORECASE),
    "hi-IN": re.compile("|".join(_HINDI_DISCOURSE_MARKERS), re.IGNORECASE),
}

_ALL_DISCOURSE_PATTERN = re.compile(
    "|".join(_MALAYALAM_DISCOURSE_MARKERS + _HINDI_DISCOURSE_MARKERS),
    re.IGNORECASE,
)


def clean_discourse_markers(text: str, language: str | None = None) -> str:
    """Strip spoken discourse particles and conversational tags from extracted entity values.

    For example, 'ജോൺസൺ എന്നാട്ടോ' -> 'ജോൺസൺ', or 'Rahul bhaiya' -> 'Rahul'.
    """
    if not text:
        return ""

    if language:
        pattern = _DISCOURSE_PATTERNS.get(language, _ALL_DISCOURSE_PATTERN)
    else:
        pattern = _ALL_DISCOURSE_PATTERN

    cleaned = pattern.sub("", text)
    # Collapse excess whitespace
    return re.sub(r"\s+", " ", cleaned).strip()
