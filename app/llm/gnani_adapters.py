from typing import Any

import httpx

from app.config import GnaniConfig, STTConfig, TTSConfig
from app.llm.interfaces import STTAdapter, STTMode, STTResult, TTSAdapter, TTSMode, TTSResult
from app.llm.language import DEFAULT_LANGUAGE, default_voice, normalize_language


class GnaniSTTAdapter(STTAdapter):
    def __init__(self, config: GnaniConfig, stt_config: STTConfig):
        self.config = config
        self.stt_config = stt_config
        self.client = httpx.AsyncClient(
            base_url=config.base_url,
            headers={"X-API-Key-ID": config.api_key_id},
            timeout=30.0,
        )

    async def transcribe(
        self, audio: bytes, mode: STTMode = STTMode.REST, **kwargs: Any
    ) -> STTResult:
        if mode == STTMode.REST:
            return await self._transcribe_rest(audio, **kwargs)
        raise NotImplementedError(f"STT mode {mode} not yet implemented")

    async def _transcribe_rest(self, audio: bytes, **kwargs: Any) -> STTResult:
        files = {"audio_file": ("audio.wav", audio, "audio/wav")}
        data = {
            "model": self.stt_config.model,
            "language_code": kwargs.get("language", self.stt_config.language),
        }

        response = await self.client.post("/stt/v3", files=files, data=data)
        response.raise_for_status()

        result = response.json()
        return STTResult(
            text=str(result.get("transcript", "")),
            language=str(
                result.get("detected_language_code", self.stt_config.language)
            ),
            confidence=float(result.get("confidence") or 0.0),
            duration_ms=int(result.get("duration_ms") or 0),
        )

    async def close(self) -> None:
        await self.client.aclose()


class GnaniTTSAdapter(TTSAdapter):
    def __init__(self, config: GnaniConfig, tts_config: TTSConfig):
        self.config = config
        self.tts_config = tts_config
        self.client = httpx.AsyncClient(
            base_url=config.base_url,
            headers={"X-API-Key-ID": config.api_key_id},
            timeout=30.0,
        )

    async def synthesize(
        self, text: str, mode: TTSMode = TTSMode.REST, **kwargs: Any
    ) -> TTSResult:
        if mode == TTSMode.REST:
            return await self._synthesize_rest(text, **kwargs)
        raise NotImplementedError(f"TTS mode {mode} not yet implemented")

    async def _synthesize_rest(self, text: str, **kwargs: Any) -> TTSResult:
        language = (
            normalize_language(kwargs.get("language")) or DEFAULT_LANGUAGE
        )
        voice = (
            kwargs.get("voice")
            or self.tts_config.voices.get(language)
            or default_voice(language)
            or self.tts_config.voice
        )
        data = {
            "text": text,
            "model": self.tts_config.model,
            "voice": voice,
            "language": language,
            "speed": kwargs.get("speed", 1.0),
            "audio_config": {
                "sample_rate": 48000,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        }

        response = await self.client.post("/api/v1/tts/inference", json=data)
        response.raise_for_status()

        return TTSResult(
            audio=response.content,
            format="wav",
            sample_rate=48000,
        )

    async def close(self) -> None:
        await self.client.aclose()
