from typing import Any

from app.llm.interfaces import STTAdapter, STTMode, STTResult, TTSAdapter, TTSMode, TTSResult


class WarpSTTAdapter(STTAdapter):
    async def transcribe(
        self, audio: bytes, mode: STTMode = STTMode.REALTIME, **kwargs: Any
    ) -> STTResult:
        raise NotImplementedError(
            "Warp is not documented. Use GnaniSTTAdapter with Prisma instead."
        )


class WarpTTSAdapter(TTSAdapter):
    async def synthesize(
        self, text: str, mode: TTSMode = TTSMode.REALTIME, **kwargs: Any
    ) -> TTSResult:
        raise NotImplementedError(
            "Warp is not documented. Use GnaniTTSAdapter with Timbre instead."
        )
