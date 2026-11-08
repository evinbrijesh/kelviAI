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
        Resolver["CustomDateTimeResolver\n(app/llm/custom_resolver.py)\nMultilingual date/time extraction"]
        Registry["ToolRegistry\n(app/tools/registry.py)\nJSON Schema validation & timeouts"]
    end
    
    subgraph SpeechLayer ["Gnani Live Speech Layer"]
        STT["Gnani STT: prisma-v3.0\n(indic-auto, multipart audio_file)"]
        TTS["Gnani TTS: timbre-v2.5\n(per-language voice, 48kHz WAV)"]
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
  * Uses `/stt/v3` with multipart payload `audio_file` and `language_code=indic-auto`.
  * Returns the transcript in its native script plus the spoken `detected_language_code`.
* **Text-to-Speech (TTS) — Gnani Timbre v2.5:**
  * Uses `/api/v1/tts/inference` with a documented voice for the detected language (see the table below) and structured `audio_config`.
  * Delivers high-fidelity 48 kHz mono linear PCM inside a standard WAV container.
* **Language Handling — `app/llm/language.py`:**
  * Supports the ten documented Prisma/Timbre languages: Bengali (`bn-IN`), English (`en-IN`), Gujarati (`gu-IN`), Hindi (`hi-IN`), Kannada (`kn-IN`), Malayalam (`ml-IN`), Marathi (`mr-IN`), Punjabi (`pa-IN`), Tamil (`ta-IN`), and Telugu (`te-IN`).
  * Voice calls use the STT-detected language; text and simulation paths detect the language from its Unicode script (with Marathi keyword hints for Devanagari).
  * Agent replies, clarifications, confirmations, and booking summaries are rendered in the caller's language from `app/agent/replies.py`.
* **Date/Time Resolution — `CustomDateTimeResolver`:**
  * Rather than relying on unverified external LLM parameters, colloquial temporal phrases in every supported language (e.g. *"നാളെ രാവിലെ 10 മണിക്ക്"*, *"कल सुबह 10 बजे"*, *"நாளை காலை 10 மணிக்கு"*) are parsed by a deterministic resolver grounded in Indian Standard Time (`Asia/Kolkata`).
  * Handles relative days, morning/afternoon/evening/night qualifiers, o'clock markers, half-hours, native-script digits, ISO and `DD/MM/YYYY` dates, and structured times.
  * Emits structured ISO dates, normalized times, confidence scores, and diagnostic explanations.
* **Code-mixed booking phrases:**
  * Handles focused Hinglish, Manglish, Tanglish and Benglish patterns, including `kal subah 10 baje`, `naale raavile 10 mani`, `naalai kaalai 10 mani` and `kal shokal 10 tay`.
  * Recognizes romanized name prefixes and confirmations. Negations take priority, so `don't book`, `nahi book karo` and `book venda` do not create a booking.
  * Native script and provider language hints retain priority. This is phrase-based parsing, not unrestricted multilingual understanding.
* **Warp & Evon Stubs:**
  * Modular stubs exist in `app/llm/warp_stubs.py` and `app/llm/evon_stub.py`. Because Warp and Evon lack live documentation, the system defaults to Path B (verified Gnani Speech APIs + deterministic resolver) without brittle undocumented assumptions.

### Per-language TTS voices

| Language | Code | Voice |
| --- | --- | --- |
| Bengali | `bn-IN` | Kirra |
| English | `en-IN` | Kaveri |
| Gujarati | `gu-IN` | Falak |
| Hindi | `hi-IN` | Nalini |
| Kannada | `kn-IN` | Saanvi |
| Malayalam | `ml-IN` | Reshma |
| Marathi | `mr-IN` | Zahira |
| Punjabi | `pa-IN` | Mehuli |
| Tamil | `ta-IN` | Asmita |
| Telugu | `te-IN` | Suhana |

These mappings are the defaults; `model.tts.voices` in `agent.yaml` overrides any language, and `model.tts.voice` remains the fallback.

---

## Multilingual Conversation Flow & Limitations

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

