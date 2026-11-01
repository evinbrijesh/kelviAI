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

# 4. Check health
curl http://localhost:8000/health
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

The app creates its tables on startup and seeds a synthetic clinic, two demo calls,
and two demo bookings the first time it runs against an empty database.

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

## Admin API

The admin surface is JSON only and explicitly non-production. Phone numbers are masked
in every response.

| Endpoint | Purpose |
| --- | --- |
| `GET /admin` | Index and non-production notice |
| `GET /admin/calls` | Recent calls |
| `GET /admin/bookings` | Upcoming bookings |
| `GET /admin/status` | Row counts and environment label |
| `GET /admin/tools` | Tools declared in `agent.yaml` with their argument schemas |

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

## License

Apache-2.0
