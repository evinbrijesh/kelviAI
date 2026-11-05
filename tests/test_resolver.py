from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.llm.custom_resolver import CustomDateTimeResolver


@pytest.mark.asyncio
async def test_resolve_malayalam_tomorrow_morning() -> None:
    resolver = CustomDateTimeResolver()
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    expected_date = (now + timedelta(days=1)).date()

    res = await resolver.resolve("നാളെ രാവിലെ 10 മണിക്ക് അപ്പോയിന്റ്മെന്റ് വേണം", language="malayalam")
    assert res.date == expected_date
    assert res.time == time(10, 0)
    assert res.timezone == "Asia/Kolkata"
    assert res.confidence >= 0.9
    assert "നാളെ" in res.explanation


@pytest.mark.asyncio
async def test_resolve_malayalam_today_evening() -> None:
    resolver = CustomDateTimeResolver()
    now = datetime.now(ZoneInfo("Asia/Kolkata"))

    res = await resolver.resolve("ഇന്ന് വൈകുന്നേരം 4 മണിക്ക് സമയം കിട്ടുമോ", language="malayalam")
    assert res.date == now.date()
    assert res.time == time(16, 0)
    assert res.timezone == "Asia/Kolkata"


@pytest.mark.asyncio
async def test_resolve_malayalam_day_after_tomorrow() -> None:
    resolver = CustomDateTimeResolver()
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    expected_date = (now + timedelta(days=2)).date()

    res = await resolver.resolve("മറ്റന്നാൾ ഉച്ചയ്ക്ക് 1 മണി", language="malayalam")
    assert res.date == expected_date
    assert res.time == time(13, 0)


@pytest.mark.asyncio
async def test_resolve_malayalam_half_hour() -> None:
    resolver = CustomDateTimeResolver()

    res = await resolver.resolve("പത്തര മണിക്ക്", language="malayalam")
    assert res.time == time(10, 30)


@pytest.mark.asyncio
async def test_resolve_english_fallback() -> None:
    resolver = CustomDateTimeResolver()
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    expected_date = (now + timedelta(days=1)).date()

    res = await resolver.resolve("tomorrow at 2 pm", language="english")
    assert res.date == expected_date
    assert res.time == time(14, 0)


@pytest.mark.asyncio
async def test_resolve_compact_am_pm() -> None:
    resolver = CustomDateTimeResolver()
    now = datetime.now(ZoneInfo("Asia/Kolkata"))

    res = await resolver.resolve("tomorrow at 10am", language="english")
    assert res.date == (now + timedelta(days=1)).date()
    assert res.time == time(10, 0)

    res = await resolver.resolve("tomorrow at 3pm", language="english")
    assert res.time == time(15, 0)


@pytest.mark.asyncio
async def test_am_inside_a_word_does_not_mean_morning() -> None:
    resolver = CustomDateTimeResolver()

    res = await resolver.resolve("namaskaram, 5 മണി", language="malayalam")
    assert res.time == time(17, 0)

    res = await resolver.resolve("example 6 മണി", language="malayalam")
    assert res.time == time(18, 0)


@pytest.mark.asyncio
async def test_resolve_unrecognized() -> None:
    resolver = CustomDateTimeResolver()

    res = await resolver.resolve("random chatter with no dates", language="english")
    assert res.date is None
    assert res.time is None
    assert res.confidence == 0.0


@pytest.mark.parametrize(
    ("language", "utterance"),
    [
        ("hi-IN", "कल सुबह 10 बजे अपॉइंटमेंट चाहिए"),
        ("mr-IN", "उद्या सकाळी 10 वाजता हवे आहे"),
        ("bn-IN", "কাল সকাল ১০টায় অ্যাপয়েন্টমেন্ট চাই"),
        ("ta-IN", "நாளை காலை 10 மணிக்கு வேண்டும்"),
        ("te-IN", "రేపు ఉదయం 10 గంటలకు కావాలి"),
        ("kn-IN", "ನಾಳೆ ಬೆಳಗ್ಗೆ 10 ಗಂಟೆಗೆ ಬೇಕು"),
        ("gu-IN", "કાલે સવારે 10 વાગ્યે જોઈએ"),
        ("pa-IN", "ਕੱਲ੍ਹ ਸਵੇਰੇ 10 ਵਜੇ ਚਾਹੀਦਾ ਹੈ"),
    ],
)
@pytest.mark.asyncio
async def test_resolve_tomorrow_morning_in_each_language(
    language: str, utterance: str
) -> None:
    resolver = CustomDateTimeResolver()
    now = datetime.now(ZoneInfo("Asia/Kolkata"))

    res = await resolver.resolve(utterance, language=language)

    assert res.date == (now + timedelta(days=1)).date()
    assert res.time == time(10, 0)
    assert res.confidence >= 0.9


@pytest.mark.asyncio
async def test_resolve_hindi_day_after_tomorrow_evening() -> None:
    resolver = CustomDateTimeResolver()
    now = datetime.now(ZoneInfo("Asia/Kolkata"))

    res = await resolver.resolve("परसों शाम 5 बजे", language="hi-IN")

    assert res.date == (now + timedelta(days=2)).date()
    assert res.time == time(17, 0)


@pytest.mark.asyncio
async def test_resolve_hindi_half_hour() -> None:
    resolver = CustomDateTimeResolver()

    res = await resolver.resolve("साढ़े दस बजे", language="hi-IN")

    assert res.time == time(10, 30)


@pytest.mark.asyncio
async def test_resolve_native_digits() -> None:
    resolver = CustomDateTimeResolver()
    now = datetime.now(ZoneInfo("Asia/Kolkata"))

    res = await resolver.resolve("কাল সকাল ১০টায়", language="bn-IN")

    assert res.date == (now + timedelta(days=1)).date()
    assert res.time == time(10, 0)


@pytest.mark.asyncio
async def test_resolve_numeric_day_first_date() -> None:
    resolver = CustomDateTimeResolver()

    res = await resolver.resolve("6/11/2026 14:30", language="en-IN")

    assert res.date.isoformat() == "2026-11-06"
    assert res.time == time(14, 30)
