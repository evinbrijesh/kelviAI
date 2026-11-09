from __future__ import annotations

import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Kolkata")

_MALAYALAM_MONTHS = {
    1: "ജനുവരി",
    2: "ഫെബ്രുവരി",
    3: "മാർച്ച്",
    4: "ഏപ്രിൽ",
    5: "മെയ്",
    6: "ജൂൺ",
    7: "ജൂലൈ",
    8: "ഓഗസ്റ്റ്",
    9: "സെപ്റ്റംബർ",
    10: "ഒക്ടോബർ",
    11: "നവംബർ",
    12: "ഡിസംബർ",
}

_HINDI_MONTHS = {
    1: "जनवरी",
    2: "फ़रवरी",
    3: "मार्च",
    4: "अप्रैल",
    5: "मई",
    6: "जून",
    7: "जुलाई",
    8: "अगस्त",
    9: "सितंबर",
    10: "अक्टूबर",
    11: "नवंबर",
    12: "दिसंबर",
}

_ENGLISH_MONTHS = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


def _parse_time_parts(time_val: time | str) -> tuple[int, int]:
    if isinstance(time_val, time):
        return time_val.hour, time_val.minute
    clean = str(time_val).strip()
    match = re.match(r"(\d{1,2}):(\d{2})", clean)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 10, 0


def format_spoken_time(time_val: time | str, language: str = "ml-IN") -> str:
    """Format time into a natural spoken Indic or English phrasing."""
    hour, minute = _parse_time_parts(time_val)
    time_str = f"{hour:02d}:{minute:02d}"

    if language.startswith("ml"):
        if 5 <= hour < 12:
            period = "രാവിലെ"
        elif 12 <= hour < 16:
            period = "ഉച്ചയ്ക്ക്"
        elif 16 <= hour < 20:
            period = "വൈകുന്നേരം"
        else:
            period = "രാത്രി"
        return f"{period} {time_str}"

    if language.startswith("hi"):
        if 5 <= hour < 12:
            period = "सुबह"
        elif 12 <= hour < 16:
            period = "दोपहर"
        elif 16 <= hour < 20:
            period = "शाम"
        else:
            period = "रात"
        return f"{period} {time_str} बजे"

    # English / fallback
    suffix = "AM" if hour < 12 else "PM"
    disp_h = hour if 1 <= hour <= 12 else (hour - 12 if hour > 12 else 12)
    return f"{disp_h}:{minute:02d} {suffix}"


def format_spoken_date(
    date_val: date | str,
    language: str = "ml-IN",
    base_date: date | None = None,
) -> str:
    """Format calendar date into natural spoken Indic phrasing."""
    if isinstance(date_val, str):
        try:
            d = datetime.fromisoformat(date_val[:10]).date()
        except ValueError:
            return date_val
    else:
        d = date_val

    ref_date = base_date or datetime.now(TZ).date()
    delta_days = (d - ref_date).days

    if language.startswith("ml"):
        m_name = _MALAYALAM_MONTHS.get(d.month, str(d.month))
        if delta_days == 0:
            return f"ഇന്ന് ({m_name} {d.day})"
        if delta_days == 1:
            return f"നാളെ ({m_name} {d.day})"
        if delta_days == 2:
            return f"മറ്റന്നാൾ ({m_name} {d.day})"
        return f"{m_name} {d.day}"

    if language.startswith("hi"):
        m_name = _HINDI_MONTHS.get(d.month, str(d.month))
        if delta_days == 0:
            return f"आज ({d.day} {m_name})"
        if delta_days == 1:
            return f"कल ({d.day} {m_name})"
        return f"{d.day} {m_name}"

    m_name = _ENGLISH_MONTHS.get(d.month, str(d.month))
    if delta_days == 0:
        return f"today ({d.day} {m_name})"
    if delta_days == 1:
        return f"tomorrow ({d.day} {m_name})"
    return f"{d.day} {m_name}"


def format_spoken_slot(
    dt_or_date: date | datetime | str,
    time_val: time | str | None = None,
    language: str = "ml-IN",
) -> str:
    """Format complete appointment slot into natural spoken sentence."""
    if isinstance(dt_or_date, str) and "T" in dt_or_date:
        try:
            parsed = datetime.fromisoformat(dt_or_date)
            d = parsed.date()
            t: time | str = parsed.time()
        except ValueError:
            return dt_or_date
    elif isinstance(dt_or_date, datetime):
        d = dt_or_date.date()
        t = dt_or_date.time()
    elif isinstance(dt_or_date, date):
        d = dt_or_date
        t = time_val or "10:00"
    else:
        return str(dt_or_date)

    spoken_d = format_spoken_date(d, language=language)
    spoken_t = format_spoken_time(t, language=language)

    if language.startswith("ml"):
        return f"{spoken_d} {spoken_t}"
    if language.startswith("hi"):
        return f"{spoken_d} {spoken_t}"
    return f"{spoken_d} at {spoken_t}"