1. **Greeting (`AWAITING_SLOT`):** Plays the configured `agent.greeting` (Malayalam by default) and requests the desired slot. The greeting is sent before the caller speaks, so it stays in the configured language; every reply after the first turn follows the caller.
2. **Language Detection:** Voice turns take the STT `detected_language_code`; text and simulation turns detect the Unicode script. The first detected language locks the call for text paths so a later Latin-script name does not flip an Indic conversation to English, while voice turns may still change language when the STT hint changes.
3. **Ambiguity Handling (`CLARIFYING`):** If the caller's time expression has low confidence (< 0.6) or is incomplete, the agent asks for clarification in the caller's language (*"ദയവായി സമയം വ്യക്തമാക്കാമോ?"*, *"कृपया समय स्पष्ट करें?"*). Bounded at 2 clarification attempts before failing cleanly.
4. **Availability & Conflict Resolution:** The tool checks calendar open hours and conflicts. If the slot is taken or the clinic is closed, the agent automatically suggests the nearest open alternative.
5. **Name Capture (`AWAITING_NAME`):** Extracts the caller/patient name from all supported scripts.
6. **Confirmation (`AWAITING_CONFIRMATION`):** Repeats the clinic, date, time, and patient name in the caller's language before booking.
7. **Transactional Commit (`COMPLETED`):** Books the slot in the database, releases the temporary lock, records the booking ID, and issues a confirmation reference in the caller's language.
8. **Human Handoff (`TRANSFERRED`):** If the caller's request cannot be satisfied or clarification is exceeded, the call transfers to a human operator.

### 2. Limitations

* **Language Detection Scope:** Detection covers the ten documented Prisma/Timbre languages. Romanized Indic input written in Latin script is treated as English (`en-IN`), and unsupported languages fall back to the configured default.
* **Greeting Language:** The first greeting uses `agent.language` because no caller audio exists yet; replies mirror the caller from the first processed turn onward.
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

The app creates its tables on startup and seeds a fictional clinic, five demo calls
(booked, conflict resolved, unresolved, transferred, and a Hindi call), plus three
confirmed demo bookings the first time it runs against an empty database.

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

## Demo

The screenshots below come from the seeded synthetic dataset. The 60-second script,
three-minute backup demo, and freeze checklist are in the
[demo runbook](docs/demo-runbook.md).

| Dashboard | Call detail |
| --- | --- |
| ![Admin dashboard](docs/screenshots/admin-dashboard.png) | ![Call detail with event timeline](docs/screenshots/admin-call-detail.png) |

Mobile layout at 390px:

![Admin dashboard on mobile](docs/screenshots/admin-mobile.png)

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

## Browser voice demo (Stage 2)

Open `/demo` on the running local server. The Stage 1 dashboard remains at `/admin/ui`.

1. Press **Start demo call** and listen to the Malayalam greeting.
2. Press **Record your turn**, speak a date and time, then **Send this turn**.
3. Give a fictional name, check the spoken date and time, and confirm or decline.
4. Inspect the transcript and booking reference, then open the call dashboard.

The browser captures mono PCM with AudioWorklet and sends 16 kHz, 16-bit WAV to
Prisma, not Web Speech dictation. Turns auto-send at 25 seconds, below the REST
provider limit. End call discards unsent audio and releases the microphone.
Microphone audio is held in memory, not saved as a recording; transcripts and
synthetic bookings are persisted. Use localhost or HTTPS in a current browser.
If autoplay is blocked, use the reply's audio controls. After a failed or timed-out
turn, end the session instead of resending a potentially processed confirmation.

This is a non-production demo, not an open public service. Do not enter real
patient details or expose the unauthenticated voice API to the internet. Record
Stage 1 before exercising voice calls against the same database: new calls and
bookings will change the dashboard counts. Later videos can show Stage 2; nominate
the final public post when submitting the contest entry.

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

* Agent language (`agent.language`, the greeting and fallback language), greeting, persona, and rules
* STT/TTS models — keep `stt.language: indic-auto` so Prisma reports the spoken language per turn
* `tts.voices` per-language voice overrides (the documented defaults are built in; `tts.voice` is the fallback)
* The date/time resolver
* Declared tools and their JSON argument schemas
* Database connection (via `${DATABASE_URL}`)

Unknown or malformed sections fail startup with a safe `ConfigError` instead of a traceback.
`/health` returns `503` whenever configuration or the database is unavailable.

---

## Verification & Testing

VaaniKit includes a test suite covering database isolation, concurrent slot booking races, security audits, admin routes, and Gnani adapters:

```bash
make test     # pytest (318 unit & integration tests)
make lint     # ruff + mypy (0 errors across 40 source files)
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
* [Demo Runbook](docs/demo-runbook.md)
* [Integration Notes](docs/integration-notes.md)
* [Malayalam Demo Script](docs/malayalam-demo-script.md)
* [Demo Fixtures and Data Reset](docs/demo-fixtures.md)

---

## License

Apache-2.0
