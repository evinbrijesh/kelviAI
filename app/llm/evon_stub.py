from app.llm.interfaces import DateTimeResolver, DateTimeResolution


class EvonDateTimeResolver(DateTimeResolver):
    async def resolve(self, text: str, language: str, context: dict | None = None) -> DateTimeResolution:
        raise NotImplementedError("Evon is not documented. Use CustomDateTimeResolver instead.")
