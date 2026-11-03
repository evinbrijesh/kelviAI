import asyncio
import logging
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.agent.session import AgentSession, AgentState
from app.calls.session_log import CallSessionLog
from app.config import AppConfig, Settings, load_config
from app.db.seed import seed_demo_data
from app.db.session import Database
from app.llm.registry import AdapterRegistry
from app.privacy import mask_phone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scenario.appointment_malayalam")

REQUEST_UTTERANCE = "നാളെ രാവിലെ 10 മണിക്ക് അപ്പോയിന്റ്മെന്റ് വേണം"
CONFIRMATION_UTTERANCE = "അതെ, ബുക്ക് ചെയ്യാം"
CALLER_NAME = "Meera Krishnan"
CALLER_PHONE = "+919000000010"


async def run_scenario() -> int:
    logger.info("Starting the Malayalam appointment simulation")

    settings = Settings()
    config = load_config(settings.agent_config_path or None)
    database = Database(config.database.url)
    database.create_schema()
    adapters = AdapterRegistry(config)

    try:
        with database.session() as session:
            seed_demo_data(session)

        with database.session() as session:
            return await run_appointment_call(session, config, adapters)
    finally:
        await adapters.close()
        database.dispose()


async def run_appointment_call(
    session: Session,
    config: AppConfig,
    adapters: AdapterRegistry,
) -> int:

    agent = AgentSession(
        session=session,
        config=config,
        resolver=adapters.get_date_time_resolver(),
        call_sid=f"sim-{uuid4().hex[:12]}",
        caller_phone=CALLER_PHONE,
    )
    agent.start(emit_greeting=False)

    await agent.process_turn(REQUEST_UTTERANCE)
    if agent.state == AgentState.FAILED:
        return 1

    chosen = agent.chosen_time or "10:00"
    await agent.process_turn(f"എന്റെ പേര് {CALLER_NAME}. {chosen} സമയം ശരിയാണ്.")
    if agent.state == AgentState.FAILED:
        return 1

    await agent.process_turn(CONFIRMATION_UTTERANCE)
    if agent.state != AgentState.COMPLETED or not agent.booking_result:
        return 1

    assert agent.call_log is not None
    _print_summary(agent.call_log, agent.booking_result)
    return 0


def _print_summary(log: CallSessionLog, booking: dict[str, Any]) -> None:
    logger.info("Simulation summary")
    logger.info("  call: %s", log.call.call_sid)
    logger.info("  caller: %s %s", booking["patient_name"], mask_phone(log.call.caller_phone))
    logger.info("  clinic: %s", booking["clinic"])
    logger.info("  slot: %s (%s)", booking["slot_start"], booking["timezone"])
    logger.info("  reference: %s", booking["booking_id"])
    logger.info("  events recorded: %d", log.recorded_events)
    logger.info("  summary: %s", log.call.summary)


def main() -> None:
    exit_code = asyncio.run(run_scenario())
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
