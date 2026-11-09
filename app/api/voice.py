import base64
import hashlib
import hmac
import logging
import re
import urllib.parse
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.admin.routes import get_session
from app.bridge.audio_utils import MAX_AUDIO_BYTES, AudioValidationError
from app.bridge.voice_session import VoiceSessionManager
from app.config import AppConfig, Settings
from app.llm.language import SUPPORTED_LANGUAGE_CODES
from app.llm.registry import AdapterRegistry
from app.providers.telephony import TwilioProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])
_manager = VoiceSessionManager()
_twilio_provider = TwilioProvider()


def verify_twilio_signature(
    auth_token: str, url: str, params: dict[str, str], signature: str
) -> bool:
    """Verify inbound Twilio request signature using HMAC-SHA1."""
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params.keys()))
    expected = base64.b64encode(
        hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    return hmac.compare_digest(expected, signature)



class VoiceStartRequest(BaseModel):
    caller_phone: str = Field(default="", description="Caller phone number (e.g. +919000000001)")
    call_sid: str | None = Field(default=None, description="Optional call identifier")
    channel: str = Field(default="voice_api", description="Channel identifier (e.g. telephony)")


class VoiceStartResponse(BaseModel):
    call_sid: str
    greeting: str
    state: str
    language: str
    audio_base64: str
    audio_url: str
    xray: dict[str, Any] | None = None


class VoiceTurnJSONRequest(BaseModel):
    audio_base64: str = Field(description="Base64 encoded audio bytes (WAV or linear PCM)")
    language: str | None = Field(default=None, description="Optional override language code")


class VoiceTextTurnRequest(BaseModel):
    text: str = Field(description="Caller utterance in plain text")
    language: str | None = Field(default=None, description="Optional override language code")


class VoiceTurnResponse(BaseModel):
    call_sid: str
    caller_transcript: str
    agent_reply: str
    state: str
    language: str
    is_terminal: bool
    booking_id: str | None
    audio_base64: str
    audio_url: str
    latencies_ms: dict[str, float]
    xray: dict[str, Any] | None = None


class VoiceStatusResponse(BaseModel):
    status: str
    provider: str
    stt_model: str
    tts_model: str
    tts_voice: str
    language: str
    supported_languages: list[str]
    sample_rate: int
    active_calls: int


def get_dependencies(request: Request) -> tuple[AppConfig, AdapterRegistry]:
    config: AppConfig | None = getattr(request.app.state, "config", None)
    registry: AdapterRegistry | None = getattr(request.app.state, "registry", None)
    if config is None or registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application configuration or model registry is not initialized",
        )
    return config, registry


@router.get("/status", response_model=VoiceStatusResponse)
async def get_voice_status(request: Request) -> VoiceStatusResponse:
    """Retrieve operational diagnostics for the voice and speech adapters."""
    config, _ = get_dependencies(request)
    return VoiceStatusResponse(
        status="ok",
        provider=config.model.provider,
        stt_model=config.model.stt.model,
        tts_model=config.model.tts.model,
        tts_voice=config.model.tts.voice,
        language=config.model.stt.language,
        supported_languages=list(SUPPORTED_LANGUAGE_CODES),
        sample_rate=48000,
        active_calls=_manager.active_count(),
    )


@router.post("/session/start", response_model=VoiceStartResponse)
async def start_voice_session(
    body: VoiceStartRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> VoiceStartResponse:
    """Initialize a new voice session, register the call, and return the synthesized greeting."""
    config, registry = get_dependencies(request)
    stt = registry.get_stt_adapter()
    tts = registry.get_tts_adapter()
    resolver = registry.get_date_time_resolver()

    voice_session = _manager.create(
        session=session,
        config=config,
        resolver=resolver,
        stt=stt,
        tts=tts,
        call_sid=body.call_sid,
        caller_phone=body.caller_phone,
        channel=body.channel,
    )

    turn = await voice_session.start(emit_greeting=True)
    audio_b64 = base64.b64encode(turn.audio).decode("ascii")
    audio_url = f"/api/voice/session/{voice_session.call_sid}/audio"

    return VoiceStartResponse(
        call_sid=voice_session.call_sid,
        greeting=turn.agent_reply,
        state=turn.state.value,
        language=turn.language,
        audio_base64=audio_b64,
        audio_url=audio_url,
        xray=turn.xray,
    )


@router.post("/session/{call_sid}/turn", response_model=VoiceTurnResponse)
async def process_voice_turn(
    call_sid: str,
    request: Request,
    language: str | None = None,
) -> VoiceTurnResponse:
    """Process an audio turn using JSON with base64 audio or raw binary audio in request body."""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_AUDIO_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"Audio payload exceeds maximum limit of {MAX_AUDIO_BYTES} bytes",
                )
        except ValueError:
            pass

    voice_session = _manager.get(call_sid)
    if voice_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active voice session not found for call_sid '{call_sid}'",
        )

    content_type = request.headers.get("content-type", "")

    raw_audio: bytes | None = None

    if "application/json" in content_type:
        try:
            body_json = await request.json()
            req = VoiceTurnJSONRequest(**body_json)
            raw_audio = base64.b64decode(req.audio_base64)
            if req.language:
                language = req.language
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to parse JSON audio body: {exc}",
            ) from exc
    else:
        raw_audio = await request.body()

    if not raw_audio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio payload provided in request",
        )

    if len(raw_audio) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Audio payload exceeds maximum limit of {MAX_AUDIO_BYTES} bytes",
        )

    try:
        turn = await voice_session.process_turn(raw_audio, language=language)
    except AudioValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    audio_b64 = base64.b64encode(turn.audio).decode("ascii")
    audio_url = f"/api/voice/session/{call_sid}/audio"

    if turn.is_terminal:
        logger.info("Call %s reached terminal state: %s", call_sid, turn.state)

    return VoiceTurnResponse(
        call_sid=call_sid,
        caller_transcript=turn.caller_transcript,
        agent_reply=turn.agent_reply,
        state=turn.state.value,
        language=turn.language,
        is_terminal=turn.is_terminal,
        booking_id=turn.booking_id,
        audio_base64=audio_b64,
        audio_url=audio_url,
        latencies_ms=turn.latencies_ms,
        xray=turn.xray,
    )


