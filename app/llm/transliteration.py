from __future__ import annotations

# Malayalam mappings
_ML_INDEPENDENT_VOWELS: dict[str, str] = {
    "അ": "a", "ആ": "aa", "ഇ": "i", "ഈ": "ee",
    "ഉ": "u", "ഊ": "oo", "ഋ": "ri", "എ": "e",
    "ഏ": "e", "ഐ": "ai", "ഒ": "o", "ഓ": "o", "ഔ": "au",
}

_ML_CONSONANTS: dict[str, str] = {
    "ക": "k", "ഖ": "kh", "ഗ": "g", "ഘ": "gh", "ങ": "ng",
    "ച": "ch", "ഛ": "chh", "ജ": "j", "ഝ": "jh", "ഞ": "ny",
    "ട": "t", "ഠ": "th", "ഡ": "d", "ഢ": "dh", "ണ": "n",
    "ത": "th", "ഥ": "thh", "ദ": "d", "ധ": "dh", "ന": "n",
    "പ": "p", "ഫ": "ph", "ബ": "b", "ഭ": "bh", "മ": "m",
    "യ": "y", "ര": "r", "ല": "l", "വ": "v",
    "ശ": "sh", "ഷ": "sh", "സ": "s", "ഹ": "h",
    "ള": "l", "ഴ": "zh", "റ": "r",
}

_ML_CONJUNCTS: dict[str, str] = {
    "റ്റ": "tt",
    "ന്റ": "nt",
    "ൻ്റ": "nt",
    "സ\u0D4Dറ\u0D4Dറ": "st",
    "സ\u0D4Dട": "st",
    "ഷ\u0D4Dട": "sht",
    "ഞ\u0D4Dച": "nch",
    "ണ\u0D4Dട": "nd",
    "മ\u0D4Dപ": "mb",
    "ങ\u0D4Dക": "nk",
    "ങ\u0D4Dങ": "ng",
    "ണ\u0D4Dണ": "nn",
    "ന\u0D4Dന": "nn",
    "മ\u0D4Dമ": "mm",
    "പ\u0D4Dപ": "pp",
    "ക\u0D4Dക": "kk",
    "ച\u0D4Dച": "ch",
    "ത\u0D4Dത": "th",
    "ല\u0D4Dല": "ll",
}

_ML_VOWEL_SIGNS: dict[str, str] = {
    "ാ": "aa", "ി": "i", "ീ": "ee", "ു": "u", "ൂ": "oo",
    "ൃ": "ri", "െ": "e", "േ": "e", "ൈ": "ai", "ൊ": "o",
    "ോ": "o", "ൌ": "au", "ൗ": "au",
}

_ML_CHILLUS: dict[str, str] = {
    "ൺ": "n", "ൻ": "n", "ർ": "r", "ൽ": "l", "ൾ": "l", "ൿ": "k",
}

# Hindi / Devanagari mappings
_HI_INDEPENDENT_VOWELS: dict[str, str] = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee",
    "उ": "u", "ऊ": "oo", "ऋ": "ri", "ए": "e",
    "ऐ": "ai", "ओ": "o", "औ": "au",
}

_HI_CONSONANTS: dict[str, str] = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
}

_HI_VOWEL_SIGNS: dict[str, str] = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo",
    "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
}


def transliterate_malayalam(text: str) -> str:
    """Convert Malayalam script into phonetic Romanized Manglish."""
    out: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        # Check conjuncts first (longest match first)
        matched_conjunct = False
        for cj_len in (3, 2, 1):
            if i + cj_len <= n:
                sub = text[i : i + cj_len]
                if sub in _ML_CONJUNCTS:
                    base = _ML_CONJUNCTS[sub]
                    i += cj_len
                    if i < n and text[i] == "്":  # Virama
                        out.append(base)
                        i += 1
                    elif i < n and text[i] in _ML_VOWEL_SIGNS:
                        out.append(base + _ML_VOWEL_SIGNS[text[i]])
                        i += 1
                    else:
                        out.append(base + "a")
                    matched_conjunct = True
                    break
        if matched_conjunct:
            continue

        ch = text[i]

        # Independent vowels
        if ch in _ML_INDEPENDENT_VOWELS:
            out.append(_ML_INDEPENDENT_VOWELS[ch])
            i += 1
            continue

        # Chillus
        if ch in _ML_CHILLUS:
            out.append(_ML_CHILLUS[ch])
            i += 1
            continue

        # Anusvara & Visarga
        if ch == "ം":
            out.append("m")
            i += 1
            continue
        if ch == "ഃ":
            out.append("h")
            i += 1
            continue

        # Consonants
        if ch in _ML_CONSONANTS:
            base = _ML_CONSONANTS[ch]
            if i + 1 < n:
                nxt = text[i + 1]
                if nxt == "്":  # Virama
                    out.append(base)
                    i += 2
                    continue
                if nxt in _ML_VOWEL_SIGNS:
                    out.append(base + _ML_VOWEL_SIGNS[nxt])
                    i += 2
                    continue
            out.append(base + "a")
            i += 1
            continue

        # Other characters
        out.append(ch)
        i += 1

    result = "".join(out)
    result = result.replace("aa", "a").replace("ee", "i").replace("oo", "u")
    return result


def transliterate_devanagari(text: str) -> str:
    """Convert Devanagari script into phonetic Romanized Hinglish."""
    out: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        if ch in _HI_INDEPENDENT_VOWELS:
            out.append(_HI_INDEPENDENT_VOWELS[ch])
            i += 1
            continue

        if ch in ("ं", "ँ"):
            out.append("n")
            i += 1
            continue
        if ch == "ः":
            out.append("h")
            i += 1
            continue

        if ch in _HI_CONSONANTS:
            base = _HI_CONSONANTS[ch]
            if i + 1 < n:
                nxt = text[i + 1]
                if nxt == "्":  # Virama
                    out.append(base)
                    i += 2
                    continue
                if nxt in _HI_VOWEL_SIGNS:
                    out.append(base + _HI_VOWEL_SIGNS[nxt])
                    i += 2
                    continue
            out.append(base + "a")
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def transliterate_indic(text: str, language: str | None = None) -> str:
    """Transliterate Indic text to phonetic Latin script."""
    if not text:
        return ""

    has_malayalam = any("\u0D00" <= ch <= "\u0D7F" for ch in text)
    if has_malayalam or (language and language.startswith("ml")):
        return transliterate_malayalam(text)

    has_devanagari = any("\u0900" <= ch <= "\u097F" for ch in text)
    if has_devanagari or (language and language.startswith("hi")):
        return transliterate_devanagari(text)

    return text
