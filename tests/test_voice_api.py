import base64
from typing import Any

import pytest
from httpx import AsyncClient

from app.bridge.audio_utils import wrap_pcm_in_wav
from app.llm.interfaces import STTAdapter, STTResult, TTSAdapter, TTSResult
from app.main import app


class MockSTT(STTAdapter):
    def __init__(self, text: str = "നാളെ 10:00") -> None:
        self.text = text

    async def transcribe(self, audio: bytes, **kwargs: Any) -> STTResult:
        return STTResult(
            text=self.text,
            language=kwargs.get("language", "ml-IN"),
            confidence=0.95,
            duration_ms=800,
        )


class MockTTS(TTSAdapter):
    async def synthesize(self, text: str, **kwargs: Any) -> TTSResult:
        return TTSResult(
            audio=b"RIFFmockwavcontent48k",
            format="wav",
            sample_rate=48000,
        )


@pytest.mark.asyncio
async def test_browser_voice_demo_is_separate_from_admin(client: AsyncClient) -> None:
    response = await client.get("/demo")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Talk to KelviAI" in response.text
    assert "/admin/static/voice-demo.js" in response.text
    assert "Use fictional names only" in response.text
    assert "Non-production demo" in response.text
    assert "api_key_id" not in response.text

    root = await client.get("/")
    assert root.headers["location"] == "/admin/ui"
    for asset in ("voice-demo.js", "voice-capture.js"):
        assert (await client.get(f"/admin/static/{asset}")).status_code == 200


