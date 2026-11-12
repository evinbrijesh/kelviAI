from datetime import datetime
from typing import Any

import pytest

from app.agent.session import AgentSession, AgentState
from app.bridge.audio_utils import AudioValidationError, wrap_pcm_in_wav
from app.bridge.voice_session import VoiceSession, VoiceSessionManager
from app.config import load_config
from app.db.models import Calendar
from app.db.session import Database
from app.llm.custom_resolver import CustomDateTimeResolver
from app.llm.interfaces import STTAdapter, STTResult, TTSAdapter, TTSResult


class DummySTT(STTAdapter):
    def __init__(self, text: str = "നാളെ 10:00") -> None:
        self.text = text
        self.calls: list[bytes] = []

    async def transcribe(self, audio: bytes, **kwargs: Any) -> STTResult:
        self.calls.append(audio)
        return STTResult(
            text=self.text,
            language=kwargs.get("language", "ml-IN"),
            confidence=0.99,
            duration_ms=1200,
        )


class DummyTTS(TTSAdapter):
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.languages: list[str | None] = []

    async def synthesize(self, text: str, **kwargs: Any) -> TTSResult:
        self.calls.append(text)
        self.languages.append(kwargs.get("language"))
        return TTSResult(
            audio=b"RIFFdummywavdata",
            format="wav",
            sample_rate=48000,
        )


@pytest.fixture
def clinic_calendar(database: Database) -> Calendar:
    with database.session() as session:
        calendar = Calendar(
            name="Test Voice Clinic",
            timezone="Asia/Kolkata",
            slot_minutes=30,
            open_time=datetime.strptime("09:00", "%H:%M").time(),
            close_time=datetime.strptime("17:00", "%H:%M").time(),
            working_days="0,1,2,3,4,5,6",
            is_active=True,
        )
        session.add(calendar)
        session.flush()
        session.refresh(calendar)
        return calendar


@pytest.mark.asyncio
async def test_voice_session_start_synthesizes_greeting(
    database: Database, agent_config: Any
) -> None:
    config = load_config(agent_config)
    resolver = CustomDateTimeResolver()
    stt = DummySTT()
    tts = DummyTTS()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            caller_phone="+919000000001",
        )
        voice = VoiceSession(agent, stt, tts)
        turn = await voice.start()

        assert turn.caller_transcript == ""
        assert turn.agent_reply == config.agent.greeting
        assert turn.audio == b"RIFFdummywavdata"
        assert turn.sample_rate == 48000
        assert turn.state == AgentState.AWAITING_SLOT
        assert "tts_ms" in turn.latencies_ms
        assert tts.calls == [config.agent.greeting]


@pytest.mark.asyncio
async def test_voice_session_process_turn_flow(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> None:
    config = load_config(agent_config)
    resolver = CustomDateTimeResolver()
    stt = DummySTT("നാളെ 10:00")
    tts = DummyTTS()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            caller_phone="+919000000002",
        )
        voice = VoiceSession(agent, stt, tts)
        await voice.start()

        audio_input = wrap_pcm_in_wav(b"\x00\x00" * 400, sample_rate=16000)
        turn = await voice.process_turn(audio_input)

        assert turn.caller_transcript == "നാളെ 10:00"
        assert "10:00" in turn.agent_reply
        assert turn.state == AgentState.AWAITING_NAME
        assert turn.audio == b"RIFFdummywavdata"
        assert "stt_ms" in turn.latencies_ms
        assert "agent_ms" in turn.latencies_ms
        assert "tts_ms" in turn.latencies_ms


class HindiSTT(STTAdapter):
    async def transcribe(self, audio: bytes, **kwargs: Any) -> STTResult:
        return STTResult(
            text="कल सुबह 10 बजे अपॉइंटमेंट चाहिए",
            language="hi-IN",
            confidence=0.97,
            duration_ms=900,
        )


@pytest.mark.asyncio
async def test_voice_session_uses_detected_language_for_reply(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> None:
    config = load_config(agent_config)
    tts = DummyTTS()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=CustomDateTimeResolver(),
            caller_phone="+919000000008",
        )
        voice = VoiceSession(agent, HindiSTT(), tts)
        await voice.start()

        audio_input = wrap_pcm_in_wav(b"\x00\x00" * 400, sample_rate=16000)
        turn = await voice.process_turn(audio_input)

        assert turn.language == "hi-IN"
        assert tts.languages[-1] == "hi-IN"
        assert "स्लॉट उपलब्ध है" in turn.agent_reply
        assert agent.language == "hi-IN"
        assert agent.call.language == "hi-IN"


@pytest.mark.asyncio
async def test_voice_session_wraps_raw_pcm(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> None:
    config = load_config(agent_config)
    resolver = CustomDateTimeResolver()
    stt = DummySTT("നാളെ 10:00")
    tts = DummyTTS()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            caller_phone="+919000000003",
        )
        voice = VoiceSession(agent, stt, tts)
        await voice.start()

        # Send raw PCM bytes (no RIFF header)
        raw_pcm = b"\x01\x00" * 400
        await voice.process_turn(raw_pcm)

        assert len(stt.calls) == 1
        assert stt.calls[0].startswith(b"RIFF")


@pytest.mark.asyncio
async def test_voice_session_rejects_empty_audio(
    database: Database, agent_config: Any
) -> None:
    config = load_config(agent_config)
    resolver = CustomDateTimeResolver()
    stt = DummySTT()
    tts = DummyTTS()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=resolver,
            caller_phone="+919000000004",
        )
        voice = VoiceSession(agent, stt, tts)
        await voice.start()

        with pytest.raises(AudioValidationError, match="empty"):
            await voice.process_turn(b"")


