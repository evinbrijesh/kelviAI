# VaaniKit

Open-source Indian-language-first starter kit for building tool-using voice agents.

VaaniKit combines documented Indian speech models, an explicit dialogue state machine, transactional business tools, database persistence, and an observability dashboard into a production-grade, testable voice platform.

---

## System Architecture

```mermaid
flowchart TD
    Caller["Caller / Telephony Client\n(Twilio, Webhook, REST)"]
    
    subgraph Ingress ["Ingress Layer (FastAPI)"]
        VoiceAPI["/api/voice/session/...\n(Audio turn endpoints)"]
        TwilioWebhook["/api/voice/webhook/twilio\n(TwiML voice ingress)"]
        AdminUI["/admin/ui\n(AMOLED Inspection Dashboard)"]
    end
    
    subgraph Engine ["Orchestration & Voice Engine"]
        VoiceSession["VoiceSession Bridge\n(app/bridge/voice_session.py)\nTurn timing & audio formatting"]
        AgentSession["AgentSession State Machine\n(app/agent/session.py)\nState progression & clarifications"]
        Resolver["CustomDateTimeResolver\n(app/llm/custom_resolver.py)\nMalayalam date/time extraction"]
        Registry["ToolRegistry\n(app/tools/registry.py)\nJSON Schema validation & timeouts"]
    end
    
    subgraph SpeechLayer ["Gnani Live Speech Layer"]
        STT["Gnani STT: prisma-v3.0\n(ml-IN, multipart audio_file)"]
        TTS["Gnani TTS: timbre-v2.5\n(Voice: Reshma, 48kHz WAV)"]
    end
    
    subgraph Storage ["Persistence (PostgreSQL / SQLAlchemy)"]
        DBCalls["Calls & CallEvents\n(Chronological audit log)"]
        DBBookings["Bookings & Calendars\n(Partial unique index conflict prevention)"]
    end
    
    Caller -->|Audio / Form data| Ingress
    VoiceAPI --> VoiceSession
    TwilioWebhook --> VoiceSession
    VoiceSession <-->|Audio bytes| SpeechLayer
    VoiceSession <-->|Dialogue turns| AgentSession
    AgentSession --> Resolver
    AgentSession --> Registry
    Registry -->|Transactional booking| Storage
    AgentSession -->|Persist state & turns| Storage
    AdminUI -->|Live 10s poll| Storage
```

---

## Model & Provider Architecture

VaaniKit is designed around documented, verifiable interfaces with clean fallbacks:

* **Speech-to-Text (STT) — Gnani Prisma v3.0:**
  * Uses `/stt/v3` with multipart payload `audio_file` and language code `ml-IN`.
  * Returns native Malayalam script (`transcript`) with automatic language detection (`detected_language_code`).
* **Text-to-Speech (TTS) — Gnani Timbre v2.5:**
  * Uses `/api/v1/tts/inference` with the documented Malayalam voice **Reshma** and structured `audio_config`.
  * Delivers high-fidelity 48 kHz mono linear PCM inside a standard WAV container.
* **Date/Time Resolution — `CustomDateTimeResolver`:**
  * Rather than relying on unverified external LLM parameters, colloquial Malayalam temporal phrases (e.g. *"നാളെ രാവിലെ 10 മണിക്ക്"*, *"അടുത്ത തിങ്കളാഴ്ച"*) are parsed by a deterministic resolver grounded in Indian Standard Time (`Asia/Kolkata`).
  * Emits structured ISO dates, normalized times, confidence scores, and diagnostic explanations.
* **Warp & Evon Stubs:**
  * Modular stubs exist in `app/llm/warp_stubs.py` and `app/llm/evon_stub.py`. Because Warp and Evon lack live documentation, the system defaults to Path B (verified Gnani Speech APIs + deterministic resolver) without brittle undocumented assumptions.

---

## Supported Malayalam Conversation Flow & Limitations

### 1. Conversation Progression

The `AgentSession` manages dialogue through explicit states:

