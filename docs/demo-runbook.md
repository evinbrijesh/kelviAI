# Demo runbook and freeze checklist

The demo uses only the synthetic clinic, calls, and bookings from
[demo fixtures](demo-fixtures.md). No real patient data, phone numbers, recordings,
or customer conversations are involved.

## What the demo proves

- A Malayalam request is resolved into a date/time with a confidence score.
- Availability is checked, conflicts get alternatives, and booking is transactional.
- Every caller turn, tool call, tool result, and latency is persisted.
- The admin page shows the story without opening the database.
- Phone numbers are masked and recordings are disabled.

## Before recording

```bash
git pull --ff-only
make install
make test          # 112 tests
make lint          # ruff + mypy
make rehearse      # three-call local rehearsal, no network
```

Start from a clean dataset:

```bash
docker compose down -v
docker compose up -d --build
curl http://localhost:8000/admin/status
```

`/admin/status` should report `calls: 4`, `bookings: 2`, `phone_masking: enabled`,
and `recordings: disabled`. If port 8000 is taken, start with `make dev PORT=8032`
and use that port in every URL below. The reset steps for an existing local
PostgreSQL are in [demo fixtures](demo-fixtures.md).

Keep `make rehearse` open in a terminal as the offline fallback. It uses a temporary
SQLite database, writes nothing persistent, and passes without PostgreSQL or a Gnani
API key.

## 60-second demo

| Time | On screen | Say |
| --- | --- | --- |
| 0:00–0:07 | Dashboard at `/admin/ui` | "VaaniKit books Malayalam appointments by voice. This admin page is non-production and uses synthetic data only." |
| 0:07–0:17 | Status cards and Calls list | "Four demo calls: two booked, one abandoned, one transferred. Caller numbers are masked in every view." |
| 0:17–0:35 | Open `demo-call-0001` | "The request resolved to 2026-11-04 at 10:00 IST with 95% confidence, and produced one confirmed booking." |
| 0:35–0:52 | Events timeline | "The timeline records the Malayalam turn, the resolved date, the availability tool call and result, and the booking commit — twelve events with latency." |
| 0:52–1:00 | Bookings tab, then privacy cards | "Recordings are disabled and audio is never returned. Live refresh polls every ten seconds." |

Keep the cursor away from the **Live** toggle so the demo does not pause refreshes.

## Backup demo (about three minutes)

1. **0:00–0:30 — Deterministic rehearsal.** Run `make rehearse` and show
   `[1/3] ... PASS`, `[2/3] ... PASS`, `[3/3] ... PASS`.
2. **0:30–1:10 — Evidence.** Run `make test` and `make lint`; show 112 tests passing
   and no lint or type errors.
3. **1:10–2:00 — Architecture.** Walk the README diagram: FastAPI ingress, the
   explicit `AgentSession` state machine, the deterministic date resolver, the tool
   registry, PostgreSQL persistence, and the polling dashboard.
4. **2:00–2:40 — Admin deep dive.** Repeat the 60-second walkthrough, then open the
   Bookings tab and the event payloads.
5. **2:40–3:00 — Limitations.** State the live path honestly: Warp and Evon are not
   documented, so the project uses verified Gnani STT/TTS plus the deterministic
   resolver; live speech needs credentials and outbound HTTPS, while simulation and
   rehearsal are guaranteed offline.

## Screenshots

| File | Content | Capture size |
| --- | --- | --- |
| `screenshots/admin-dashboard.png` | Dashboard with status cards and calls list | 1440 × 1100 |
| `screenshots/admin-call-detail.png` | Resolved date/time, summary, booking, event timeline | 1440 × 1600 |
| `screenshots/admin-mobile.png` | Mobile dashboard | 390 × 844 |

They were captured from the seeded dataset (four calls, two bookings) with the
non-production notice and masking enabled. To recapture, start the clean stack,
open `/admin/ui` (and `#call-1` for the detail), set the widths above, and take
full-window screenshots without browser chrome. Update the images if the seeded
data or layout changes.

## Freeze checklist — November 6

Run from the exact commit that will be tagged:

- [ ] `make test`, `make lint`, and `make rehearse` pass.
- [ ] Database initializes from a clean environment (`docker compose down -v` then up).
- [ ] `make simulate SCENARIO=appointment-malayalam` completes with one confirmed booking.
- [ ] `/health` returns `ok` and the dashboard loads at the deployed or local URL.
- [ ] `/admin/status` reports masking enabled and recordings disabled.
- [ ] No secrets or real data are staged (`tests/test_security_review.py` covers the checklist).
- [ ] Tag `v0.1.0-hackathon` on the release commit.
- [ ] Create the GitHub release from that tag and record the demo from the tag, not a working tree.

Tagging and publishing the release are release-owner actions and need explicit
approval. Stop adding features after the tag; use November 7–10 only for submission
edits.