def test_voice_session_manager(database: Database, agent_config: Any) -> None:
    config = load_config(agent_config)
    resolver = CustomDateTimeResolver()
    stt = DummySTT()
    tts = DummyTTS()
    manager = VoiceSessionManager()

    with database.session() as session:
        v1 = manager.create(
            session=session,
            config=config,
            resolver=resolver,
            stt=stt,
            tts=tts,
            call_sid="call-test-1",
            caller_phone="+919000000005",
        )
        assert manager.active_count() == 1
        assert manager.get("call-test-1") is v1
        assert manager.get("unknown") is None

        removed = manager.remove("call-test-1")
        assert removed is v1
        assert manager.active_count() == 0


class ScriptSwitchSTT(STTAdapter):
    """Simulates STT behavior on multi-turn Malayalam dialogue."""
    def __init__(self, turn2_text: str = "Johnson", turn2_lang: str = "kn-IN") -> None:
        self.turn = 0
        self.turn2_text = turn2_text
        self.turn2_lang = turn2_lang
        self.stt_languages_called: list[str | None] = []

    async def transcribe(self, audio: bytes, **kwargs: Any) -> STTResult:
        self.turn += 1
        lang = kwargs.get("language")
        self.stt_languages_called.append(lang)
        if self.turn == 1:
            return STTResult(
                text="നാളെ 10:00",
                language="ml-IN",
                confidence=0.99,
                duration_ms=1000,
            )
        return STTResult(
            text=self.turn2_text,
            language=self.turn2_lang,
            confidence=0.95,
            duration_ms=600,
        )


@pytest.mark.asyncio
async def test_malayalam_call_does_not_switch_to_kannada_on_johnson(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> None:
    """Regression test: saying 'johnson' in a Malayalam session must stay Malayalam,

    even if STT acoustically hints Kannada (kn-IN) or transcribes in Latin/Kannada script.
    """
    config = load_config(agent_config)
    stt = ScriptSwitchSTT(turn2_text="Johnson", turn2_lang="kn-IN")
    tts = DummyTTS()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=CustomDateTimeResolver(),
            caller_phone="+919000000009",
        )
        voice = VoiceSession(agent, stt, tts)
        await voice.start()

        audio_input = wrap_pcm_in_wav(b"\x00\x00" * 400, sample_rate=16000)

        # Turn 1: Slot requested in Malayalam
        turn1 = await voice.process_turn(audio_input)
        assert turn1.language == "ml-IN"
        assert agent.language == "ml-IN"
        assert agent.state == AgentState.AWAITING_NAME

        # Turn 2: Caller says "Johnson", STT returned kn-IN hint
        turn2 = await voice.process_turn(audio_input)
        assert turn2.language == "ml-IN"
        assert agent.language == "ml-IN"
        assert agent.caller_name == "Johnson"
        assert tts.languages[-1] == "ml-IN"
        assert "അപ്പോയിന്റ്മെന്റ്" in turn2.agent_reply or "ഉറപ്പാക്കാമോ" in turn2.agent_reply
        assert "ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್" not in turn2.agent_reply  # Must not contain Kannada

        # Check STT called with ml-IN on Turn 2 (locked language), not indic-auto
        assert stt.stt_languages_called[1] == "ml-IN"


@pytest.mark.asyncio
async def test_malayalam_call_does_not_switch_to_kannada_on_kannada_script_name(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> None:
    """If STT decoded the name into Kannada script (ಜಾನ್ಸನ್), session still stays Malayalam."""
    config = load_config(agent_config)
    stt = ScriptSwitchSTT(turn2_text="ಜಾನ್ಸನ್", turn2_lang="kn-IN")
    tts = DummyTTS()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=CustomDateTimeResolver(),
            caller_phone="+919000000010",
        )
        voice = VoiceSession(agent, stt, tts)
        await voice.start()

        audio_input = wrap_pcm_in_wav(b"\x00\x00" * 400, sample_rate=16000)
        await voice.process_turn(audio_input)

        turn2 = await voice.process_turn(audio_input)
        assert turn2.language == "ml-IN"
        assert agent.language == "ml-IN"
        assert tts.languages[-1] == "ml-IN"
        assert "ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್" not in turn2.agent_reply


@pytest.mark.asyncio
async def test_malayalam_text_turn_does_not_flip_to_english_on_johnson(
    database: Database, agent_config: Any, clinic_calendar: Calendar
) -> None:
    """Typing 'johnson' in text fallback must keep Malayalam, not switch to en-IN."""
    config = load_config(agent_config)
    tts = DummyTTS()

    with database.session() as session:
        agent = AgentSession(
            session=session,
            config=config,
            resolver=CustomDateTimeResolver(),
            caller_phone="+919000000011",
        )
        voice = VoiceSession(agent, DummySTT(), tts)
        await voice.start()

        # Turn 1 in Malayalam
        await voice.process_text_turn("നാളെ രാവിലെ 10 മണിക്ക്")
        assert agent.language == "ml-IN"
        assert agent.state == AgentState.AWAITING_NAME

        # Turn 2: Caller enters name 'johnson'
        turn2 = await voice.process_text_turn("johnson")
        assert turn2.language == "ml-IN"
        assert agent.language == "ml-IN"
        assert agent.caller_name == "johnson"
        assert tts.languages[-1] == "ml-IN"
