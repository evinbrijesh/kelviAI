from pathlib import Path

import pytest

from app.config import ConfigError, load_config, validate_config


def test_load_config_valid(tmp_path: Path) -> None:
    yaml_content = """
agent:
  name: "test-agent"
  language: "malayalam"
  greeting: "നമസ്കാരം"
  persona: "Assistant"
  rules:
    - "Rule 1"
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
gnani:
  api_key_id: "test-key"
  base_url: "https://api.vachana.ai"
database:
  url: "postgresql://user:pass@localhost:5432/db"
"""
    config_file = tmp_path / "test_agent.yaml"
    config_file.write_text(yaml_content, encoding="utf-8")

    config = load_config(config_file)
    assert config.agent.name == "test-agent"
    assert config.agent.greeting == "നമസ്കാരം"
    assert config.tools[0].name == "check_availability"
    assert "date" in config.tools[0].parameters["properties"]


def test_load_config_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_config("nonexistent_path.yaml")


def test_validate_config(tmp_path: Path) -> None:
    yaml_content = """
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
tools: []
gnani:
  api_key_id: ""
  base_url: "https://api.vachana.ai"
database:
  url: "postgresql://user:pass@localhost:5432/db"
"""
    config_file = tmp_path / "invalid_agent.yaml"
    config_file.write_text(yaml_content, encoding="utf-8")

    is_valid, msg = validate_config(config_file)
    assert not is_valid
    assert msg == "GNAI_API_KEY_ID is not configured"


MINIMAL_CONFIG = """
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
tools: []
database:
  url: "sqlite:///test.db"
"""


def _write(tmp_path: Path, content: str) -> Path:
    config_file = tmp_path / "agent.yaml"
    config_file.write_text(content, encoding="utf-8")
    return config_file


def test_missing_section_raises_config_error(tmp_path: Path) -> None:
    config_file = _write(tmp_path, MINIMAL_CONFIG)

    with pytest.raises(ConfigError, match="gnani"):
        load_config(config_file)


def test_non_string_api_key_raises_config_error(tmp_path: Path) -> None:
    gnani_section = '\ngnani:\n  api_key_id: null\n  base_url: "x"\n'
    config_file = _write(tmp_path, MINIMAL_CONFIG + gnani_section)

    with pytest.raises(ConfigError, match="api_key_id"):
        load_config(config_file)


def test_non_mapping_yaml_raises_config_error(tmp_path: Path) -> None:
    config_file = _write(tmp_path, "- just\n- a list\n")

    with pytest.raises(ConfigError):
        load_config(config_file)


def test_validate_config_reports_invalid_without_leaking_details(tmp_path: Path) -> None:
    config_file = _write(tmp_path, MINIMAL_CONFIG)

    is_valid, msg = validate_config(config_file)
    assert not is_valid
    assert msg == "Invalid configuration"
