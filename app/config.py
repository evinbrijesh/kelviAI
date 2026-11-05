import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "agent.yaml"


class ConfigError(ValueError):
    """Raised when agent.yaml is missing, malformed, or has invalid placeholders."""


class AgentConfig(BaseModel):
    name: str
    language: str
    greeting: str
    persona: str
    rules: list[str]


class STTConfig(BaseModel):
    model: str
    language: str


class TTSConfig(BaseModel):
    model: str
    voice: str
    voices: dict[str, str] = Field(default_factory=dict)


class ModelConfig(BaseModel):
    provider: str
    stt: STTConfig
    tts: TTSConfig
    date_time_resolver: str


class ToolConfig(BaseModel):
    name: str
    description: str
    enabled: bool
    parameters: dict[str, Any] = Field(default_factory=dict)


class GnaniConfig(BaseModel):
    api_key_id: str
    base_url: str


class DatabaseConfig(BaseModel):
    url: str


class AppConfig(BaseModel):
    agent: AgentConfig
    model: ModelConfig
    tools: list[ToolConfig]
    gnani: GnaniConfig
    database: DatabaseConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gnai_api_key_id: str = ""
    database_url: str = "postgresql://vaanikit:vaanikit@localhost:5432/vaanikit"
    agent_config_path: str = ""
    seed_demo_data: bool = True


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"Configuration section '{name}' is missing or invalid")
    return value


def _substitute(section: dict[str, Any], field: str, placeholder: str, value: str) -> None:
    current = section.get(field)
    if not isinstance(current, str):
        raise ConfigError(f"Configuration field '{field}' is missing or invalid")
    section[field] = current.replace(placeholder, value)


def load_config(config_path: str | Path | None = None) -> AppConfig:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw_config: Any = yaml.safe_load(f)

    if not isinstance(raw_config, dict):
        raise ConfigError("Configuration file must contain a top-level mapping")

    settings = Settings()

    gnani_section = _section(raw_config, "gnani")
    database_section = _section(raw_config, "database")

    _substitute(gnani_section, "api_key_id", "${GNAI_API_KEY_ID}", settings.gnai_api_key_id)
    _substitute(database_section, "url", "${DATABASE_URL}", settings.database_url)

    try:
        return AppConfig(**raw_config)
    except ValidationError as e:
        logger.error("Configuration schema validation failed: %s", e)
        raise ConfigError("Invalid configuration schema") from None


def validate_config(config_path: str | Path | None = None) -> tuple[bool, str]:
    try:
        config = load_config(config_path)
        if not config.gnani.api_key_id:
            logger.warning("Configuration invalid: GNAI_API_KEY_ID is missing")
            return False, "GNAI_API_KEY_ID is not configured"
        if not config.database.url:
            logger.warning("Configuration invalid: DATABASE_URL is missing")
            return False, "DATABASE_URL is not configured"
        return True, "Configuration is valid"
    except FileNotFoundError:
        logger.warning("Configuration file not found: %s", config_path)
        return False, "Configuration file not found"
    except ConfigError:
        return False, "Invalid configuration"
    except Exception:
        logger.exception("Unexpected error while validating configuration")
        return False, "Configuration error"
