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
async def test_resolve_unrecognized() -> None:
    resolver = CustomDateTimeResolver()

    res = await resolver.resolve("random chatter with no dates", language="english")
    assert res.date is None
    assert res.time is None
    assert res.confidence == 0.0
