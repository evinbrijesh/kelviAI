import asyncio
import logging
from typing import Any

from app.config import load_config
from app.llm.registry import AdapterRegistry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scenario.appointment_malayalam")


async def run_scenario() -> int:
    logger.info("Initializing Malayalam appointment booking simulation...")

    config = load_config()
    logger.info("Loaded agent configuration for: %s (%s)", config.agent.name, config.agent.language)

    configured_tools: dict[str, dict[str, Any]] = {
        tool.name: tool.parameters for tool in config.tools if tool.enabled
    }
    logger.info("Registered active tools: %s", list(configured_tools.keys()))

    if "check_availability" not in configured_tools:
        logger.error("Required tool 'check_availability' is not configured")
        return 1

    registry = AdapterRegistry(config)
    try:
        resolver = registry.get_date_time_resolver()

        # Simulated user turn in Malayalam: "Tomorrow at 10 AM I need an appointment"
        user_utterance = "നാളെ രാവിലെ 10 മണിക്ക് അപ്പോയിന്റ്മെന്റ് വേണം"
        logger.info("Simulating user utterance: '%s'", user_utterance)

        resolution = await resolver.resolve(user_utterance, language="malayalam")
        logger.info(
            "Resolved: date=%s, time=%s, timezone=%s, confidence=%.2f, explanation='%s'",
            resolution.date,
            resolution.time,
            resolution.timezone,
            resolution.confidence,
            resolution.explanation,
        )

        if resolution.date is None or resolution.time is None:
            logger.error("Failed to resolve date and time from user utterance")
            return 1

        tool_input = {
            "date": str(resolution.date),
            "time_slot": f"{resolution.time.strftime('%H:%M')} morning",
        }
        logger.info("Simulating tool call 'check_availability' with arguments: %s", tool_input)

        logger.info("Malayalam appointment simulation completed successfully")
        return 0
    finally:
        await registry.close()


def main() -> None:
    exit_code = asyncio.run(run_scenario())
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
