def mask_phone(phone: str) -> str:
    """Keep a leading + and the last four digits; mask everything else."""
    raw = (phone or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return "***"
    if len(digits) <= 4:
        return "*" * len(digits)
    masked = "*" * (len(digits) - 4) + digits[-4:]
    return ("+" if raw.startswith("+") else "") + masked
