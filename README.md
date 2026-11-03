# VaaniKit

Open-source Indian-language-first starter kit for building tool-using voice agents.

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

## Run the simulation

```bash
make db-up
make simulate SCENARIO=appointment-malayalam
```

The scenario writes to the configured database:

1. Resolves "നാളെ രാവിലെ 10 മണിക്ക് അപ്പോയിന്റ്മെന്റ് വേണം" into a date and time.
2. Checks availability, moving to the next open day when the clinic is closed that day.
3. Offers the nearest open slot when the requested one is already taken.
4. Books the slot transactionally and records every caller turn, agent turn, and tool
   call in `call_events`.
5. Prints a summary with the booking reference and the number of recorded events.

Each run creates one new call and books the next open slot, so the simulation stays
usable on a database that already contains demo bookings. Duplicate and overlapping
requests are rejected by an overlap check plus a partial unique index in the database.

For a repeatable, three-call demo that does not need PostgreSQL or a Gnani API key:

```bash
make rehearse
```

It runs a successful booking, an unavailable slot with an accepted alternative, and an
ambiguous request followed by a hangup against a temporary SQLite database, printing
`PASS`/`FAIL` for each call. See the [Malayalam demo script](docs/malayalam-demo-script.md)
for the exact utterances and pronunciation checks, and
[demo fixtures](docs/demo-fixtures.md) for the synthetic data and reset steps.

## Admin API and dashboard

The admin surface is a self-contained dashboard at `http://localhost:8000/admin/ui`
(the root URL redirects there) plus a JSON API. Replace the port if you started the
API with `PORT=...`. Both are explicitly non-production,
use synthetic data only, and mask phone numbers in every view.

The AMOLED dashboard background is the Swell preset from `asciify-engine`, bundled
by `npm run build:admin` into `app/admin/static/asciify.bundle.js`. The built bundle
is committed, so Node is only needed when changing
`app/admin/frontend/asciify-background.js`.

The dashboard lists calls and bookings, and opens a call detail with the resolved
date/time, outcome, summary, errors, linked bookings, and a chronological event
timeline including tool arguments, tool results, and latency. Call details are
hash-addressable (`#call-N`), and empty, loading, and error states are built in.

The dashboard refreshes itself every 10 seconds while the Calls/Bookings view is
visible (pause with the **Live** toggle, or press **Refresh** for an immediate load).
The status cards include phone-masking and recording status; recordings are disabled
by design and the API never returns audio.

| Endpoint | Purpose |
| --- | --- |
| `GET /admin` | Index and non-production notice |
| `GET /admin/ui` | Browser dashboard |
| `GET /admin/static/*` | Bundled dashboard assets |
| `GET /admin/calls` | Recent calls with masked caller numbers |
| `GET /admin/calls/{id}` | Call detail: resolution, events, bookings, errors |
| `GET /admin/bookings` | Upcoming bookings with clinic and linked call |
| `GET /admin/status` | Row counts, phone-masking, and recording status |
| `GET /admin/tools` | Tools declared in `agent.yaml` with their argument schemas |

## Voice API and live speech

VaaniKit includes a live voice bridge connecting Gnani STT (`prisma-v3.0`), the `AgentSession` state machine, and Gnani TTS (`timbre-v2.5` voice `Reshma`).

Verify the live Gnani speech pipeline end-to-end:

```bash
make voice-check
```

The Voice API provides REST and telephony webhook endpoints:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/voice/status` | GET | Inspect STT/TTS adapter status, voice model, and active calls |
| `/api/voice/session/start` | POST | Start a voice session and return the synthesized greeting audio |
| `/api/voice/session/{call_sid}/turn` | POST | Submit caller audio (base64 JSON or binary WAV/PCM) and receive synthesized agent audio |
| `/api/voice/session/{call_sid}/audio` | GET | Retrieve the latest synthesized agent audio for playback |
| `/api/voice/session/{call_sid}/hangup` | POST | Gracefully terminate an ongoing voice session |
| `/api/voice/webhook/twilio` | POST | Telephony webhook receiving calls and returning standard TwiML |

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

This is a local demo deployment, not a hosted service: there is no public URL, no
authentication, and no TLS. It uses synthetic data only, masks phone numbers, and
records no audio. Do not expose it to the internet. If the Gnani live API is
unavailable, the deterministic local simulation and rehearsal remain the official
demo path (see [the demo script](docs/malayalam-demo-script.md)).

## Configuration

Edit `agent.yaml` to configure:

- Agent language, greeting, persona, and rules
- STT/TTS models (Gnani Prisma and Timbre) and the date/time resolver
- Declared tools and their JSON argument schemas
- Database connection (via `${DATABASE_URL}`)

Unknown or malformed sections fail startup with a short message instead of a traceback.
`/health` returns `503` whenever configuration or the database is unavailable.

## Development

```bash
make test     # pytest
make lint     # ruff + mypy
```

## Documentation

- [Execution Plan](docs/VaaniKit_Execution_Plan_Nov1-6.md)
- [Integration Notes](docs/integration-notes.md)
- [Malayalam Demo Script](docs/malayalam-demo-script.md)
- [Demo Fixtures and Data Reset](docs/demo-fixtures.md)

## License

Apache-2.0
