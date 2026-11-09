import json
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from app.llm.evon_adapter import EvonReasoningEngine
from app.llm.evon_stub import EvonDateTimeResolver
from app.main import app


@pytest.mark.asyncio
async def test_evon_fallback_deterministic_resolves_datetime() -> None:
    engine = EvonReasoningEngine()
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    expected_date = (now + timedelta(days=1)).date()

    analysis = await engine.reason("നാളെ രാവിലെ 10 മണിക്ക് അപ്പോയിന്റ്മെന്റ് വേണം", language="ml-IN")
    assert analysis.resolution.date == expected_date
    assert analysis.resolution.time == time(10, 0)
    assert analysis.engine_used == "evon-deterministic-guardrail"
    assert analysis.intent == "request_slot"


@pytest.mark.asyncio
async def test_evon_fallback_extracts_complex_name_and_filters_filler() -> None:
    engine = EvonReasoningEngine()

    # Conversational exasperation containing name
    analysis = await engine.reason(
        "ഞാൻ എൻ്റെ പേര് ഓൾറെഡി പറഞ്ഞല്ലോ, എൻ്റെ പേര് മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ്, അതിൽ ബുക്ക് ചെയ്തോ",
        language="ml-IN",
    )
    assert analysis.caller_name == "മിസ്റ്റർ ഹൂ ഇസ് ദ ബോസ്"
    assert analysis.intent == "provide_name"

    # Only conversational filler: must NOT be stored as a name
    analysis_filler = await engine.reason("ഓൾറെഡി പറഞ്ഞല്ലോ", language="ml-IN")
    assert analysis_filler.caller_name is None


@pytest.mark.asyncio
async def test_evon_fallback_intent_classification() -> None:
    engine = EvonReasoningEngine()

    query_analysis = await engine.reason(
        "എൻ്റെ പേരായിട്ടെന്താ സേവ് ചെയ്തേക്കുന്നത്?", language="ml-IN"
    )
    assert query_analysis.intent == "query_saved_name"

    retain_analysis = await engine.reason(
        "വേണ്ട, അപ്പോഴത്തേക്കിന് ബുക്ക് ചെയ്തോ? ഇഷ്യൂ ഇല്ല.", language="ml-IN"
    )
    assert retain_analysis.intent == "retain_slot"


@pytest.mark.asyncio
async def test_evon_api_mock_success() -> None:
    engine = EvonReasoningEngine(api_base="https://evon.mock.ai/v1", api_key="mock-key")

    mock_json_content = json.dumps({
        "date": "2026-11-12",
        "time": "14:30",
        "caller_name": "Dr. Kurian",
        "intent": "request_slot",
        "confidence": 0.98,
        "explanation": "Evon v3.3 Indic temporal parsing",
    })

    mock_resp = httpx.Response(
        200,
        json={"choices": [{"message": {"content": mock_json_content}}]},
        request=httpx.Request("POST", "https://evon.mock.ai/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        analysis = await engine.reason("നവംബർ 12 ഉച്ചയ്ക്ക് 2:30", language="ml-IN")

        assert analysis.engine_used == "evon-v3.3"
        assert analysis.caller_name == "Dr. Kurian"
        assert analysis.resolution.time == time(14, 30)
        assert analysis.resolution.confidence == 0.98


@pytest.mark.asyncio
async def test_evon_api_error_falls_back_cleanly() -> None:
    engine = EvonReasoningEngine(api_base="https://evon.mock.ai/v1")

    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused")):
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        expected_date = (now + timedelta(days=1)).date()

        analysis = await engine.reason("നാളെ രാവിലെ 10 മണിക്ക്", language="ml-IN")
        assert analysis.engine_used == "evon-deterministic-guardrail"
        assert analysis.resolution.date == expected_date
        assert analysis.resolution.time == time(10, 0)


@pytest.mark.asyncio
async def test_evon_date_time_resolver_interface() -> None:
    resolver = EvonDateTimeResolver()
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    expected_date = (now + timedelta(days=1)).date()

    res = await resolver.resolve("നാളെ രാവിലെ 10 മണിക്ക്", language="ml-IN")
    assert res.date == expected_date
    assert res.time == time(10, 0)


def test_voice_status_includes_reasoning_model() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/voice/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "reasoning_model" in data
        assert "evon" in data["reasoning_model"].lower()
