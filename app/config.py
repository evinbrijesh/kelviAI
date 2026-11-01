import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


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
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gnai_api_key_id: str = ""
    database_url: str = "postgresql://vaanikit:vaanikit@localhost:5432/vaanikit"


def load_config(config_path: str | Path = "agent.yaml") -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, encoding="utf-8") as f:
        raw_config: dict[str, Any] = yaml.safe_load(f)

    settings = Settings()

    raw_config["gnani"]["api_key_id"] = raw_config["gnani"]["api_key_id"].replace(
        "${GNAI_API_KEY_ID}", settings.gnai_api_key_id
    )
    raw_config["database"]["url"] = raw_config["database"]["url"].replace(
        "${DATABASE_URL}", settings.database_url
    )

    try:
        return AppConfig(**raw_config)
    except ValidationError as e:
        logger.error("Configuration schema validation failed: %s", e)
        raise ValueError("Invalid configuration schema") from None


def validate_config(config_path: str | Path = "agent.yaml") -> tuple[bool, str]:
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
    except ValueError:
        return False, "Invalid configuration schema"
    except Exception:
        logger.exception("Unexpected error while validating configuration")
        return False, "Configuration error"
