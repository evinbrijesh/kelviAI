from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.db.models import Booking, BookingStatus, Calendar, Call
from app.db.seed import seed_demo_data
from app.db.session import Database, normalize_database_url


def make_db(tmp_path: Path) -> Database:
    database = Database(f"sqlite:///{(tmp_path / 'unit.db').as_posix()}")
    database.create_schema()
    return database


def test_normalize_database_url() -> None:
    assert normalize_database_url("postgresql://u:p@h:5432/d") == "postgresql+psycopg://u:p@h:5432/d"
    assert normalize_database_url("postgres://u:p@h:5432/d") == "postgresql+psycopg://u:p@h:5432/d"
    assert normalize_database_url("postgresql+psycopg://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert normalize_database_url("sqlite:///local.db") == "sqlite:///local.db"


def test_seed_is_idempotent(tmp_path: Path) -> None:
    database = make_db(tmp_path)

    with database.session() as session:
        assert seed_demo_data(session) is True
    with database.session() as session:
        assert seed_demo_data(session) is False
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Calendar)) == 1
        assert session.scalar(select(func.count()).select_from(Call)) == 5
        assert session.scalar(select(func.count()).select_from(Booking)) == 3

    database.dispose()


def test_database_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = make_db(tmp_path)
    assert database.check() is True

    def unavailable(*args: object, **kwargs: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("database is down"))

    monkeypatch.setattr(database.engine, "connect", unavailable)
    assert database.check() is False
    database.dispose()


def test_confirmed_booking_slot_is_unique(tmp_path: Path) -> None:
    database = make_db(tmp_path)

    with database.session() as session:
        seed_demo_data(session)
        calendar = session.scalars(select(Calendar)).first()
        booking = session.scalars(select(Booking)).first()
        assert calendar is not None and booking is not None
        calendar_id = calendar.id
        slot_start = booking.slot_start
        slot_end = booking.slot_end

    with pytest.raises(IntegrityError):
        with database.session() as session:
            session.add(
                Booking(
                    calendar_id=calendar_id,
                    patient_name="Duplicate Patient",
                    caller_phone="+919000000009",
                    slot_start=slot_start,
                    slot_end=slot_end,
                    status=BookingStatus.CONFIRMED,
                )
            )

    database.dispose()


def test_cancelled_booking_frees_the_slot(tmp_path: Path) -> None:
    database = make_db(tmp_path)

    with database.session() as session:
        seed_demo_data(session)

    with database.session() as session:
        cancelled = session.scalars(select(Booking)).first()
        assert cancelled is not None
        cancelled.status = BookingStatus.CANCELLED
        calendar_id = cancelled.calendar_id
        slot_start = cancelled.slot_start
        slot_end = cancelled.slot_end

    with database.session() as session:
        session.add(
            Booking(
                calendar_id=calendar_id,
                patient_name="Replacement Patient",
                caller_phone="+919000000010",
                slot_start=slot_start,
                slot_end=slot_end,
                status=BookingStatus.CONFIRMED,
            )
        )
        session.flush()

    database.dispose()
