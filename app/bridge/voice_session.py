import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.agent.session import AgentSession, AgentState
from app.bridge.audio_utils import (
    AudioValidationError,
    validate_audio_bytes,
    wrap_pcm_in_wav,
)
from app.config import AppConfig
from app.llm.interfaces import DateTimeResolver, STTAdapter, TTSAdapter
from app.llm.language import detect_language, normalize_language
from app.llm.transliteration import transliterate_indic

if TYPE_CHECKING:
    from kelvi import KelviEngine
    from kelvi import Session as KelviSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceTurnResult:
    caller_transcript: str
    agent_reply: str
    audio: bytes
    sample_rate: int
    audio_format: str
    state: AgentState | str
    is_terminal: bool
    language: str
    caller_transliteration: str | None = None
    agent_transliteration: str | None = None
    booking_id: str | None = None
    booking_patient: str | None = None
    booking_slot: dict[str, str] | None = None
    latencies_ms: dict[str, float] = field(default_factory=dict)
    xray: dict[str, Any] = field(default_factory=dict)


class VoiceSession:
    """Bridges audio I/O with conversational AgentSession, Gnani STT, and Gnani TTS."""

    def __init__(
        self,
        agent_session: AgentSession,
        stt_adapter: STTAdapter,
        tts_adapter: TTSAdapter,
        *,
        default_language: str = "indic-auto",
        agent_type: str = "clinic",
    ) -> None:
        self.agent_session = agent_session
        self.stt = stt_adapter
        self.tts = tts_adapter
        self.default_language = default_language
        self.latest_audio: bytes | None = None
        self.agent_type = agent_type
        self.delivery_engine: KelviEngine | None = None
        self.delivery_session: KelviSession | None = None
        if agent_type == "delivery":
            from examples.delivery_agent.app import create_delivery_engine
            from kelvi import Session as DeliverySession
            self.delivery_engine = create_delivery_engine()
            self.delivery_session = DeliverySession(
                session_id=agent_session.call_sid, language="ml-IN"
            )

    @property
    def call_sid(self) -> str:
        return self.agent_session.call_sid

    @property
    def state(self) -> AgentState:
        return self.agent_session.state

    @property
    def language(self) -> str:
        return self.agent_session.language

    def _booking_slot(self) -> dict[str, str] | None:
        chosen_date = self.agent_session.chosen_date
        chosen_time = self.agent_session.chosen_time
        if not self.agent_session.booking_id or chosen_date is None or chosen_time is None:
            return None
        return {"date": chosen_date.isoformat(), "time": chosen_time[:5]}

    def _build_xray(self, latencies_ms: dict[str, float]) -> dict[str, Any]:
        engine = (
            self.agent_session.last_resolved.get("engine")
            if self.agent_session.last_resolved
            else None
        ) or "evon-v3.3 (hybrid)"
        return {
            "language": self.agent_session.language,
            "state": self.agent_session.state.value,
            "resolved_datetime": self.agent_session.last_resolved,
            "tool_invoked": self.agent_session.last_tool_invoked,
            "latencies_ms": latencies_ms,
            "sovereign_stack": {
                "stt": self.agent_session.config.model.stt.model,
                "reasoning": f"Evon v3.3 [{engine}]",
                "tts": self.agent_session.config.model.tts.model,
            },
        }

    async def start(self, *, emit_greeting: bool = True) -> VoiceTurnResult:
        """Start agent session, synthesize greeting, and commit initial turn."""
        if self.agent_type == "delivery" and self.delivery_session is not None:
            greeting_text = (
                "നമസ്കാരം! ക്വിക്ക്ബൈറ്റ്സ് സപ്പോർട്ടിൽ നിന്നാണ്. "
                "ഓർഡർ സംബന്ധിച്ച് എന്ത് സഹായമാണ് വേണ്ടത്?"
            )
            t_start = time.perf_counter()
            tts_result = await self.tts.synthesize(
                greeting_text, language=self.delivery_session.language
            )
            tts_ms = round((time.perf_counter() - t_start) * 1000, 2)
            self.latest_audio = tts_result.audio
            self.agent_session.session.commit()
            latencies = {"tts_ms": tts_ms}
            return VoiceTurnResult(
                caller_transcript="",
                agent_reply=greeting_text,
                audio=tts_result.audio,
                sample_rate=tts_result.sample_rate,
                audio_format=tts_result.format,
                state="active",
                is_terminal=False,
                language=self.delivery_session.language,
                booking_id=None,
                latencies_ms=latencies,
                xray={
                    "language": self.delivery_session.language,
                    "agent": "QuickBites Delivery Assistant",
                    "latencies_ms": latencies,
                    "sovereign_stack": {
                        "stt": self.agent_session.config.model.stt.model,
                        "reasoning": "Kelvi Core Engine",
                        "tts": self.agent_session.config.model.tts.model,
                    },
                },
            )

        greeting_text = self.agent_session.start(emit_greeting=emit_greeting)

        t_start = time.perf_counter()
        tts_result = await self.tts.synthesize(
            greeting_text, language=self.agent_session.language
        )
        tts_ms = round((time.perf_counter() - t_start) * 1000, 2)
        self.latest_audio = tts_result.audio

        # Persist initial call turn to DB so admin dashboard reflects it immediately
        self.agent_session.session.commit()
        latencies = {"tts_ms": tts_ms}

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
            latencies_ms=latencies,
            xray=self._build_xray(latencies),
        )


    @staticmethod
    def _script_language_hint(text: str) -> str | None:
        """Only an Indic script in the utterance may switch a locked call's language.

        English is never treated as a switch signal: names and mixed phrases are typed
        in Latin script and would otherwise flip an ongoing Hindi or Malayalam call.
        """
        detected = detect_language(text)
        return detected if detected and detected != "en-IN" else None

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

        if (
            self.agent_type == "delivery"
            and self.delivery_engine is not None
            and self.delivery_session is not None
        ):
            t_agent = time.perf_counter()
            turn_res = await self.delivery_engine.process_turn(
                self.delivery_session, caller_transcript
            )
            agent_ms = round((time.perf_counter() - t_agent) * 1000, 2)
            agent_reply = turn_res.reply_text

            t_tts = time.perf_counter()
            tts_result = await self.tts.synthesize(
                agent_reply, language=self.delivery_session.language, **kwargs
            )
            tts_ms = round((time.perf_counter() - t_tts) * 1000, 2)
            self.latest_audio = tts_result.audio
            self.agent_session.session.commit()

            latencies = {
                "stt_ms": stt_ms,
                "agent_ms": agent_ms,
                "tts_ms": tts_ms,
                "total_ms": round(stt_ms + agent_ms + tts_ms, 2),
            }
            caller_translit = transliterate_indic(
                caller_transcript, self.delivery_session.language
            )
            agent_translit = transliterate_indic(
                agent_reply, self.delivery_session.language
            )
            xray_data = dict(turn_res.xray)
            xray_data["latencies_ms"] = latencies
            xray_data["tool_invoked"] = turn_res.tool_executed
            xray_data["sovereign_stack"] = {
                "stt": self.agent_session.config.model.stt.model,
                "reasoning": "Kelvi Core Engine",
                "tts": self.agent_session.config.model.tts.model,
            }
            return VoiceTurnResult(
                caller_transcript=caller_transcript,
                caller_transliteration=caller_translit,
                agent_reply=agent_reply,
                agent_transliteration=agent_translit,
                audio=tts_result.audio,
                sample_rate=tts_result.sample_rate,
                audio_format=tts_result.format,
                state="awaiting_confirmation" if turn_res.pending_confirmation else "active",
                is_terminal=False,
                language=self.delivery_session.language,
                booking_id=None,
                latencies_ms=latencies,
                xray=xray_data,
            )

        # 2. Process turn through AgentSession in the caller's detected language
        detected_language = normalize_language(language) or self._script_language_hint(
            caller_transcript
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

        latencies = {
            "stt_ms": stt_ms,
            "agent_ms": agent_ms,
            "tts_ms": tts_ms,
            "total_ms": round(stt_ms + agent_ms + tts_ms, 2),
        }

        caller_translit = transliterate_indic(
            caller_transcript, detected_language or self.agent_session.language
        )
        agent_translit = transliterate_indic(agent_reply, self.agent_session.language)

        return VoiceTurnResult(
            caller_transcript=caller_transcript,
            caller_transliteration=caller_translit,
            agent_reply=agent_reply,
            agent_transliteration=agent_translit,
            audio=tts_result.audio,
            sample_rate=tts_result.sample_rate,
            audio_format=tts_result.format,
            state=self.agent_session.state,
            is_terminal=is_terminal,
            language=self.agent_session.language,
            booking_id=self.agent_session.booking_id,
            booking_patient=self.agent_session.caller_name,
            booking_slot=self._booking_slot(),
            latencies_ms=latencies,
            xray=self._build_xray(latencies),
        )

    async def process_text_turn(
        self,
        text: str,
        *,
        language: str | None = None,
        **kwargs: Any,
    ) -> VoiceTurnResult:
        """Process a text turn without inbound audio, and synthesize speech reply."""
        clean_text = text.strip()

        if (
            self.agent_type == "delivery"
            and self.delivery_engine is not None
            and self.delivery_session is not None
        ):
            t_agent = time.perf_counter()
            turn_res = await self.delivery_engine.process_turn(
                self.delivery_session, clean_text
            )
            agent_ms = round((time.perf_counter() - t_agent) * 1000, 2)
            agent_reply = turn_res.reply_text

            t_tts = time.perf_counter()
            tts_result = await self.tts.synthesize(
                agent_reply, language=self.delivery_session.language, **kwargs
            )
            tts_ms = round((time.perf_counter() - t_tts) * 1000, 2)
            self.latest_audio = tts_result.audio
            self.agent_session.session.commit()

            latencies = {
                "stt_ms": 0.0,
                "agent_ms": agent_ms,
                "tts_ms": tts_ms,
                "total_ms": round(agent_ms + tts_ms, 2),
            }
            caller_translit = transliterate_indic(
                clean_text, self.delivery_session.language
            )
            agent_translit = transliterate_indic(
                agent_reply, self.delivery_session.language
            )
            xray_data = dict(turn_res.xray)
            xray_data["latencies_ms"] = latencies
            xray_data["tool_invoked"] = turn_res.tool_executed
            xray_data["sovereign_stack"] = {
                "stt": self.agent_session.config.model.stt.model,
                "reasoning": "Kelvi Core Engine",
                "tts": self.agent_session.config.model.tts.model,
            }
            return VoiceTurnResult(
                caller_transcript=clean_text,
                caller_transliteration=caller_translit,
                agent_reply=agent_reply,
                agent_transliteration=agent_translit,
                audio=tts_result.audio,
                sample_rate=tts_result.sample_rate,
                audio_format=tts_result.format,
                state="awaiting_confirmation" if turn_res.pending_confirmation else "active",
                is_terminal=False,
                language=self.delivery_session.language,
                booking_id=None,
                latencies_ms=latencies,
                xray=xray_data,
            )

        detected_language = normalize_language(language) or self._script_language_hint(
            clean_text
        )
        t_agent = time.perf_counter()
        agent_reply = await self.agent_session.process_turn(
            clean_text, language=detected_language
        )
        agent_ms = round((time.perf_counter() - t_agent) * 1000, 2)

        t_tts = time.perf_counter()
        tts_result = await self.tts.synthesize(
            agent_reply, language=self.agent_session.language, **kwargs
        )
        tts_ms = round((time.perf_counter() - t_tts) * 1000, 2)
        self.latest_audio = tts_result.audio

        self.agent_session.session.commit()

        is_terminal = self.agent_session.state in (
            AgentState.COMPLETED,
            AgentState.FAILED,
            AgentState.TRANSFERRED,
        )
        latencies = {
            "stt_ms": 0.0,
            "agent_ms": agent_ms,
            "tts_ms": tts_ms,
            "total_ms": round(agent_ms + tts_ms, 2),
        }

        caller_translit = transliterate_indic(clean_text, detected_language)
        agent_translit = transliterate_indic(agent_reply, self.agent_session.language)

        return VoiceTurnResult(
            caller_transcript=clean_text,
            caller_transliteration=caller_translit,
            agent_reply=agent_reply,
            agent_transliteration=agent_translit,
            audio=tts_result.audio,
            sample_rate=tts_result.sample_rate,
            audio_format=tts_result.format,
            state=self.agent_session.state,
            is_terminal=is_terminal,
            language=self.agent_session.language,
            booking_id=self.agent_session.booking_id,
            booking_patient=self.agent_session.caller_name,
            booking_slot=self._booking_slot(),
            latencies_ms=latencies,
            xray=self._build_xray(latencies),
        )

    def hangup(self) -> None:
        """Record caller abandonment / hangup and commit."""
        self.agent_session.hangup()
        self.agent_session.session.commit()


class VoiceSessionManager:
    """Manages active VoiceSession instances indexed by call SID with TTL eviction."""

    def __init__(self, ttl_seconds: float = 1800.0, max_sessions: int = 1000) -> None:
        self._sessions: dict[str, VoiceSession] = {}
        self._last_accessed: dict[str, float] = {}
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [
            sid
            for sid, last_ts in self._last_accessed.items()
            if now - last_ts > self.ttl_seconds
        ]
        for sid in expired:
            self._sessions.pop(sid, None)
            self._last_accessed.pop(sid, None)

        if len(self._sessions) >= self.max_sessions:
            oldest = sorted(self._last_accessed.items(), key=lambda x: x[1])
            to_remove = oldest[: max(1, len(oldest) // 10)]
            for sid, _ in to_remove:
                self._sessions.pop(sid, None)
                self._last_accessed.pop(sid, None)

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
        agent_type: str = "clinic",
    ) -> VoiceSession:
        self._evict_expired()
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
            agent_type=agent_type,
        )
        self._sessions[voice_session.call_sid] = voice_session
        self._last_accessed[voice_session.call_sid] = time.time()
        return voice_session

    def get(self, call_sid: str) -> VoiceSession | None:
        self._evict_expired()
        voice_session = self._sessions.get(call_sid)
        if voice_session is not None:
            self._last_accessed[call_sid] = time.time()
        return voice_session

    def remove(self, call_sid: str) -> VoiceSession | None:
        self._last_accessed.pop(call_sid, None)
        return self._sessions.pop(call_sid, None)

    def active_count(self) -> int:
        self._evict_expired()
        return len(self._sessions)

