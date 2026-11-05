import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.agent.session import AgentSession, AgentState
from app.bridge.audio_utils import (
    AudioValidationError,
    validate_audio_bytes,
    wrap_pcm_in_wav,
)
from app.config import AppConfig
from app.llm.interfaces import DateTimeResolver, STTAdapter, TTSAdapter
from app.llm.language import resolve_language

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceTurnResult:
    caller_transcript: str
    agent_reply: str
    audio: bytes
    sample_rate: int
    audio_format: str
    state: AgentState
    is_terminal: bool
    language: str
    booking_id: str | None = None
    latencies_ms: dict[str, float] = field(default_factory=dict)


class VoiceSession:
    """Bridges audio I/O with conversational AgentSession, Gnani STT, and Gnani TTS."""

    def __init__(
        self,
        agent_session: AgentSession,
        stt_adapter: STTAdapter,
        tts_adapter: TTSAdapter,
        *,
        default_language: str = "indic-auto",
    ) -> None:
        self.agent_session = agent_session
        self.stt = stt_adapter
        self.tts = tts_adapter
        self.default_language = default_language
        self.latest_audio: bytes | None = None

    @property
    def call_sid(self) -> str:
        return self.agent_session.call_sid

    @property
    def state(self) -> AgentState:
        return self.agent_session.state

    @property
    def language(self) -> str:
        return self.agent_session.language

    async def start(self, *, emit_greeting: bool = True) -> VoiceTurnResult:
        """Start agent session, synthesize greeting, and commit initial turn."""
        greeting_text = self.agent_session.start(emit_greeting=emit_greeting)

        t_start = time.perf_counter()
        tts_result = await self.tts.synthesize(
            greeting_text, language=self.agent_session.language
        )
        tts_ms = round((time.perf_counter() - t_start) * 1000, 2)
        self.latest_audio = tts_result.audio

        # Persist initial call turn to DB so admin dashboard reflects it immediately
        self.agent_session.session.commit()

        return VoiceTurnResult(
            caller_transcript="",
            agent_reply=greeting_text,
            audio=tts_result.audio,
            sample_rate=tts_result.sample_rate,
            audio_format=tts_result.format,
            state=self.agent_session.state,
            is_terminal=False,
            language=self.agent_session.language,
            booking_id=None,
            latencies_ms={"tts_ms": tts_ms},
        )

    async def process_turn(
        self,
        audio_bytes: bytes,
        *,
        language: str | None = None,
        **kwargs: Any,
    ) -> VoiceTurnResult:
        """Transcribe caller audio, drive agent session, and synthesize speech reply."""
        lang = language or self.default_language

        is_valid, diag = validate_audio_bytes(audio_bytes)
        if not is_valid:
            logger.warning("Audio validation failed for call %s: %s", self.call_sid, diag)
            raise AudioValidationError(f"Invalid audio payload: {diag}")

        prepared_audio = audio_bytes
        if audio_bytes[:4] != b"RIFF":
            # Wrap raw linear PCM into a standard 16 kHz WAV container
            prepared_audio = wrap_pcm_in_wav(audio_bytes, sample_rate=16000)

        # 1. Transcribe caller audio
        t_stt = time.perf_counter()
        stt_result = await self.stt.transcribe(prepared_audio, language=lang, **kwargs)
        stt_ms = round((time.perf_counter() - t_stt) * 1000, 2)
        caller_transcript = stt_result.text.strip()

        # 2. Process turn through AgentSession in the caller's detected language
        detected_language = resolve_language(
            caller_transcript,
            hint=stt_result.language,
            default=self.agent_session.language,
        )
        t_agent = time.perf_counter()
        agent_reply = await self.agent_session.process_turn(
            caller_transcript, language=detected_language
        )
        agent_ms = round((time.perf_counter() - t_agent) * 1000, 2)

        # 3. Synthesize the reply with a voice for the reply language
        t_tts = time.perf_counter()
        tts_result = await self.tts.synthesize(
            agent_reply, language=self.agent_session.language, **kwargs
        )
        tts_ms = round((time.perf_counter() - t_tts) * 1000, 2)
        self.latest_audio = tts_result.audio

        # Commit DB state for real-time admin observability
        self.agent_session.session.commit()

        is_terminal = self.agent_session.state in (
            AgentState.COMPLETED,
            AgentState.FAILED,
            AgentState.TRANSFERRED,
        )

        return VoiceTurnResult(
            caller_transcript=caller_transcript,
            agent_reply=agent_reply,
            audio=tts_result.audio,
            sample_rate=tts_result.sample_rate,
            audio_format=tts_result.format,
            state=self.agent_session.state,
            is_terminal=is_terminal,
            language=self.agent_session.language,
            booking_id=self.agent_session.booking_id,
            latencies_ms={
                "stt_ms": stt_ms,
                "agent_ms": agent_ms,
                "tts_ms": tts_ms,
                "total_ms": round(stt_ms + agent_ms + tts_ms, 2),
            },
        )

    def hangup(self) -> None:
        """Record caller abandonment / hangup and commit."""
        self.agent_session.hangup()
        self.agent_session.session.commit()


class VoiceSessionManager:
    """Manages active VoiceSession instances indexed by call SID."""

    def __init__(self) -> None:
        self._sessions: dict[str, VoiceSession] = {}

    def create(
        self,
        *,
        session: Session,
        config: AppConfig,
        resolver: DateTimeResolver,
        stt: STTAdapter,
        tts: TTSAdapter,
        call_sid: str | None = None,
        caller_phone: str = "",
        channel: str = "voice_api",
    ) -> VoiceSession:
        agent_session = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            call_sid=call_sid,
            caller_phone=caller_phone,
            channel=channel,
        )
        voice_session = VoiceSession(
            agent_session=agent_session,
            stt_adapter=stt,
            tts_adapter=tts,
            default_language=config.model.stt.language,
        )
        self._sessions[voice_session.call_sid] = voice_session
        return voice_session

    def get(self, call_sid: str) -> VoiceSession | None:
        return self._sessions.get(call_sid)

    def remove(self, call_sid: str) -> VoiceSession | None:
        return self._sessions.pop(call_sid, None)

    def active_count(self) -> int:
        return len(self._sessions)
