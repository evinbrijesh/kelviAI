from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, time
from enum import Enum
from typing import Any


class STTMode(Enum):
    REST = "rest"
    REALTIME = "realtime"
    BATCH = "batch"


class TTSMode(Enum):
    REST = "rest"
    STREAMING = "streaming"
    REALTIME = "realtime"


@dataclass
class STTResult:
    text: str
    language: str
    confidence: float
    duration_ms: int


@dataclass
class TTSResult:
    audio: bytes
    format: str
    sample_rate: int


@dataclass
class DateTimeResolution:
    date: date | None
    time: time | None
    timezone: str
    confidence: float
    explanation: str


class STTAdapter(ABC):
    @abstractmethod
    async def transcribe(
        self, audio: bytes, mode: STTMode = STTMode.REST, **kwargs: Any
    ) -> STTResult:
        pass


class TTSAdapter(ABC):
    @abstractmethod
    async def synthesize(
        self, text: str, mode: TTSMode = TTSMode.REST, **kwargs: Any
    ) -> TTSResult:
        pass


class DateTimeResolver(ABC):
    @abstractmethod
    async def resolve(
        self, text: str, language: str, context: dict[str, Any] | None = None
    ) -> DateTimeResolution:
        pass
