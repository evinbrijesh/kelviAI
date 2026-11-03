import re
from pathlib import Path

from sqlalchemy import select

from app.db.models import Booking, Calendar, Call
from app.db.seed import DEMO_CLINIC_NAME, seed_demo_data
from app.db.session import Database

SYNTHETIC_PHONE = re.compile(r"^\+9190000000\d{2}$")
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".ogg"}


def test_seed_contains_only_synthetic_people_and_clinic(database: Database) -> None:
    with database.session() as session:
        assert seed_demo_data(session) is True

    with database.session() as session:
        call_phones = set(session.scalars(select(Call.caller_phone)))
        booking_phones = set(session.scalars(select(Booking.caller_phone)))
        phones = call_phones | booking_phones

        assert phones
        assert all(SYNTHETIC_PHONE.match(phone) for phone in phones)

        clinic = session.scalars(select(Calendar)).one()
        assert clinic.name == DEMO_CLINIC_NAME
        assert "synthetic demo" in clinic.name

        bookings = session.scalars(select(Booking)).all()
        assert all(booking.notes == "Synthetic demo booking" for booking in bookings)


def test_repository_contains_no_audio_recordings() -> None:
    root = Path(__file__).resolve().parents[1]
    audio = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in AUDIO_SUFFIXES
        and ".venv" not in path.parts
    ]
    assert audio == []
