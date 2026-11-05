import pytest

from app.llm.language import (
    DEFAULT_TTS_VOICES,
    SUPPORTED_LANGUAGE_CODES,
    default_voice,
    detect_language,
    normalize_language,
    resolve_language,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ml-IN", "ml-IN"),
        ("ml", "ml-IN"),
        ("malayalam", "ml-IN"),
        ("Malayalam", "ml-IN"),
        ("hi", "hi-IN"),
        ("hindi", "hi-IN"),
        ("tamil", "ta-IN"),
        ("telugu", "te-IN"),
        ("kannada", "kn-IN"),
        ("marathi", "mr-IN"),
        ("bengali", "bn-IN"),
        ("bangla", "bn-IN"),
        ("gujarati", "gu-IN"),
        ("punjabi", "pa-IN"),
        ("english", "en-IN"),
        ("indic-auto", None),
        ("auto", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_language(value: str | None, expected: str | None) -> None:
    assert normalize_language(value) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("നാളെ രാവിലെ 10 മണിക്ക്", "ml-IN"),
        ("कल सुबह 10 बजे अपॉइंटमेंट चाहिए", "hi-IN"),
        ("उद्या सकाळी 10 वाजता हवे आहे", "mr-IN"),
        ("কাল সকাল ১০টায় অ্যাপয়েন্টমেন্ট চাই", "bn-IN"),
        ("நாளை காலை 10 மணிக்கு வேண்டும்", "ta-IN"),
        ("రేపు ఉదయం 10 గంటలకు కావాలి", "te-IN"),
        ("ನಾಳೆ ಬೆಳಗ್ಗೆ 10 ಗಂಟೆಗೆ ಬೇಕು", "kn-IN"),
        ("કાલે સવારે 10 વાગ્યે જોઈએ", "gu-IN"),
        ("ਕੱਲ੍ਹ ਸਵੇਰੇ 10 ਵਜੇ ਚਾਹੀਦਾ ਹੈ", "pa-IN"),
        ("tomorrow at 10 am", "en-IN"),
        ("10:00", None),
        ("", None),
    ],
)
def test_detect_language(text: str, expected: str | None) -> None:
    assert detect_language(text) == expected


def test_detect_language_uses_default_for_unscripted_text() -> None:
    assert detect_language("10:00", default="hi-IN") == "hi-IN"
    assert detect_language("", default="ta-IN") == "ta-IN"


def test_resolve_language_precedence() -> None:
    assert resolve_language("नमस्ते", hint="ta-IN") == "ta-IN"
    assert resolve_language("नमस्ते", hint="indic-auto") == "hi-IN"
    assert resolve_language("10:00", default="ml-IN") == "ml-IN"
    assert resolve_language("hello", default="ml-IN") == "en-IN"


def test_supported_codes_and_voices_cover_the_same_languages() -> None:
    assert set(SUPPORTED_LANGUAGE_CODES) == set(DEFAULT_TTS_VOICES)
    assert default_voice("ml-IN") == "Reshma"
    assert default_voice("hi-IN") == "Nalini"
    assert default_voice("unknown") is None
