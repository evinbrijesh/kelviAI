from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.calls.session_log import start_call
from app.config import Settings
from app.db.models import Calendar
from app.main import app
from app.tools.booking import build_tool_registry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Kolkata")


def next_working_day() -> date:
    day = datetime.now(TZ).date() + timedelta(days=1)
    while day.weekday() > 4:
        day += timedelta(days=1)
    return day


def test_env_example_bootstraps_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GNAI_API_KEY_ID", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings(_env_file=PROJECT_ROOT / ".env.example")

    assert settings.gnai_api_key_id == "your_gnani_api_key_here"
    assert settings.database_url.startswith("postgresql://")
    assert settings.seed_demo_data is True


@pytest.mark.asyncio
async def test_clean_machine_bootstrap_and_first_booking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "clean.db"
    assert not database_path.exists()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("GNAI_API_KEY_ID", "clean-machine-placeholder")
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(PROJECT_ROOT / "agent.yaml"))
    monkeypatch.setenv("SEED_DEMO_DATA", "true")

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json()["database"] == "ok"

            status = (await client.get("/admin/status")).json()
            assert status["calendars"] == 1
            assert status["calls"] == 5
            assert status["bookings"] == 3

        database = app.state.database
        config = app.state.config
        assert database_path.exists()

        with database.session() as session:
            assert session.scalar(select(func.count()).select_from(Calendar)) == 1
            log = start_call(
                session,
                call_sid="clean-machine-call",
                caller_phone="+919000000077",
                language="malayalam",
            )
            registry = build_tool_registry(session, config.tools, call=log.call)
            result = await registry.invoke(
                "book_slot",
                {
                    "caller_name": "Clean Machine Caller",
                    "date": next_working_day().isoformat(),
                    "time": "14:00",
                },
            )

            assert result["status"] == "confirmed"
            assert result["clinic"].startswith("Nila Family Clinic")