```text
[IDLE]
  │
  ▼
[AWAITING_SLOT] ──(Ambiguous time)──► [CLARIFYING] (Max 2 retries)
  │                                        │ (Resolved)
  │ (Slot resolved & available)            ▼
  ├────────────────────────────────► [AWAITING_NAME]
  │                                        │
  ▼                                        ▼
[CONFLICT / UNAVAILABLE]            [AWAITING_CONFIRMATION]
  │                                        │
  ▼                                        ▼
Offers nearest open slot             [COMPLETED] ──► Transactional booking reference
  or TRANSFERRED to human
```

1. **Greeting (`AWAITING_SLOT`):** Greets in Malayalam (*"നമസ്കാരം, ഞാൻ വാണികിറ്റ് അസിസ്റ്റന്റ് ആണ്..."*) and requests the desired slot.
2. **Ambiguity Handling (`CLARIFYING`):** If the caller's time expression has low confidence (< 0.6) or is incomplete, the agent asks for clarification (*"ദയവായി സമയം വ്യക്തമാക്കാമോ?"*). Bounded at 2 clarification attempts before failing cleanly.
3. **Availability & Conflict Resolution:** The tool checks calendar open hours and conflicts. If the slot is taken or the clinic is closed, the agent automatically suggests the nearest open alternative.
4. **Name Capture (`AWAITING_NAME`):** Extracts the caller/patient name.
5. **Confirmation (`AWAITING_CONFIRMATION`):** Repeats the clinic, date, time, and patient name before booking.
6. **Transactional Commit (`COMPLETED`):** Books the slot in the database, releases the temporary lock, records the booking ID, and issues a confirmation reference.
7. **Human Handoff (`TRANSFERRED`):** If the caller's request cannot be satisfied or clarification is exceeded, the call transfers to a human operator.

### 2. Limitations

* **Slot Alignment:** Bookings are quantized to 30-minute intervals aligned with clinic working hours.
* **Single Calendar Scope:** Each active session queries and books against a primary active clinic calendar.
* **Audio Requirements:** Inbound telephony audio expects linear PCM or WAV (raw 8/16 kHz streams are automatically wrapped into 16 kHz WAV before reaching STT).
* **Network Connectivity:** Live speech requires outbound HTTPS to `api.vachana.ai`. When offline, the deterministic local rehearsal (`make rehearse`) and database simulation (`make simulate`) provide guaranteed fallback demo paths.

---

## Error, Timeout, and Fallback Behavior

* **Bounded HTTP Timeouts:** All Gnani STT and TTS network requests enforce an explicit 30-second timeout.
* **Audio Stream Validation:** Empty or truncated audio payloads (< 44 bytes) are rejected with `422 Unprocessable Entity` before initiating network calls.
* **Savepoint Isolation:** Slot reservation runs inside a database savepoint. If a concurrent race condition triggers the partial unique index, the transaction rolls back cleanly without losing preceding caller dialogue or call event logs.
* **Caller Disconnect (`hangup`):** Premature caller abandonment records the call status as `failed` with outcome `abandoned`.

---

## Quick Start

Requirements: Python 3.11+, Docker (for PostgreSQL).

```bash
# 1. Install dependencies
make install

# 2. Create your environment file
cp .env.example .env
# Edit .env and set GNAI_API_KEY_ID

# 3. Start PostgreSQL and the API (make dev runs docker compose first)
make dev

# 4. Open the dashboard or check health
#    http://localhost:8000/admin/ui
curl http://localhost:8000/health
```

If port 8000 is already in use, pick another API port and use it in the URLs above:

```bash
make dev PORT=8032
# http://localhost:8032/admin/ui
```

The default `DATABASE_URL` points at `localhost:5432`. If port 5432 is already taken,
pick another host port:

```bash
POSTGRES_HOST_PORT=5433 make db-up
export DATABASE_URL="postgresql://vaanikit:vaanikit@localhost:5433/vaanikit"
```

