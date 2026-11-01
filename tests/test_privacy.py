import pytest

from app.privacy import mask_phone


@pytest.mark.parametrize(
    ("phone", "expected"),
    [
        ("+919000000001", "+********0001"),
        ("9000000001", "******0001"),
        ("+1 (900) 000-0001", "+*******0001"),
        ("1234", "****"),
        ("", "***"),
        ("not-a-number", "***"),
    ],
)
def test_mask_phone(phone: str, expected: str) -> None:
    assert mask_phone(phone) == expected


def test_mask_phone_never_leaks_middle_digits() -> None:
    masked = mask_phone("+919876543210")
    assert "98765" not in masked
    assert masked.endswith("3210")
