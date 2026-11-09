from app.config import AppConfig
from app.llm.custom_resolver import CustomDateTimeResolver
from app.llm.evon_stub import EvonDateTimeResolver
from app.llm.gnani_adapters import GnaniSTTAdapter, GnaniTTSAdapter
from app.llm.interfaces import DateTimeResolver, STTAdapter, TTSAdapter
from app.llm.warp_stubs import WarpSTTAdapter, WarpTTSAdapter


class AdapterRegistry:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._stt_adapter: STTAdapter | None = None
        self._tts_adapter: TTSAdapter | None = None
        self._resolver: DateTimeResolver | None = None

    def get_stt_adapter(self) -> STTAdapter:
        if self._stt_adapter is None:
            provider = self.config.model.provider.lower()
            if provider == "gnani":
                self._stt_adapter = GnaniSTTAdapter(self.config.gnani, self.config.model.stt)
            elif provider == "warp":
                self._stt_adapter = WarpSTTAdapter()
            else:
                raise ValueError(f"Unknown STT provider: {self.config.model.provider}")
        return self._stt_adapter

    def get_tts_adapter(self) -> TTSAdapter:
        if self._tts_adapter is None:
            provider = self.config.model.provider.lower()
            if provider == "gnani":
                self._tts_adapter = GnaniTTSAdapter(self.config.gnani, self.config.model.tts)
            elif provider == "warp":
                self._tts_adapter = WarpTTSAdapter()
            else:
                raise ValueError(f"Unknown TTS provider: {self.config.model.provider}")
        return self._tts_adapter

    def get_date_time_resolver(self) -> DateTimeResolver:
        if self._resolver is None:
            resolver_type = self.config.model.date_time_resolver.lower()
            if resolver_type == "custom":
                self._resolver = CustomDateTimeResolver()
            elif resolver_type in ("evon", "hybrid"):
                self._resolver = EvonDateTimeResolver()
            else:
                raise ValueError(f"Unknown date_time_resolver: {resolver_type}")
        return self._resolver

    async def close(self) -> None:
        if self._stt_adapter is not None and hasattr(self._stt_adapter, "close"):
            await self._stt_adapter.close()
        if self._tts_adapter is not None and hasattr(self._tts_adapter, "close"):
            await self._tts_adapter.close()
