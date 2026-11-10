from kelvi import (
    clean_discourse_markers,
    detect_language,
    format_spoken_date,
    format_spoken_time,
    normalize_language,
    transliterate_indic,
)


def test_clean_discourse_markers_malayalam():
    assert clean_discourse_markers("ജോൺസൺ എന്നാട്ടോ", "ml-IN") == "ജോൺസൺ"
    assert clean_discourse_markers("എന്റെ പേര് രാഹുൽ ആണട്ടോ", "ml-IN") == "എന്റെ പേര് രാഹുൽ"
    assert clean_discourse_markers("Rahul ennatto", "ml-IN") == "Rahul"
    assert clean_discourse_markers("Suresh ketto", "ml-IN") == "Suresh"


def test_clean_discourse_markers_hindi():
    assert clean_discourse_markers("Rahul bhaiya", "hi-IN") == "Rahul"
    assert clean_discourse_markers("सुनील जी", "hi-IN") == "सुनील"


def test_detect_and_normalize_language():
    assert normalize_language("malayalam") == "ml-IN"
    assert normalize_language("hindi") == "hi-IN"
    assert normalize_language("manglish") == "ml-IN"
    assert detect_language("നാളെ രാവിലെ പത്ത് മണിക്ക്") == "ml-IN"
    assert detect_language("कल सुबह दस बजे") == "hi-IN"


def test_transliterate_indic():
    assert transliterate_indic("നന്ദി") == "nandi"
    assert transliterate_indic("नमस्ते") == "namaste"


def test_format_spoken_datetime():
    time_str = format_spoken_time("10:30", language="ml-IN")
    assert "രാവിലെ" in time_str or "10:30" in time_str

    date_str = format_spoken_date("2026-11-12", language="ml-IN")
    assert date_str is not None