@pytest.mark.asyncio
async def test_voice_status_endpoint(client: AsyncClient) -> None:
    response = await client.get("/api/voice/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["provider"] == "gnani"
    assert data["stt_model"] == "prisma-v3.0"
    assert data["tts_model"] == "timbre-v2.5"
    assert data["sample_rate"] == 48000
    assert "active_calls" in data
    assert "ml-IN" in data["supported_languages"]
    assert "hi-IN" in data["supported_languages"]
    assert len(data["supported_languages"]) == 10


@pytest.mark.asyncio
async def test_voice_session_lifecycle_and_turn(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = app.state.registry
    monkeypatch.setattr(registry, "get_stt_adapter", lambda: MockSTT("നാളെ 10:00"))
    monkeypatch.setattr(registry, "get_tts_adapter", lambda: MockTTS())

    # 1. Start voice session
    start_resp = await client.post(
        "/api/voice/session/start",
        json={"caller_phone": "+919000000010", "channel": "voice_api"},
    )
    assert start_resp.status_code == 200
    start_data = start_resp.json()
    call_sid = start_data["call_sid"]
    assert start_data["state"] == "awaiting_slot"
    assert start_data["language"] == "ml-IN"
    assert start_data["audio_base64"] != ""
    assert start_data["audio_url"] == f"/api/voice/session/{call_sid}/audio"

    # 2. Retrieve audio for greeting
    audio_resp = await client.get(f"/api/voice/session/{call_sid}/audio")
    assert audio_resp.status_code == 200
    assert audio_resp.headers["content-type"] == "audio/wav"
    assert audio_resp.content == b"RIFFmockwavcontent48k"

    # 3. Process turn with JSON base64 audio
    sample_wav = wrap_pcm_in_wav(b"\x00\x00" * 320, sample_rate=16000)
    wav_b64 = base64.b64encode(sample_wav).decode("ascii")

    turn_resp = await client.post(
        f"/api/voice/session/{call_sid}/turn",
        json={"audio_base64": wav_b64},
    )
    assert turn_resp.status_code == 200
    turn_data = turn_resp.json()
    assert turn_data["caller_transcript"] == "നാളെ 10:00"
    assert "10:00" in turn_data["agent_reply"]
    assert turn_data["language"] == "ml-IN"
    assert turn_data["state"] == "awaiting_name"
    assert not turn_data["is_terminal"]
    assert "total_ms" in turn_data["latencies_ms"]

    # 3b. Process text fallback turn
    text_resp = await client.post(
        f"/api/voice/session/{call_sid}/text-turn",
        json={"text": "എന്റെ പേര് അനൂപ് കുമാർ"},
    )
    assert text_resp.status_code == 200
    text_data = text_resp.json()
    assert text_data["caller_transcript"] == "എന്റെ പേര് അനൂപ് കുമാർ"
    assert text_data["state"] == "awaiting_confirmation"
    assert "audio_base64" in text_data
    assert text_data["latencies_ms"]["stt_ms"] == 0.0

    # 4. Hangup call
    hangup_resp = await client.post(f"/api/voice/session/{call_sid}/hangup")
    assert hangup_resp.status_code == 200
    assert hangup_resp.json()["status"] == "hungup"

    # 5. Subsequent turn on hungup/removed call returns 404
    turn_again = await client.post(
        f"/api/voice/session/{call_sid}/turn",
        json={"audio_base64": wav_b64},
    )
    assert turn_again.status_code == 404


@pytest.mark.asyncio
async def test_browser_voice_booking_uses_no_phone_number(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stt = MockSTT("कल सुबह 10 बजे appointment चाहिए")
    registry = app.state.registry
    monkeypatch.setattr(registry, "get_stt_adapter", lambda: stt)
    monkeypatch.setattr(registry, "get_tts_adapter", lambda: MockTTS())
    start = await client.post("/api/voice/session/start", json={"channel": "browser_demo"})
    assert start.status_code == 200
    sid = start.json()["call_sid"]
    audio = wrap_pcm_in_wav(b"\x00\x00" * 320, sample_rate=16000)

    for text, state in (
        ("कल सुबह 10 बजे appointment चाहिए", "awaiting_name"),
        ("My name is Asha Demo", "awaiting_confirmation"),
        ("Yes, confirm", "completed"),
    ):
        stt.text = text
        response = await client.post(
            f"/api/voice/session/{sid}/turn",
            content=audio,
            headers={"content-type": "audio/wav"},
        )
        assert response.status_code == 200
        assert response.json()["state"] == state

    booking_id = response.json()["booking_id"]
    assert booking_id is not None
    assert response.json()["is_terminal"]
    bookings = (await client.get("/admin/bookings")).json()
    booking = next(item for item in bookings if str(item["id"]) == booking_id)
    assert booking["patient_name"] == "Asha Demo"
    assert booking["caller_phone"] == "***"
    assert booking["status"] == "confirmed"
    assert (await client.post(f"/api/voice/session/{sid}/hangup")).status_code == 200
    assert (await client.get(f"/api/voice/session/{sid}/audio")).status_code == 404


@pytest.mark.asyncio
async def test_voice_turn_raw_binary_body(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = app.state.registry
    monkeypatch.setattr(registry, "get_stt_adapter", lambda: MockSTT("നാളെ 10:00"))
    monkeypatch.setattr(registry, "get_tts_adapter", lambda: MockTTS())

    # Start session
    start_resp = await client.post(
        "/api/voice/session/start",
        json={"caller_phone": "+919000000011"},
    )
    call_sid = start_resp.json()["call_sid"]

    # Send raw binary WAV in request body
    sample_wav = wrap_pcm_in_wav(b"\x00\x00" * 320, sample_rate=16000)
    turn_resp = await client.post(
        f"/api/voice/session/{call_sid}/turn",
        content=sample_wav,
        headers={"content-type": "audio/wav"},
    )
    assert turn_resp.status_code == 200
    assert turn_resp.json()["caller_transcript"] == "നാളെ 10:00"


@pytest.mark.asyncio
async def test_twilio_voice_webhook(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = app.state.registry
    monkeypatch.setattr(registry, "get_stt_adapter", lambda: MockSTT("നാളെ 10:00"))
    monkeypatch.setattr(registry, "get_tts_adapter", lambda: MockTTS())

    # Call start webhook
    resp = await client.post(
        "/api/voice/webhook/twilio",
        content="CallSid=tw-call-001&From=%2B919000000012",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    assert "<Response>" in resp.text
    assert "<Gather" in resp.text
    assert "/api/voice/session/tw-call-001/audio" in resp.text

    # Utterance webhook
    turn_resp = await client.post(
        "/api/voice/webhook/twilio",
        content="CallSid=tw-call-001&From=%2B919000000012&SpeechResult=10:00",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert turn_resp.status_code == 200
    assert "<Response>" in turn_resp.text
