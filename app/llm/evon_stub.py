from typing import Any

from app.llm.interfaces import DateTimeResolution, DateTimeResolver


class EvonDateTimeResolver(DateTimeResolver):
    async def resolve(
        self, text: str, language: str, context: dict[str, Any] | None = None
    ) -> DateTimeResolution:
        raise NotImplementedError("Evon is not documented. Use CustomDateTimeResolver instead.")
