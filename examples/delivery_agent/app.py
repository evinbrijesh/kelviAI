import re
from typing import Any

from examples.delivery_agent.tools import call_delivery_partner, cancel_order, track_order
from kelvi import KelviEngine, Session

TRACK_PATTERN = re.compile(
    r"(?:എവിടെ\s+എത്തി|സ്റ്റാറ്റസ്|ട്രാക്ക്|order\s+status|where\s+is\s+my\s+order|kahan\s+hai|track)",
    re.IGNORECASE,
)

CANCEL_PATTERN = re.compile(
    r"(?:റദ്ദാക്കണം|റദ്ദാക്കുക|ക്യാൻസൽ|cancel\s+(?:my\s+)?order|order\s+cancel|radd\s+karna)",
    re.IGNORECASE,
)

CALL_PATTERN = re.compile(
    r"(?:വിളിക്കണം|വിളിക്കാമോ|പാർട്ണർ|റൈഡർ|call\s+(?:the\s+)?(?:driver|partner|rider)|baat\s+karwao)",
    re.IGNORECASE,
)


def create_delivery_engine() -> KelviEngine:
    engine = KelviEngine(name="QuickBites Assistant", default_language="ml-IN")

    # Register tools
    engine.register_tool(track_order)
    engine.register_tool(cancel_order)
    engine.register_tool(call_delivery_partner)

    # 1. Track Order intent
    def match_track(text: str, session: Session) -> bool:
        return bool(TRACK_PATTERN.search(text))

    def format_track(result: dict[str, Any], session: Session) -> str:
        lang = session.language
        eta = result.get("eta_minutes", 10)
        partner = result.get("partner_name", "റൈഡർ")
        if lang.startswith("ml"):
            return (
                f"നിങ്ങളുടെ ഓർഡർ പുറപ്പെട്ടു കഴിഞ്ഞു. "
                f"ഡെലിവറി പാർട്ണർ {partner} ഏകദേശം {eta} മിനിറ്റിനുള്ളിൽ എത്തും."
            )
        if lang.startswith("hi"):
            return (
                f"आपका आर्डर निकल चुका है। "
                f"डिलीवरी पार्टनर {partner} लगभग {eta} मिनट में पहुंच जाएंगे।"
            )
        return (
            f"Your order is out for delivery! Partner {partner} "
            f"will arrive in approximately {eta} minutes."
        )

    engine.on_intent(match_track, "track_order", format_track)

    # 2. Cancel Order intent
    def match_cancel(text: str, session: Session) -> bool:
        return bool(CANCEL_PATTERN.search(text))

    def format_cancel(result: dict[str, Any], session: Session) -> str:
        lang = session.language
        amount = result.get("refund_amount", "തുക")
        if lang.startswith("ml"):
            return f"നിങ്ങളുടെ ഓർഡർ റദ്ദാക്കി. {amount} ഉടൻ നിങ്ങളുടെ അക്കൗണ്ടിലേക്ക് റീഫണ്ട് ചെയ്യുന്നതാണ്."
        if lang.startswith("hi"):
            return f"आपका आर्डर रद्द कर दिया गया है। {amount} का रिफंड शुरू कर दिया गया है।"
        return f"Your order has been cancelled and {amount} refund has been initiated."

    engine.on_intent(match_cancel, "cancel_order", format_cancel)

    # 3. Call Partner intent
    def match_call(text: str, session: Session) -> bool:
        return bool(CALL_PATTERN.search(text))

    def format_call(result: dict[str, Any], session: Session) -> str:
        lang = session.language
        if lang.startswith("ml"):
            return "ഡെലിവറി പാർട്ണറുമായി ഫോൺ കോൾ കണക്ട് ചെയ്യുന്നു, ദയവായി ലൈനിൽ തുടരുക."
        if lang.startswith("hi"):
            return "डिलीवरी पार्टनर से कॉल कनेक्ट की जा रही है, कृपया लाइन पर बने रहें।"
        return "Connecting you directly to the delivery partner, please hold the line."

    engine.on_intent(match_call, "call_delivery_partner", format_call)

    return engine
