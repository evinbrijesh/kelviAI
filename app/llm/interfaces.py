from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


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
    date: datetime | None
    time: datetime | None
    timezone: str
    confidence: float
    explanation: str


class STTAdapter(ABC):
    @abstractmethod
    async def transcribe(
        self, audio: bytes, mode: STTMode = STTMode.REST, **kwargs
    ) -> STTResult:
        pass


class TTSAdapter(ABC):
    @abstractmethod
    async def synthesize(
        self, text: str, mode: TTSMode = TTSMode.REST, **kwargs
    ) -> TTSResult:
        pass


class DateTimeResolver(ABC):
    @abstractmethod
    async def resolve(self, text: str, language: str, context: dict | None = None) -> DateTimeResolution:
        pass
