# Kelvi AI Delivery Assistant Example

This example demonstrates how to build an **Indian-language-first customer delivery assistant** in under 60 lines of Python code using **Kelvi AI**.

## What this demonstrates

1. **Declarative Tools with Confirmation Guardrails**:
   - `track_order`: Read-only, executes immediately.
   - `cancel_order`: Destructive mutation, requires explicit affirmative confirmation (`requires_confirmation=True`).
   - `call_delivery_partner`: Connects rider.
2. **Indian Language & Code-Mixing**:
   - Responds natively in Malayalam, Hindi, or English.
   - Cleans spoken discourse markers (`"chetta"`, `"bhaiya"`).
3. **Engine X-Ray Telemetry**:
   - Inspect every turn's latency, language detection, and tool execution in real-time.

## Quickstart

```python
from examples.delivery_agent.app import create_delivery_engine
from kelvi import Session

engine = create_delivery_engine()
session = Session(session_id="order_turn_1", language="ml-IN")

# 1. Ask where the order is (Malayalam)
turn_1 = await engine.process_turn(session, "എന്റെ ഓർഡർ എവിടെ എത്തി?")
print(turn_1.reply_text)
# Output: നിങ്ങളുടെ ഓർഡർ പുറപ്പെട്ടു കഴിഞ്ഞു. ഡെലിവറി പാർട്ണർ സുരേഷ് 12 മിനിറ്റിനുള്ളിൽ എത്തും.

# 2. Ask to cancel (triggers safety confirmation guardrail)
turn_2 = await engine.process_turn(session, "ഓർഡർ ക്യാൻസൽ ചെയ്യണം")
print(turn_2.reply_text)
# Output: ഓർഡർ റദ്ദാക്കണമെന്ന് ഉറപ്പാണോ?

# 3. Confirm in Malayalam
turn_3 = await engine.process_turn(session, "അതെ, റദ്ദാക്കിക്കോളൂ")
print(turn_3.reply_text)
# Output: നിങ്ങളുടെ ഓർഡർ റദ്ദാക്കി. ₹340 ഉടൻ നിങ്ങളുടെ അക്കൗണ്ടിലേക്ക് റീഫണ്ട് ചെയ്യുന്നതാണ്.
```
