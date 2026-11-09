from typing import Any

from app.llm.evon_adapter import EvonAnalysis, EvonReasoningEngine
from app.llm.interfaces import DateTimeResolution, DateTimeResolver


class EvonDateTimeResolver(DateTimeResolver):
    """Evon v3.3 Sovereign Indic Reasoning Resolver with deterministic guardrail fallback."""

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model_name: str = "evon-v3.3",
        timeout: float = 2.0,
    ) -> None:
        self.engine = EvonReasoningEngine(
            api_base=api_base,
            api_key=api_key,
            model_name=model_name,
            timeout=timeout,
        )

    async def resolve(
        self, text: str, language: str, context: dict[str, Any] | None = None
    ) -> DateTimeResolution:
        return await self.engine.resolve(text, language, context=context)

    async def reason(
        self, text: str, language: str, context: dict[str, Any] | None = None
    ) -> EvonAnalysis:
        return await self.engine.reason(text, language, context=context)


__all__ = ["EvonAnalysis", "EvonDateTimeResolver", "EvonReasoningEngine"]
