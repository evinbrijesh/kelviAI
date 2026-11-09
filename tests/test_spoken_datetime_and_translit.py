from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.agent.spoken_datetime import (
    format_spoken_date,
    format_spoken_slot,
    format_spoken_time,
)
from app.llm.transliteration import (
    transliterate_devanagari,
    transliterate_indic,
    transliterate_malayalam,
)

TZ = ZoneInfo("Asia/Kolkata")


def test_spoken_time_formatting() -> None:
    # Morning
    assert "രാവിലെ" in format_spoken_time("09:30", language="ml-IN")
    assert "09:30" in format_spoken_time("09:30", language="ml-IN")
    assert "सुबह" in format_spoken_time("10:00", language="hi-IN")
    assert "10:00 AM" == format_spoken_time("10:00", language="en-IN")

    # Afternoon
    assert "ഉച്ചയ്ക്ക്" in format_spoken_time(time(14, 0), language="ml-IN")
    assert "दोपहर" in format_spoken_time("14:30", language="hi-IN")
    assert "2:00 PM" == format_spoken_time(time(14, 0), language="en-IN")

    # Evening & Night
    assert "വൈകുന്നേരം" in format_spoken_time("17:30", language="ml-IN")
    assert "രാത്രി" in format_spoken_time("21:00", language="ml-IN")


def test_spoken_date_formatting() -> None:
    ref = date(2026, 11, 9)

    # Today
    today_str = format_spoken_date(date(2026, 11, 9), language="ml-IN", base_date=ref)
    assert "ഇന്ന്" in today_str
    assert "നവംബർ" in today_str

    # Tomorrow
    tomorrow_str = format_spoken_date(date(2026, 11, 10), language="ml-IN", base_date=ref)
    assert "നാളെ" in tomorrow_str
    assert "നവംബർ 10" in tomorrow_str

    # Day after tomorrow
    day_after = format_spoken_date(date(2026, 11, 11), language="ml-IN", base_date=ref)
    assert "മറ്റന്നാൾ" in day_after

    # Other dates
    other = format_spoken_date(date(2026, 12, 25), language="ml-IN", base_date=ref)
    assert "ഡിസംബർ 25" in other

    # Hindi
    hi_tomorrow = format_spoken_date(date(2026, 11, 10), language="hi-IN", base_date=ref)
    assert "कल" in hi_tomorrow
    assert "नवंबर" in hi_tomorrow


def test_spoken_slot_formatting() -> None:
    slot_iso = "2026-11-10T10:00:00+05:30"
    ml_slot = format_spoken_slot(slot_iso, language="ml-IN")
    assert "നവംബർ 10" in ml_slot
    assert "രാവിലെ 10:00" in ml_slot

    dt = datetime(2026, 11, 10, 15, 30, tzinfo=TZ)
    hi_slot = format_spoken_slot(dt, language="hi-IN")
    assert "नवंबर" in hi_slot
    assert "दोपहर 15:30 बजे" in hi_slot


def test_malayalam_transliteration() -> None:
    t1 = transliterate_malayalam("നമസ്കാരം, ഞാൻ കേൾവി AI അസിസ്റ്റന്റ് ആണ്.")
    assert "namaskaram" in t1.lower()
    assert "kelvi" in t1.lower()

    t2 = transliterate_malayalam("മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ് എന്ന പേരിൽ ബുക്ക് ചെയ്തോളൂ")
    assert "misttar" in t2.lower()
    assert "peril" in t2.lower()
    assert "bukk" in t2.lower()


def test_devanagari_transliteration() -> None:
    t = transliterate_devanagari("नमस्ते, मैं केल्वी एआई सहायक हूँ।")
    assert "namaste" in t.lower()
    assert "sahaayak" in t.lower()


def test_transliterate_indic_auto() -> None:
    res = transliterate_indic("എനിക്ക് നാളെ അപ്പോയിൻമെൻറ്റ് വേണം")
    assert "nale" in res.lower()
    assert "venam" in res.lower()

    # Plain ASCII unchanged
    assert transliterate_indic("Hello world") == "Hello world"