@router.post("/session/{call_sid}/text-turn", response_model=VoiceTurnResponse)
async def process_text_turn(
    call_sid: str,
    body: VoiceTextTurnRequest,
) -> VoiceTurnResponse:
    """Process a typed text turn (fallback for microphone failure) and synthesize agent speech."""
    voice_session = _manager.get(call_sid)
    if voice_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active voice session not found for call_sid '{call_sid}'",
        )

    if not body.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text utterance cannot be empty",
        )

    turn = await voice_session.process_text_turn(body.text, language=body.language)

    audio_b64 = base64.b64encode(turn.audio).decode("ascii")
    audio_url = f"/api/voice/session/{call_sid}/audio"

    if turn.is_terminal:
        logger.info("Call %s reached terminal state: %s", call_sid, turn.state)

    return VoiceTurnResponse(
        call_sid=call_sid,
        caller_transcript=turn.caller_transcript,
        agent_reply=turn.agent_reply,
        state=turn.state.value,
        language=turn.language,
        is_terminal=turn.is_terminal,
        booking_id=turn.booking_id,
        audio_base64=audio_b64,
        audio_url=audio_url,
        latencies_ms=turn.latencies_ms,
        xray=turn.xray,
    )


@router.get("/session/{call_sid}/audio")
async def get_latest_session_audio(call_sid: str) -> Response:
    """Stream or download the most recent agent audio response for the given call."""
    voice_session = _manager.get(call_sid)
    if voice_session is None or voice_session.latest_audio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No audio available for call_sid '{call_sid}'",
        )

    return Response(content=voice_session.latest_audio, media_type="audio/wav")


@router.post("/session/{call_sid}/hangup")
async def hangup_voice_session(call_sid: str) -> dict[str, str]:
    """Gracefully terminate an active voice session."""
    voice_session = _manager.get(call_sid)
    if voice_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active voice session not found for call_sid '{call_sid}'",
        )

    voice_session.hangup()
    _manager.remove(call_sid)
    return {"status": "hungup", "call_sid": call_sid}


@router.post("/webhook/twilio")
async def twilio_voice_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Twilio telephony voice webhook entry point with standard TwiML responses."""
    config, registry = get_dependencies(request)

    body_bytes = await request.body()
    form_data = urllib.parse.parse_qs(body_bytes.decode("utf-8", errors="replace"))

    settings = Settings()
    if settings.twilio_auth_token:
        signature = request.headers.get("X-Twilio-Signature", "")
        flat_params = {k: v[0] for k, v in form_data.items()}
        if not verify_twilio_signature(
            settings.twilio_auth_token, str(request.url), flat_params, signature
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid Twilio signature",
            )

    call_sid = form_data.get("CallSid", ["call-anon"])[0]
    if not re.match(r"^[a-zA-Z0-9_\-]+$", call_sid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid CallSid format",
        )

    caller_phone = form_data.get("From", [""])[0]
    speech_result = form_data.get("SpeechResult", [None])[0]

    voice_session = _manager.get(call_sid)
    action_url = f"/api/voice/webhook/twilio?CallSid={urllib.parse.quote(call_sid)}"

    if voice_session is None:
        # Initial call start
        stt = registry.get_stt_adapter()
        tts = registry.get_tts_adapter()
        resolver = registry.get_date_time_resolver()

        voice_session = _manager.create(
            session=session,
            config=config,
            resolver=resolver,
            stt=stt,
            tts=tts,
            call_sid=call_sid,
            caller_phone=caller_phone,
            channel="twilio",
        )
        turn = await voice_session.start(emit_greeting=True)
        audio_url = f"/api/voice/session/{call_sid}/audio"

        twiml = _twilio_provider.format_response(
            turn.agent_reply,
            audio_url=audio_url,
            listen_for_input=True,
            action_url=action_url,
            language=turn.language,
        )
        return Response(content=twiml, media_type="application/xml")

    # Inbound speech utterance from Twilio Gather
    if speech_result:
        reply_text = await voice_session.agent_session.process_turn(speech_result)
        reply_language = voice_session.agent_session.language
        tts = registry.get_tts_adapter()
        tts_res = await tts.synthesize(reply_text, language=reply_language)
        voice_session.latest_audio = tts_res.audio
        voice_session.agent_session.session.commit()

        audio_url = f"/api/voice/session/{call_sid}/audio"
        is_terminal = voice_session.agent_session.state in (
            "completed",
            "failed",
            "transferred",
        )

        twiml = _twilio_provider.format_response(
            reply_text,
            audio_url=audio_url,
            listen_for_input=not is_terminal,
            action_url=action_url if not is_terminal else None,
            language=reply_language,
        )
        if is_terminal:
            _manager.remove(call_sid)

        return Response(content=twiml, media_type="application/xml")

    # Caller ended without speech
    twiml = _twilio_provider.format_response(
        voice_session.agent_session.message("thanks"),
        listen_for_input=False,
        language=voice_session.agent_session.language,
    )
    return Response(content=twiml, media_type="application/xml")
