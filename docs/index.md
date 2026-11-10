# Kelvi AI Documentation

> **Kelvi AI: Indian-Language Voice Agent Framework**  
> An open-source framework for building voice agents with speech recognition, conversation state, tool execution, memory, and localized voice responses.

---

## Documentation Navigation

```text
Documentation
├── Introduction
├── Getting Started
│   ├── Installation
│   ├── Configuration
│   └── First Agent
├── Core Concepts
│   ├── Session Engine
│   ├── Conversation State
│   ├── Memory
│   └── Confirmation Guardrails
├── Indian-Language Engine
│   ├── Language Detection
│   ├── Code-Mixed Speech
│   ├── Transliteration
│   └── Date and Time Resolution
├── Tools
│   ├── Creating Tools (@tool)
│   ├── Schema Validation
│   ├── Timeouts
│   └── Tool Results & Localized Formatting
├── Provider Adapters
│   ├── Prisma STT (Acoustic Ear)
│   ├── Timbre TTS (Contextual Prosody)
│   ├── Evon Reasoning (Indic LLM)
│   └── Custom Adapters
├── Interfaces
│   ├── Browser Voice (AudioWorklet)
│   ├── REST & Streaming API
│   └── Twilio Telephony Webhook
├── Reference Applications
│   ├── Clinic Appointments (Healthcare Flagship)
│   ├── Delivery Support (Quick-Commerce)
│   └── College Helpdesk
├── Deployment
│   ├── Local Development
│   ├── Hosted Public Demo (Render / Vercel)
│   ├── Environment Variables
│   └── Production Checklist
└── Security and Privacy
    ├── Audio Retention (Zero Persistence)
    ├── PII Masking
    ├── Rate Limits
    └── Webhook Signature Verification
```

---

## 1. Introduction

Kelvi AI (*"Kelvi"* = *Question / Hearing* in Dravidian languages) is an open-source framework designed specifically for Indian-language and code-mixed voice agents that take actions in the real world.

Unlike generic chatbots that pass audio to overseas models, Kelvi AI is built on three layers:
1. **Kelvi Core Engine**: Domain-agnostic turn management, conversation state, memory, tool registry, and confirmation guardrails.
2. **Kelvi Indic Layer**: Script identification, code-mixed language resolution, discourse marker stripping, dual-script transliteration, and spoken datetime prosody.
3. **Reference Applications**: Production-grade examples demonstrating how to build outpatient appointment schedulers, quick-commerce delivery bots, and helpdesks.

---

## 2. Getting Started

### Installation

```bash
# Install Kelvi AI via pip
pip install kelvi-ai

# Or clone from source
git clone https://github.com/evinbrijesh/vaanikit.git
cd vaanikit
pip install -e ".[dev]"
```

### Scaffold Your First Agent

Use the bundled CLI to generate a complete runnable project in 5 seconds:

```bash
kelvi init my-delivery-agent --template delivery
cd my-delivery-agent
python main.py
```

### Quickstart Agent Example

```python
from kelvi import Agent, tool

agent = Agent(
    language="ml-IN",
    stt="gnani-prisma",
    tts="gnani-timbre",
    reasoning="evon",
)

@agent.tool(
    name="check_order_status",
    description="Check the status of a customer order"
)
async def check_order_status(order_id: str) -> dict:
    return {
        "order_id": order_id,
        "status": "Out for delivery",
        "eta_minutes": 12,
    }

if __name__ == "__main__":
    agent.run()
```

---

## 3. Core Concepts

### Session Engine & Lifecycle
A `Session` tracks caller dialogue turns, context variables, and active states (`awaiting_slot`, `awaiting_confirmation`, `active`, `completed`).

### Memory & Conversational Trap Prevention
Kelvi AI isolates colloquial exasperation markers (*"ഞാൻ ഓൾറെഡി പറഞ്ഞല്ലോ"*, *"already told you"*) from caller names and slot values, preventing conversational memory corruption.

### Confirmation Guardrails
High-stakes operations (cancellations, financial deductions, bookings) specify `requires_confirmation=True`. The engine automatically intercepts the execution, generates a localized confirmation prompt in the caller's dialect, and only invokes the underlying Python function once the caller explicitly affirms.

---

## 4. Indian-Language Engine

### Supported Languages

| Language | Code | Default TTS Voice | Transliteration Badge |
| :--- | :--- | :--- | :--- |
| **Malayalam** | `ml-IN` | Reshma | Manglish (Latin) |
| **Hindi** | `hi-IN` | Nalini | Hinglish (Latin) |
| **Tamil** | `ta-IN` | Asmita | Tanglish (Latin) |
| **Telugu** | `te-IN` | Suhana | Telugu-English |
| **Kannada** | `kn-IN` | Saanvi | Kannada-English |
| **Bengali** | `bn-IN` | Kirra | Benglish |
| **Gujarati** | `gu-IN` | Falak | Gujarati-English |
| **Marathi** | `mr-IN` | Zahira | Marathi-English |
| **Punjabi** | `pa-IN` | Mehuli | Punjabi-English |
| **Indian English** | `en-IN` | Kaveri | Native Latin |

### Spoken DateTime Formatter
Prevents robotic recitation of ISO strings. Converts timestamps (`2026-11-10T10:00:00`) into colloquial Malayalam syntax:
`"നാളെ രാവിലെ 10:00-ന്"` (Tomorrow at 10:00 AM).

---

## 5. Tools System

Tools are ordinary Python functions decorated with `@tool`:

```python
from kelvi import tool

@tool(
    name="cancel_order",
    description="Cancel active customer order",
    requires_confirmation=True,
    confirmation_prompt={
        "ml-IN": "ഓർഡർ റദ്ദാക്കണമെന്ന് ഉറപ്പാണോ?",
        "hi-IN": "क्या आप आर्डर रद्द करना चाहते हैं?",
        "en-IN": "Are you sure you want to cancel your order?",
    }
)
async def cancel_order(order_id: str) -> dict:
    return {"status": "cancelled", "refund": "₹340"}
```

The runtime automatically handles:
- JSON schema parameter generation
- Type validation
- Execution timeouts
- Engine X-Ray telemetry logging

---

## 6. Provider Status & Adapters

| Provider / Stack | Component | Status | Description |
| :--- | :--- | :--- | :--- |
| **Gnani Prisma** | STT Adapter | **Stable** | 14M+ telephonic hours acoustic model streaming sub-200ms |
| **Gnani Timbre** | TTS Adapter | **Stable** | Regional neural voices in 48kHz WAV |
| **Evon v3.3** | Reasoning LLM | **Stable** | 30B MoE model pre-trained natively on 11 Indian languages |
| **Deterministic Rules** | Fast-Path | **Stable** | <2ms local rule matcher consuming 0 credits and 0 tokens |
| **Twilio TwiML** | Telephony | **Experimental** | Standard telephony webhook integration |
| **Bidirectional Streaming** | LiveKit / WebSockets | **Planned** | Full-duplex WebSocket streaming for low-latency barge-in |
| **MongoDB** | Database | **Planned** | Alternative document store adapter |

---

## 7. Reference Applications

1. **Healthcare Clinic Assistant** (`app/`):
   - Appointment booking with conflict slot suggestions.
   - Atomic partial unique indexing in PostgreSQL.
   - Hosted demo accessible at `/demo`.
2. **QuickBites Delivery Assistant** (`examples/delivery_agent/`):
   - Standalone 60-line quick-commerce assistant.
   - Order tracking, partner bridge, and cancellation confirmation.
