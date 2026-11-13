import re
import subprocess
from pathlib import Path

import pytest
from httpx import AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
SKIP_FILES = {".env"}
TEXT_SUFFIXES = {
    ".css",
    ".example",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
PLACEHOLDERS = {"your_gnani_api_key_here", "test-key", "clean-machine-placeholder"}
SECRET_ASSIGNMENT = re.compile(
    r"""(?ix)
    (?:gnai_api_key_id|api[_-]?key|secret|access[_-]?token|auth[_-]?token)
    \s*[:=]\s*
    ["']?([A-Za-z0-9_\-]{20,})
    """
)


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return [PROJECT_ROOT / line for line in result.stdout.splitlines() if line]
    return [
        path
        for path in PROJECT_ROOT.rglob("*")
        if path.is_file() and not (SKIP_DIRS & set(path.parts))
    ]


def test_env_file_is_git_ignored() -> None:
    ignore_rules = {
        line.strip()
        for line in (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    }
    assert ".env" in ignore_rules

    if (PROJECT_ROOT / ".git").exists():
        result = subprocess.run(
            ["git", "check-ignore", "-q", ".env"],
            cwd=PROJECT_ROOT,
            check=False,
        )
        assert result.returncode == 0, ".env must never be tracked by git"
        assert ".env" not in {path.name for path in tracked_files()}


def test_env_example_contains_placeholders_only() -> None:
    values = {}
    for line in (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

    assert values["GNAI_API_KEY_ID"] == "your_gnani_api_key_here"
    assert values["DATABASE_URL"].startswith("postgresql://")


def test_no_secret_values_are_committed() -> None:
    offenders: list[str] = []
    for path in tracked_files():
        if path.name in SKIP_FILES or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for match in SECRET_ASSIGNMENT.finditer(text):
            if match.group(1) not in PLACEHOLDERS:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {match.group(0)}")

    assert offenders == []


@pytest.mark.asyncio
async def test_admin_responses_mask_caller_phone_numbers(client: AsyncClient) -> None:
    raw_digits = {"9000000001", "9000000002", "9000000003", "9000000004"}
    for url in ("/admin/calls", "/admin/bookings", "/admin/calls/1"):
        response = await client.get(url)
        assert response.status_code == 200
        assert not any(digits in response.text for digits in raw_digits)
        assert "****" in response.text


@pytest.mark.asyncio
async def test_privacy_status_is_reported_by_the_admin_page(client: AsyncClient) -> None:
    status = (await client.get("/admin/status")).json()
    assert status["phone_masking"] == "enabled"
    assert status["recordings"] == "disabled"
    assert status["environment"] == "non-production"

    page = (await client.get("/admin/ui")).text
    assert "non-production" in page
    assert "Synthetic demo data only" in page
    assert "not production secure" in page


def test_twilio_provider_escapes_xml_attributes() -> None:
    from app.providers.telephony import TwilioProvider

    provider = TwilioProvider()
    malicious_action = '/webhook?CallSid=123" numDigits="1"><Say>Pwned</Say><!--'
    twiml = provider.format_response(
        "Greeting",
        listen_for_input=True,
        action_url=malicious_action,
        language='en" injection="true',
    )
    # Double quotes must be escaped to &quot; and not remain raw
    expected_attr = (
        'action="/webhook?CallSid=123&quot; numDigits=&quot;1&quot;&gt;'
        "&lt;Say&gt;Pwned&lt;/Say&gt;&lt;!--\""
    )
    assert expected_attr in twiml
    assert '<Say>Pwned</Say>' not in twiml
    assert 'language="en&quot; injection=&quot;true"' in twiml


@pytest.mark.asyncio
async def test_twilio_webhook_rejects_malformed_call_sid(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/voice/webhook/twilio",
        content='CallSid=bad"sid&From=+919000000001',
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_twilio_webhook_verifies_signature_when_configured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-secret-token-12345")

    # Request without signature should fail
    resp = await client.post(
        "/api/voice/webhook/twilio",
        content="CallSid=valid-sid&From=+919000000001",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cancel_booking_enforces_caller_authorization() -> None:
    from datetime import UTC, datetime, timedelta

    from app.db.models import Booking, BookingStatus, Calendar, Call
    from app.db.session import Database
    from app.tools.booking import BookingTools


    db = Database("sqlite:///:memory:")
    db.create_schema()

    with db.session() as session:
        cal = Calendar(name="Auth Test Clinic", is_active=True, working_days="0,1,2,3,4,5,6")
        session.add(cal)
        session.flush()

        slot_start = datetime.now(UTC) + timedelta(days=2)
        slot_end = slot_start + timedelta(minutes=30)

        # Create booking for caller A
        booking = Booking(
            calendar_id=cal.id,
            patient_name="Patient A",
            caller_phone="+919000000001",
            slot_start=slot_start,
            slot_end=slot_end,
            status=str(BookingStatus.CONFIRMED),
        )
        session.add(booking)
        session.flush()
        booking_id = booking.id

        # Caller B attempts to cancel caller A's booking
        caller_b = Call(call_sid="call-b", caller_phone="+919000000099", language="en-IN")
        session.add(caller_b)
        session.flush()

        tools = BookingTools(session, call=caller_b)
        res = await tools.cancel_booking({"booking_id": booking_id})
        assert res["status"] == "unauthorized"

        # Caller A successfully cancels their own booking
        caller_a = Call(call_sid="call-a", caller_phone="+919000000001", language="en-IN")
        session.add(caller_a)
        session.flush()

        tools_a = BookingTools(session, call=caller_a)
        res_a = await tools_a.cancel_booking({"booking_id": booking_id})
        assert res_a["status"] == "cancelled"


@pytest.mark.asyncio
async def test_oversized_audio_payload_is_rejected(client: AsyncClient) -> None:
    # 11 MB payload exceeding MAX_AUDIO_BYTES (10 MB)
    resp = await client.post(
        "/api/voice/session/call-dummy/turn",
        headers={"content-type": "audio/wav", "content-length": str(11 * 1024 * 1024)},
        content=b"",
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_security_headers_present_on_responses(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_admin_dashboard_always_accessible(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_API_KEY", "secret-admin-pass-12345")
    resp = await client.get("/admin/calls")
    assert resp.status_code == 200


