# Creating New Voice Agents with Kelvi AI

Kelvi AI is an Indian-language-first framework for building reliable, action-taking voice agents. You can adapt it to any service or scheduling domain in under 60 lines of Python code using declarative configurations, the `@tool` decorator, and local Indic conversational guardrails.

---

## 1. Fast Project Scaffolding (`kelvi init`)

Kelvi AI includes a built-in CLI to scaffold new agents immediately:

```bash
# Scaffold a new delivery support voice agent
kelvi init my-delivery-agent --template delivery

# Or scaffold a healthcare clinic booking agent
kelvi init my-clinic-agent --template clinic
```

This generates a minimal project structure:
```text
my-delivery-agent/
├── agent.yaml        # Agent identity, primary dialect, and declared tools
├── tools.py          # Python async functions decorated with @tool
├── main.py           # Engine initialization and turn loop
├── .env.example      # Gnani API token and credentials
└── README.md
```

To run:
```bash
cd my-delivery-agent
python main.py
```

---

## 2. Declarative Tools with `@tool`

In Kelvi AI, tools are standard asynchronous Python functions. The framework automatically:
- Inspects Python type annotations to generate strict JSON Schema parameters.
- Validates inbound caller arguments at runtime.
- Enforces explicit caller confirmation before executing destructive mutations.

```python
from typing import Any
from kelvi import tool

# 1. Read-Only Query (executes immediately)
@tool(
    name="track_order",
    description="Check the current live delivery status and ETA of an order.",
    requires_confirmation=False,
)
async def track_order(order_id: str = "OD-9821") -> dict[str, Any]:
    return {
        "order_id": order_id,
        "status": "out_for_delivery",
        "eta_minutes": 12,
        "partner_name": "Suresh",
    }

# 2. State Mutation with Confirmation Guardrail
@tool(
    name="cancel_order",
    description="Cancel an active customer order before dispatch.",
    requires_confirmation=True,  # Safety guardrail: will not run without explicit affirmative consent
    confirmation_prompt={
        "ml-IN": "ഓർഡർ റദ്ദാക്കണമെന്ന് ഉറപ്പാണോ?",
        "hi-IN": "क्या आप वाकई अपना आर्डर रद्द करना चाहते हैं?",
        "en-IN": "Are you sure you want to cancel your order?",
    },
)
async def cancel_order(order_id: str = "OD-9821") -> dict[str, Any]:
    return {
        "order_id": order_id,
        "status": "cancelled",
        "refund_amount": "₹340",
    }
```

---

## 3. The 3-Layer Architecture

Kelvi AI separates business logic from Indian telephony realities:

1. **Kelvi Core (`kelvi.core`)**:
   - Manages session history, turn lifecycle, and pending confirmation states.
   - Emits structured `XRayTrace` events measuring exact STT, gating, tool execution, and TTS latency.
2. **Kelvi Indic Layer (`kelvi.indic`)**:
   - Script detection and automatic code-mixing routing (Malayalam, Hindi, Tamil, Kannada, Telugu, etc.).
   - Spoken Indic date/time formatting (e.g. converting `2026-11-12T10:00:00` to *"നാളെ രാവിലെ 10 മണിക്ക്"*).
   - Conversational discourse marker stripping (*"ennatto"*, *"aanatto"*, *"bhaiya"*, *"ji"*).
   - Live dual-script phonetic transliteration.
3. **Reference Applications**:
   - `app/` / `examples/clinic_appointments`: Transactional outpatient scheduling assistant with doctor slot locking.
   - `examples/delivery_agent`: Quick-commerce delivery tracking and cancellation assistant.

---

## 4. Hooking Up Custom Intent Matchers

You can wire fast-path regex rules or connect your custom reasoning model:

```python
import re
from kelvi import KelviEngine, Session
from tools import track_order, cancel_order

engine = KelviEngine(name="Delivery Assistant", default_language="ml-IN")
engine.register_tool(track_order)
engine.register_tool(cancel_order)

# Fast-path intent matcher: matches Malayalam, Hindi, and English order queries
TRACK_RE = re.compile(r"(?:എവിടെ\s+എത്തി|സ്റ്റാറ്റസ്|where\s+is\s+my\s+order|kahan\s+hai)", re.IGNORECASE)

def match_track(text: str, session: Session) -> bool:
    return bool(TRACK_RE.search(text))

def format_track(result: dict, session: Session) -> str:
    if session.language.startswith("ml"):
        return f"നിങ്ങളുടെ ഓർഡർ പുറപ്പെട്ടു കഴിഞ്ഞു. {result['partner_name']} 12 മിനിറ്റിനുള്ളിൽ എത്തും."
    return f"Your order is out for delivery with {result['partner_name']}."

engine.on_intent(match_track, "track_order", format_track)
```

---

## 5. Testing Your Agent

Run full programmatic turns using `engine.process_turn(session, text)`:

```python
session = Session(session_id="turn_1", language="ml-IN")
result = await engine.process_turn(session, "എന്റെ ഓർഡർ എവിടെ എത്തി?")
print(result.reply_text)
print("Turn latency:", result.xray["latency_ms"], "ms")
```
