import asyncio
import json

import httpx
import pytest

from app.config import GnaniConfig, STTConfig, TTSConfig
from app.llm import gnani_adapters
from app.llm.gnani_adapters import GnaniSTTAdapter, GnaniTTSAdapter


@pytest.mark.asyncio
async def test_stt_adapter_uses_documented_multipart_fields() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "transcript": "നമസ്കാരം",
                "detected_language_code": "ml-IN",
                "success": True,
            },
        )

    adapter = GnaniSTTAdapter(
        GnaniConfig(api_key_id="test-key", base_url="https://gnani.test"),
        STTConfig(model="prisma-v3.0", language="ml-IN"),
    )
    assert adapter.client.headers["X-API-Key-ID"] == "test-key"
    await adapter.client.aclose()
    adapter.client = httpx.AsyncClient(
        base_url="https://gnani.test", transport=httpx.MockTransport(handler)
    )

    result = await adapter.transcribe(b"RIFFsample")
    await adapter.close()

    body = captured["body"]
    assert captured["path"] == "/stt/v3"
    assert isinstance(body, bytes)
    assert b'name="audio_file"' in body
    assert b'name="language_code"' in body
    assert b"prisma-v3.0" in body
    assert b"ml-IN" in body
    assert result.text == "നമസ്കാരം"
    assert result.language == "ml-IN"


@pytest.mark.asyncio
async def test_stt_adapter_accepts_indic_auto_detection() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "transcript": "कल सुबह 10 बजे",
                "detected_language_code": "hi-IN",
                "success": True,
            },
        )

    adapter = GnaniSTTAdapter(
        GnaniConfig(api_key_id="test-key", base_url="https://gnani.test"),
        STTConfig(model="prisma-v3.0", language="indic-auto"),
    )
    await adapter.client.aclose()
    adapter.client = httpx.AsyncClient(
        base_url="https://gnani.test", transport=httpx.MockTransport(handler)
    )

    result = await adapter.transcribe(b"RIFFsample")
    await adapter.close()

    body = captured["body"]
    assert isinstance(body, bytes)
    assert b"indic-auto" in body
    assert result.language == "hi-IN"


@pytest.mark.asyncio
async def test_tts_adapter_selects_documented_voice_per_language() -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.read()))
        return httpx.Response(200, content=b"RIFFsample")

    adapter = GnaniTTSAdapter(
        GnaniConfig(api_key_id="test-key", base_url="https://gnani.test"),
        TTSConfig(
            model="timbre-v2.5",
            voice="Reshma",
            voices={"hi-IN": "Deepak"},
        ),
    )
    await adapter.client.aclose()
    adapter.client = httpx.AsyncClient(
        base_url="https://gnani.test", transport=httpx.MockTransport(handler)
    )

    await adapter.synthesize("नमस्ते", language="hi-IN")
    await adapter.synthesize("வணக்கம்", language="ta-IN")
    await adapter.close()

    assert payloads[0]["voice"] == "Deepak"
    assert payloads[0]["language"] == "hi-IN"
    assert payloads[1]["voice"] == "Asmita"
    assert payloads[1]["language"] == "ta-IN"


@pytest.mark.asyncio
async def test_tts_adapter_sends_voice_and_audio_config() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["payload"] = json.loads(request.read())
        return httpx.Response(
            200,
            content=b"RIFFsample",
            headers={"content-type": "audio/wav"},
        )

    adapter = GnaniTTSAdapter(
        GnaniConfig(api_key_id="test-key", base_url="https://gnani.test"),
        TTSConfig(model="timbre-v2.5", voice="Reshma"),
    )
    await adapter.client.aclose()
    adapter.client = httpx.AsyncClient(
        base_url="https://gnani.test", transport=httpx.MockTransport(handler)
    )

    result = await adapter.synthesize("നമസ്കാരം", language="ml-IN")
    await adapter.close()

    payload = captured["payload"]
    assert captured["path"] == "/api/v1/tts/inference"
    assert isinstance(payload, dict)
    assert payload["text"] == "നമസ്കാരം"
    assert payload["voice"] == "Reshma"
    assert payload["model"] == "timbre-v2.5"
    assert payload["language"] == "ml-IN"
    assert payload["speed"] == 1.0
    assert payload["audio_config"] == {
        "sample_rate": 48000,
        "num_channels": 1,
        "sample_width": 2,
        "encoding": "linear_pcm",
        "container": "wav",
    }
    assert result.audio == b"RIFFsample"
    assert result.format == "wav"
    assert result.sample_rate == 48000


@pytest.mark.asyncio
async def test_stt_adapter_retries_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gnani_adapters, "_BASE_DELAY_SECONDS", 0)
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(429, json={"error": "RATE_LIMITED"})
        return httpx.Response(
            200,
            json={"transcript": "നമസ്കാരം", "detected_language_code": "ml-IN"},
        )

    adapter = GnaniSTTAdapter(
        GnaniConfig(api_key_id="test-key", base_url="https://gnani.test"),
        STTConfig(model="prisma-v3.0", language="ml-IN"),
    )
    await adapter.client.aclose()
    adapter.client = httpx.AsyncClient(
        base_url="https://gnani.test", transport=httpx.MockTransport(handler)
    )

    result = await adapter.transcribe(b"RIFFsample")
    await adapter.close()

    assert len(attempts) == 3
    assert result.text == "നമസ്കാരം"


@pytest.mark.asyncio
async def test_tts_adapter_gives_up_after_bounded_rate_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gnani_adapters, "_BASE_DELAY_SECONDS", 0)
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(429, headers={"Retry-After": "0"})

    adapter = GnaniTTSAdapter(
        GnaniConfig(api_key_id="test-key", base_url="https://gnani.test"),
        TTSConfig(model="timbre-v2.5", voice="Reshma"),
    )
    await adapter.client.aclose()
    adapter.client = httpx.AsyncClient(
        base_url="https://gnani.test", transport=httpx.MockTransport(handler)
    )

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.synthesize("നമസ്കാരം", language="ml-IN")
    await adapter.close()

    assert len(attempts) == gnani_adapters._MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_tts_adapter_serializes_concurrent_requests() -> None:
    active = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return httpx.Response(200, content=b"RIFFsample")

    adapter = GnaniTTSAdapter(
        GnaniConfig(api_key_id="test-key", base_url="https://gnani.test"),
        TTSConfig(model="timbre-v2.5", voice="Reshma"),
    )
    await adapter.client.aclose()
    adapter.client = httpx.AsyncClient(
        base_url="https://gnani.test", transport=httpx.MockTransport(handler)
    )

    await asyncio.gather(*(adapter.synthesize(f"line {index}") for index in range(3)))
    await adapter.close()

    assert peak == 1
