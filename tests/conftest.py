from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app

TEST_AGENT_CONFIG = """
agent:
  name: "test-agent"
  language: "malayalam"
  greeting: "നമസ്കാരം"
  persona: "Assistant"
  rules: []
model:
  provider: "gnani"
  stt:
    model: "prisma-v3.0"
    language: "ml-IN"
  tts:
    model: "timbre-v2.5"
    voice: "default"
  date_time_resolver: "custom"
tools:
  - name: "check_availability"
    description: "Check slots"
    enabled: true
    parameters:
      type: "object"
      properties:
        date:
          type: "string"
      required: ["date"]
  - name: "book_slot"
    description: "Book a slot"
    enabled: true
gnani:
  api_key_id: "test-key"
  base_url: "https://api.vachana.ai"
database:
  url: "{database_url}"
"""


@pytest.fixture
def agent_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    config_path = tmp_path / "agent.yaml"
    config_path.write_text(
        TEST_AGENT_CONFIG.format(database_url=database_url), encoding="utf-8"
    )
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("SEED_DEMO_DATA", "true")
    return config_path


@pytest_asyncio.fixture
async def client(agent_config: Path) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as async_client:
            yield async_client
