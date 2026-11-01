import asyncio
import logging
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.calls.session_log import CallSessionLog, invoke_tool, start_call
from app.config import AppConfig, Settings, load_config
from app.db.models import CallStatus
from app.db.seed import seed_demo_data
from app.db.session import Database
from app.llm.registry import AdapterRegistry
from app.privacy import mask_phone
from app.tools.booking import build_tool_registry
from app.tools.registry import ToolRegistry

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
    log = start_call(
        session,
        call_sid=f"sim-{uuid4().hex[:12]}",
        caller_phone=CALLER_PHONE,
        language=config.agent.language,
    )
    tools = build_tool_registry(session, config.tools, call=log.call)
    resolver = adapters.get_date_time_resolver()

    log.user_turn(REQUEST_UTTERANCE, language=config.agent.language)
    resolution = await resolver.resolve(REQUEST_UTTERANCE, language=config.agent.language)
    logger.info(
        "Resolved utterance to date=%s time=%s confidence=%.2f (%s)",
        resolution.date,
        resolution.time,
        resolution.confidence,
        resolution.explanation,
    )

    if resolution.date is None or resolution.time is None:
        log.error(
            "date_unresolved",
            confidence=resolution.confidence,
            explanation=resolution.explanation,
        )
        return _finish(
            log,
            CallStatus.FAILED,
            "The caller's date and time could not be understood.",
            "unresolved",
        )

    requested = resolution.time.strftime("%H:%M")
    day, availability = await _open_day(tools, log, resolution.date)
    if day is None:
        message = str(
            availability.get("message") or "No open clinic day was found in the next week."
        )
        log.agent_turn(message)
        return _finish(log, CallStatus.FAILED, message, "no_availability")

    slots = [str(slot) for slot in availability.get("available") or []]
    if not slots:
        message = f"All appointments are taken on {day.isoformat()}."
        log.agent_turn(message)
        return _finish(log, CallStatus.FAILED, message, "no_availability")

    chosen = _nearest_slot(slots, requested)
    logger.info(
        "Requested %s on %s; booking %s (%d open slot(s))",
        requested,
        day.isoformat(),
        chosen,
        len(slots),
    )
    if chosen == requested:
        log.agent_turn(f"{day.isoformat()} at {requested} is available.")
    else:
        log.agent_turn(
            f"{day.isoformat()} at {requested} is taken; the nearest open slot is {chosen}."
        )

    clinic = str(availability.get("clinic") or "the clinic")
    log.user_turn(f"എന്റെ പേര് {CALLER_NAME}. {chosen} സമയം ശരിയാണ്.")
    log.agent_turn(
        f"Confirming {CALLER_NAME}, {day.isoformat()} at {chosen}, {clinic}. Shall I book it?"
    )
    log.user_turn(CONFIRMATION_UTTERANCE)

    booking = await invoke_tool(
        tools,
        log,
        "book_slot",
        {"caller_name": CALLER_NAME, "date": day.isoformat(), "time": chosen},
    )
    if booking.get("status") != "confirmed":
        message = f"The booking could not be confirmed ({booking.get('status')})."
        log.agent_turn(message)
        return _finish(log, CallStatus.FAILED, message, "booking_failed")

    summary = (
        f"{CALLER_NAME} booked an appointment at {clinic} on "
        f"{booking['slot_start']} (reference {booking['booking_id']})."
    )
    _finish(log, CallStatus.COMPLETED, summary, "booked")
    _print_summary(log, booking)
    return 0


async def _open_day(
    tools: ToolRegistry,
    log: CallSessionLog,
    start_day: date,
) -> tuple[date | None, dict[str, Any]]:
    day = start_day
    result: dict[str, Any] = {}
    for _ in range(7):
        result = await invoke_tool(tools, log, "check_availability", {"date": day.isoformat()})
        status = result.get("status")
        if status == "ok":
            return day, result
        if status != "closed":
            logger.warning("Availability check failed with status %s", status)
            return None, result
        log.agent_turn(f"The clinic is closed on {day.isoformat()}; checking the next day.")
        day += timedelta(days=1)
    return None, result


def _nearest_slot(slots: list[str], requested: str) -> str:
    if requested in slots:
        return requested
    later = [slot for slot in slots if slot > requested]
    return later[0] if later else slots[0]


def _finish(log: CallSessionLog, status: CallStatus, summary: str, outcome: str) -> int:
    log.finish(status, summary, outcome)
    logger.info("Call %s ended: %s (%s)", log.call.call_sid, outcome, status)
    return 0 if status is CallStatus.COMPLETED else 1


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