Without Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d --wait db        # or provide your own PostgreSQL
uvicorn app.main:app --reload
```

On Windows, install GNU make once, then reopen your terminal:

```bash
winget install ezwinports.make
```

The Makefile uses `.venv` automatically when it exists, so activating the virtualenv
is optional. Without make, run the commands directly:

```bash
docker compose up -d --wait db
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
.venv/Scripts/python.exe -m app.scenarios.appointment_malayalam
```

The app creates its tables on startup and seeds a fictional clinic, four demo calls
(booked, conflict resolved, unresolved, transferred), and two confirmed demo bookings
the first time it runs against an empty database.

---

## Run the Simulation & Rehearsal

### 1. Database Simulation
Runs the full Malayalam appointment booking flow against PostgreSQL:

```bash
make db-up
make simulate SCENARIO=appointment-malayalam
```

The scenario writes to the configured database:
1. Resolves *"നാളെ രാവിലെ 10 മണിക്ക് അപ്പോയിന്റ്മെന്റ് വേണം"* into a date and time.
2. Checks availability, moving to the next open day when the clinic is closed.
3. Offers the nearest open slot when the requested one is already taken.
4. Books the slot transactionally and records every caller turn, agent turn, and tool call in `call_events`.
5. Prints a summary with the booking reference and the number of recorded events.

### 2. Three-Call Rehearsal (Zero Dependencies)
For a repeatable demo that does not require PostgreSQL or an active Gnani API key:

```bash
make rehearse
```

It runs a successful booking, an unavailable slot with an accepted alternative, and an
ambiguous request followed by a hangup against a temporary SQLite database, printing
`PASS`/`FAIL` for each call. See the [Malayalam demo script](docs/malayalam-demo-script.md)
for the exact utterances and pronunciation checks, and
[demo fixtures](docs/demo-fixtures.md) for the synthetic data and reset steps.

---

## Live Speech Verification

VaaniKit includes a live speech verification runner exercising Gnani STT (`prisma-v3.0`) and TTS (`timbre-v2.5` voice `Reshma`):

```bash
make voice-check
```

Outputs live latency measurements and transcription accuracy:
```text
1. Synthesizing Malayalam TTS: 'നമസ്കാരം, വാണികിറ്റ് ലൈവ് വോയ്സ് പരിശോധന.'...
   [OK] TTS synthesized in 791 ms (WAV @ 48000 Hz)
2. Transcribing audio through Gnani STT...
   [OK] STT transcribed in 622 ms (ml-IN)
✓ Live speech round-trip verified successfully!
```

---

## Admin API and Dashboard

The admin surface is a self-contained dashboard at `http://localhost:8000/admin/ui`
(the root URL redirects there) plus a JSON API. Both are explicitly non-production,
use synthetic data only, and mask phone numbers in every view (`+********0001`).

The AMOLED dashboard background is the Swell preset from `asciify-engine`, bundled
by `npm run build:admin` into `app/admin/static/asciify.bundle.js`. The built bundle
is committed, so Node is only needed when modifying `app/admin/frontend/asciify-background.js`.

The dashboard lists calls and bookings, and opens a call detail with the resolved
date/time, outcome, summary, errors, linked bookings, and a chronological event
timeline including tool arguments, tool results, and latency.

