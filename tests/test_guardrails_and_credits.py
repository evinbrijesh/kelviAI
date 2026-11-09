import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import GnaniConfig, STTConfig, TTSConfig
from app.llm.evon_adapter import EvonReasoningEngine
from app.llm.gnani_adapters import GnaniSTTAdapter, GnaniTTSAdapter


@pytest.mark.asyncio
async def test_tts_cache_avoids_repeated_gnani_calls() -> None:
    gnani_cfg = GnaniConfig(api_key_id="test-key", base_url="https://api.vachana.ai")
    tts_cfg = TTSConfig(model="timbre-v2.5", voice="Reshma", voices={"ml-IN": "Reshma"})
    adapter = GnaniTTSAdapter(gnani_cfg, tts_cfg)

    mock_resp = httpx.Response(
        200,
        content=b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00data\x00\x00\x00\x00",
        request=httpx.Request("POST", "https://api.vachana.ai/api/v1/tts/inference"),
    )

    with patch("app.llm.gnani_adapters._post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        # First call: must call the network API
        res1 = await adapter.synthesize("നമസ്കാരം, ഞാൻ കേൾവി AI അസിസ്റ്റന്റ് ആണ്.", language="ml-IN")
        assert res1.format == "wav"
        assert mock_post.call_count == 1

        # Second call with identical text & language: must hit in-memory cache (0 API calls!)
        res2 = await adapter.synthesize("നമസ്കാരം, ഞാൻ കേൾവി AI അസിസ്റ്റന്റ് ആണ്.", language="ml-IN")
        assert res2.audio == res1.audio
        assert mock_post.call_count == 1  # Still 1, 0 extra credits used!

    await adapter.close()


@pytest.mark.asyncio
async def test_stt_short_audio_skips_gnani_call() -> None:
    gnani_cfg = GnaniConfig(api_key_id="test-key", base_url="https://api.vachana.ai")
    stt_cfg = STTConfig(model="prisma-v3.0", language="ml-IN")
    adapter = GnaniSTTAdapter(gnani_cfg, stt_cfg)

    with patch("app.llm.gnani_adapters._post_with_retry", new_callable=AsyncMock) as mock_post:
        # Empty audio payload
        result = await adapter.transcribe(b"", language="ml-IN")
        assert result.text == ""
        assert result.confidence == 0.0
        assert mock_post.call_count == 0  # 0 API calls, 0 credits wasted

    await adapter.close()


@pytest.mark.asyncio
async def test_evon_smart_gating_skips_llm_for_clear_confirmations() -> None:
    engine = EvonReasoningEngine(api_base="https://evon.mock.ai/v1")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # High confidence positive confirmation: smart gating must NOT call external LLM
        analysis = await engine.reason("അതെ, ശരിയാണ്", language="ml-IN")
        assert analysis.intent == "confirm_booking"
        assert analysis.engine_used == "evon-deterministic-guardrail"
        assert mock_post.call_count == 0  # Zero tokens consumed!


@pytest.mark.asyncio
async def test_evon_smart_gating_invokes_llm_for_conversational_filler() -> None:
    engine = EvonReasoningEngine(api_base="https://evon.mock.ai/v1")

    mock_resp = httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps({
            "date": "2026-11-10",
            "time": "10:00",
            "caller_name": "മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ്",
            "intent": "provide_name",
            "confidence": 0.96,
            "explanation": "Resolved name and dismissed conversational exasperation",
        })}}]},
        request=httpx.Request("POST", "https://evon.mock.ai/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        utterance = "ഞാൻ എൻ്റെ പേര് ഓൾറെഡി പറഞ്ഞല്ലോ, എൻ്റെ പേര് മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ്"

        # Tricky conversational filler: smart gating MUST trigger LLM reasoning
        analysis = await engine.reason(utterance, language="ml-IN")
        assert mock_post.call_count == 1
        assert analysis.engine_used == "evon-v3.3"
        assert analysis.caller_name == "മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ്"

        # Second call with identical text: must hit LRU cache (0 extra tokens)
        analysis_cached = await engine.reason(utterance, language="ml-IN")
        assert mock_post.call_count == 1  # Still 1
        assert analysis_cached.caller_name == "മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ്"
