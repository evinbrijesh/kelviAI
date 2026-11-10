import argparse
import sys
from pathlib import Path

from kelvi import __version__

_CLINIC_TEMPLATE_AGENT = """agent:
  name: "Nila Family Clinic Assistant"
  role: "Clinic Receptionist & Booking Voice Agent"
  primary_language: "ml-IN"
  supported_languages:
    - "ml-IN"
    - "hi-IN"
    - "en-IN"

tools:
  - name: "check_availability"
    description: "Find available doctor slots for a given date"
    enabled: true
    requires_confirmation: false

  - name: "book_appointment"
    description: "Confirm and book an appointment slot"
    enabled: true
    requires_confirmation: true
"""

_CLINIC_TEMPLATE_TOOLS = """from typing import Any
from kelvi import tool

@tool(
    name="check_availability",
    description="Check doctor availability for a given date",
    requires_confirmation=False,
)
async def check_availability(date: str = "tomorrow") -> dict[str, Any]:
    return {
        "date": date,
        "available_slots": ["10:00 AM", "11:30 AM", "04:00 PM"],
    }

@tool(
    name="book_appointment",
    description="Reserve an appointment slot for a patient",
    requires_confirmation=True,
    confirmation_prompt={
        "ml-IN": "അപ്പോയിന്റ്മെന്റ് സ്ഥിരീകരിക്കണമെന്ന് ഉറപ്പാണോ?",
        "hi-IN": "क्या आप अपॉइंटमेंट कन्फर्म करना चाहते हैं?",
        "en-IN": "Are you sure you want to confirm this booking?",
    },
)
async def book_appointment(date: str, time: str, patient_name: str) -> dict[str, Any]:
    return {
        "status": "confirmed",
        "date": date,
        "time": time,
        "patient_name": patient_name,
        "token": "TOKEN-42",
    }
"""

_MAIN_PY = """import asyncio
from kelvi import KelviEngine, Session
from tools import check_availability, book_appointment

async def main():
    engine = KelviEngine(name="Starter Agent", default_language="ml-IN")
    engine.register_tool(check_availability)
    engine.register_tool(book_appointment)

    session = Session(session_id="test_session", language="ml-IN")
    print("Kelvi AI Voice Agent initialized. Try calling engine.process_turn(session, text).")

if __name__ == "__main__":
    asyncio.run(main())
"""

_ENV_EXAMPLE = """GNANI_TOKEN=your_gnani_token_here
GNANI_ACCESS_KEY=your_gnani_access_key_here
PORT=8000
"""


def init_project(target_dir: Path, template: str = "clinic") -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "agent.yaml").write_text(_CLINIC_TEMPLATE_AGENT)
    (target_dir / "tools.py").write_text(_CLINIC_TEMPLATE_TOOLS)
    (target_dir / "main.py").write_text(_MAIN_PY)
    (target_dir / ".env.example").write_text(_ENV_EXAMPLE)
    readme_text = f"# {target_dir.name}\n\nBuilt with Kelvi AI v{__version__}\n"
    (target_dir / "README.md").write_text(readme_text)
    print(f"Created Kelvi AI agent in {target_dir.resolve()}")
    print("Next steps:")
    print(f"  cd {target_dir.name}")
    print("  python main.py")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kelvi",
        description="Kelvi AI: Indian-language-first framework for voice agents.",
    )
    parser.add_argument("--version", action="version", version=f"Kelvi AI {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Scaffold a new Kelvi AI agent project")
    init_parser.add_argument("name", help="Name of directory to create")
    init_parser.add_argument(
        "--template",
        choices=["clinic", "delivery"],
        default="clinic",
        help="Starter template",
    )

    args = parser.parse_args()
    if args.command == "init":
        init_project(Path(args.name), template=args.template)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