The dashboard refreshes itself every 10 seconds while the Calls/Bookings view is
visible (pause with the **Live** toggle, or press **Refresh** for an immediate load).

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/admin` | GET | Index and non-production notice |
| `/admin/ui` | GET | AMOLED Browser inspection dashboard |
| `/admin/static/*` | GET | Bundled dashboard assets & fonts |
| `/admin/calls` | GET | Recent calls with masked caller numbers |
| `/admin/calls/{id}` | GET | Call detail: resolution, events, bookings, errors |
| `/admin/bookings` | GET | Upcoming bookings with clinic and linked call |
| `/admin/status` | GET | Row counts, phone-masking, and recording status |
| `/admin/tools` | GET | Tools declared in `agent.yaml` with their schemas |

---

## Voice API & Telephony Ingress

The Voice API provides REST and telephony webhook endpoints for live calls:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/voice/status` | GET | Inspect STT/TTS adapter status, voice model, and active calls |
| `/api/voice/session/start` | POST | Start a voice session and return the synthesized greeting audio |
| `/api/voice/session/{call_sid}/turn` | POST | Submit caller audio (base64 JSON or binary WAV/PCM) and receive synthesized agent audio |
| `/api/voice/session/{call_sid}/audio` | GET | Retrieve the latest synthesized agent audio for playback |
| `/api/voice/session/{call_sid}/hangup` | POST | Gracefully terminate an ongoing voice session |
| `/api/voice/webhook/twilio` | POST | Telephony webhook receiving calls and returning standard TwiML |

---

## Deploy with Docker

`docker compose up` builds and runs the full stack: `app` (FastAPI, API, and
dashboard) and `db` (PostgreSQL 16 with a named volume). The image installs the
package and serves port 8000 inside the container.

```bash
cp .env.example .env            # set GNAI_API_KEY_ID only if you have one
docker compose up -d --build
docker compose ps               # both services should report healthy
curl http://localhost:8000/health
# Dashboard: http://localhost:8000/admin/ui
```

If 8000 or 5432 are already in use, override the host ports:

```bash
APP_HOST_PORT=8034 POSTGRES_HOST_PORT=5433 docker compose up -d --build
# Dashboard: http://localhost:8034/admin/ui
```

After changing application code, rebuild and recreate the app container so the image
picks up the new source:

```bash
docker compose build app
docker compose up -d --force-recreate app
```

The container runs the same startup seed as local development, so the dashboard shows
the four synthetic demo calls immediately.

---

## Configuration

Edit `agent.yaml` to configure:

* Agent language, greeting, persona, and rules
* STT/TTS models (Gnani Prisma and Timbre) and the date/time resolver
* Declared tools and their JSON argument schemas
* Database connection (via `${DATABASE_URL}`)

Unknown or malformed sections fail startup with a safe `ConfigError` instead of a traceback.
`/health` returns `503` whenever configuration or the database is unavailable.

---

## Verification & Testing

VaaniKit includes a test suite covering database isolation, concurrent slot booking races, security audits, admin routes, and Gnani adapters:

```bash
make test     # pytest (112 unit & integration tests)
make lint     # ruff + mypy (0 errors across 38 source files)
```

---

## Contribution Statement

VaaniKit was built by **Evin Brijesh** and **Athul Sunil Kumar**:

* **Evin Brijesh (Owner: Platform, Model Integration & Voice Architecture):**
  * `agent.yaml` schema, configuration loader, and safe startup validation.
  * Gnani STT & TTS adapter interfaces and live verification.
  * `AgentSession` multi-turn dialogue state machine, bounded clarifications, and tool permission guards.
  * `VoiceSession` audio turn bridge, turn latency tracking, and live DB transaction commits.
  * Telephony layer (`app/providers/`), Generic provider, and Twilio TwiML generator.
  * FastAPI Voice API (`/api/voice/...`) and live speech smoke test runner (`make voice-check`).
  * System architecture diagrams, integration documentation, and release orchestration.

* **Athul Sunil Kumar (Owner: Data, Tools, Observability & Frontend):**
  * PostgreSQL schema, database engine setup, and partial unique index conflict prevention.
  * Transactional booking tools (`book_slot`, `check_availability`, `cancel_booking`, `transfer_to_human`).
  * Chronological `CallSessionLog` and event persistence with latency tracking.
  * Self-contained Admin Dashboard (`/admin/ui`) with Asciify Swell animated background and mobile typography.
  * Idempotent synthetic clinic dataset, privacy audits (phone masking, no committed secrets).
  * Concurrent booking race condition test suite and 3-call rehearsal runner (`make rehearse`).

---

## Documentation

* [Execution Plan](docs/VaaniKit_Execution_Plan_Nov1-6.md)
* [Integration Notes](docs/integration-notes.md)
* [Malayalam Demo Script](docs/malayalam-demo-script.md)
* [Demo Fixtures and Data Reset](docs/demo-fixtures.md)

---

## License

Apache-2.0
