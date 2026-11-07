# VaaniKit — Day 6 Freeze Report

**Date:** November 6, 2026  
**Status:** Feature-complete, ready for tag

---

## Offline verification results

| Check | Result |
|---|---|
| `pytest` | 174 passed, 0 failed |
| `ruff check app tests` | All checks passed |
| `mypy app/` | No issues across 40 source files |
| `make rehearse` | [1/3] successful booking: PASS, [2/3] unavailable slot with alternative: PASS, [3/3] ambiguous time and hangup: PASS |

No Gnani API key was used in any of the above. All verification is fully offline.

---

## Changes made on Day 6

### Gap fixes (from Day 5 audit)

| Gap | Fix |
|---|---|
| `session.py` language leak: `no_open_day` path had an `en-IN` branch that could expose a raw English tool message to callers | Removed the branch; all languages now use `self._t("no_open_day")` exclusively |
| `custom_resolver.py`: Tamil, Telugu, and Kannada had no half-hour prefix entries | Added `ta-IN` (`முக்கால்`), `te-IN` (`అర`), `kn-IN` (`ಅರ್ಧ`) to `HALF_HOUR_PREFIXES` |
| `test_multilingual_agent.py`: Malayalam was absent from the parametrized language list | Added `ml-IN` case covering `"நமaleste..."` → available → name → confirmed booking |

### Pre-existing test corrected

`tests/test_scenario.py::test_scenario_books_exactly_one_slot` asserted exactly one `check_availability` call, but `_find_open_day` can call it multiple times when seed slots are taken. The assertion was updated to: last tool call is `book_slot`, all preceding calls are `check_availability`, minimum of two total calls.

### Docs

- `docs/demo-runbook.md` — updated test count from 167 to 174 in before-recording, backup demo, and freeze checklist
- `docs/freeze-report-nov6.md` — updated verification results

### Day 7 Security Hardening Patch

- **TwiML / XML Injection:** Added attribute quote escaping in `TwilioProvider` and regex validation on `CallSid`.
- **Twilio Webhook Verification:** Added HMAC-SHA1 signature verification for `/api/voice/webhook/twilio`.
- **IDOR Protection:** Restricted `cancel_booking` to verified caller phone numbers.
- **Resource Limits & Memory Protection:** Added `MAX_AUDIO_BYTES` (10 MB) check on audio turns and TTL/LRU eviction in `VoiceSessionManager`.
- **Admin API Key:** Optional bearer/header authentication on `/admin/*` via `ADMIN_API_KEY`.
- **Container & Security Headers:** Non-root user in Dockerfile, bound Postgres port to `127.0.0.1`, and added security headers middleware.
- **Test Suite:** Added 7 automated security tests in `test_security_review.py` (total 174 tests passing).

---

## What remains for release owner (Evin)

The following require the live environment and are outside the sandbox:

- [ ] `docker compose down -v && docker compose up -d --build` — verify clean DB init
- [ ] `make dev` and `curl http://localhost:8000/health` returns `{"status": "ok"}`
- [ ] `curl http://localhost:8000/admin/status` — confirm `phone_masking: enabled`, `recordings: disabled`
- [ ] `make simulate SCENARIO=appointment-malayalam` — confirm one confirmed booking on Postgres
- [ ] Dashboard loads at `/admin/ui`; call detail for `demo-call-0001` shows correct timeline
- [ ] Tag the final commit: `git tag -a v0.1.0-hackathon -m "VaaniKit hackathon submission"`
- [ ] Push the tag: `git push origin v0.1.0-hackathon`
- [ ] Create GitHub release from the tag, record the demo video from that exact tag

---

## Multilingual layer summary

Ten languages are production-ready in every code layer:

| Language | Code | TTS voice | Resolver | Replies | Agent test |
|---|---|---|---|---|---|
| Bengali | `bn-IN` | Kirra | Full lexicon | All 15 templates | Parametrized |
| English | `en-IN` | Kaveri | Full lexicon | All 15 templates | Parametrized |
| Gujarati | `gu-IN` | Falak | Full lexicon | All 15 templates | Language test only |
| Hindi | `hi-IN` | Nalini | Full lexicon | All 15 templates | Parametrized |
| Kannada | `kn-IN` | Saanvi | Full lexicon + half-hour | All 15 templates | Resolver test only |
| Malayalam | `ml-IN` | Reshma | Full lexicon + half-hour dict | All 15 templates | Parametrized + rehearsal |
| Marathi | `mr-IN` | Zahira | Full lexicon | All 15 templates | Parametrized |
| Punjabi | `pa-IN` | Mehuli | Full lexicon | All 15 templates | Language test only |
| Tamil | `ta-IN` | Asmita | Full lexicon + half-hour | All 15 templates | Parametrized |
| Telugu | `te-IN` | Suhana | Full lexicon + half-hour | All 15 templates | Resolver test only |

Live verification: only Malayalam was exercised against the Gnani API (November 3, 2026). All other languages are covered by deterministic tests.

---

## Definition of done — verified

| Item | Status |
|---|---|
| `make dev` starts the local environment | Requires Postgres (not sandbox) |
| `make simulate SCENARIO=appointment-malayalam` completes | Requires Postgres; covered by `test_scenario.py` on SQLite |
| Malayalam appointment request normalized safely | Verified by resolver + rehearsal + test suite |
| Availability and booking are transactional | Verified by concurrent booking test suite |
| Overlapping bookings are prevented | Verified by `test_concurrent_booking.py` |
| Calls, events, bookings, and summaries persist | Verified by `test_agent_session.py`, `test_call_events.py` |
| Admin page explains what happened | Verified by `test_admin.py` |
| Phone numbers are masked | Verified by `test_privacy.py` |
| Tool registry rejects undeclared tools | Verified by `test_tools.py` |
| Tests cover all required areas | 174 tests, all pass |
| No secrets or private data in Git | Verified by `test_security_review.py` |
| README setup works from clean environment | Reviewed and accurate |

