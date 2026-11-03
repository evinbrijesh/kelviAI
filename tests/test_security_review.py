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
