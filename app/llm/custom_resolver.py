from datetime import datetime, timedelta
from typing import Any

from app.llm.interfaces import DateTimeResolver, DateTimeResolution


class CustomDateTimeResolver(DateTimeResolver):
    async def resolve(self, text: str, language: str, context: dict | None = None) -> DateTimeResolution:
        now = datetime.now()
        context = context or {}

        text_lower = text.lower()

        if "tomorrow" in text_lower:
            target_date = now + timedelta(days=1)
            return DateTimeResolution(
                date=target_date.date(),
                time=None,
                timezone="Asia/Kolkata",
                confidence=0.8,
                explanation="Detected 'tomorrow'",
            )

        if "today" in text_lower:
            return DateTimeResolution(
                date=now.date(),
                time=None,
                timezone="Asia/Kolkata",
                confidence=0.9,
                explanation="Detected 'today'",
            )

        return DateTimeResolution(
            date=None,
            time=None,
            timezone="Asia/Kolkata",
            confidence=0.0,
            explanation="No date/time pattern detected",
        )
