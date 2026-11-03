# Demo fixtures and data reset

Every person, phone number, clinic, booking, and transcript in this repository is
synthetic. No real patient data, real phone numbers, private recordings, or customer
conversations are included.

## Synthetic clinic

| Field | Value |
| --- | --- |
| Name | `Nila Family Clinic (synthetic demo)` |
| Time zone | `Asia/Kolkata` |
| Hours | 09:00–17:00, 30-minute slots |
| Working days | Monday–Friday (`0,1,2,3,4`) |
| Capacity shown | 16 slots per open day |

## Seeded calls

Created once on startup when the `calendars` table is empty (`app/db/seed.py`).

| Call SID | Caller | Status | Outcome | Story |
| --- | --- | --- | --- | --- |
| `demo-call-0001` | `+919000000001` | `completed` | `booked` | Anjali Menon books the next open day at 10:00 |
| `demo-call-0002` | `+919000000003` | `completed` | `booked` | Rahul Nair asks for 10:00, accepts 10:30 |
| `demo-call-0003` | `+919000000002` | `failed` | `abandoned` | Date could not be resolved; caller hangs up |
| `demo-call-0004` | `+919000000004` | `transferred` | `transferred` | Insurance question handed to a human |

The seeded day is the next Monday–Friday after the seed runs. The two seeded bookings
occupy 10:00 and 10:30 on that day, which is what makes the conflict demo in the
[Malayalam script](malayalam-demo-script.md) deterministic.

## Seeded bookings

| Patient | Caller | Slot | Status | Notes |
| --- | --- | --- | --- | --- |
| Anjali Menon | `+919000000001` | next open day, 10:00 | `confirmed` | `Synthetic demo booking` |
| Rahul Nair | `+919000000003` | next open day, 10:30 | `confirmed` | `Synthetic demo booking` |

## Caller numbers used by scripts

All numbers use the `+91 90000 000xx` range, reserved here for synthetic fixtures.

| Source | Number |
| --- | --- |
| `make simulate` (`app/scenarios/appointment_malayalam.py`) | `+919000000010` |
| `make rehearse` call 1 | `+919000000021` |
| `make rehearse` call 2 | `+919000000022` |
| `make rehearse` call 3 | `+919000000023` |
| Tests | `+919000000001`–`+919000000006`, `+919000000099` |

`tests/test_synthetic_data.py` fails if a seeded call or booking uses a number outside
`^\+9190000000\d{2}$`, if the clinic name loses its "synthetic demo" marker, if any
booking notes differ from the synthetic marker, or if any audio file appears in the
repository.

## Reset the demo data

The seed is idempotent: it only runs when no calendar exists. To get a clean set of
calls and bookings:

With Docker Compose (deletes the database volume):

```bash
docker compose down -v
docker compose up -d --build
```

With a local PostgreSQL (for example the Compose `db` service on port 5433):

```bash
psql "postgresql://vaanikit:vaanikit@localhost:5433/vaanikit" \
  -c "TRUNCATE bookings, call_events, calls, calendars RESTART IDENTITY CASCADE;"
# Restart the API so startup seeding runs again.
```

Without touching the database, `make rehearse` always starts from a fresh temporary
SQLite database, so it is safe to run before every demo.

## Privacy behavior to verify

- `/admin/calls`, `/admin/calls/{id}`, and `/admin/bookings` return masked numbers
  (for example `+919000000010` becomes `+********0010`).
- `/admin/status` reports `phone_masking: "enabled"` and `recordings: "disabled"`.
- There is no recording subsystem: no audio is written, served, or stored.
- `.env` is git-ignored; only `.env.example` is committed. Never put a real
  `GNAI_API_KEY_ID` in `agent.yaml` — it uses `${GNAI_API_KEY_ID}` substitution.

Run the checks with:

```bash
make test
```
