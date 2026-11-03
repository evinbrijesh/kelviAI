# Malayalam demo script

Three scripted calls that demonstrate booking, conflict handling, and clarification.
The same flow runs deterministically with no API key or database:

```bash
make rehearse
# or, without make:
.venv/Scripts/python.exe -m app.scenarios.rehearsal
```

`make rehearse` uses a temporary SQLite database, seeds the synthetic clinic, runs the
three calls below, and prints `PASS`/`FAIL` per call. Use it as the official fallback
when the live Gnani STT/TTS path is unavailable. Do not present a simulated call as a
live one: say that the dialogue engine is running locally.

For a spoken demo against PostgreSQL, start the API (`make dev`), reset the demo data
(see [fixtures](demo-fixtures.md)), and use the utterances below in order. The agent
speaks first with the greeting from `agent.yaml`:

> നമസ്കാരം, ഞാൻ വാണികിറ്റ് അസിസ്റ്റന്റ് ആണ്. എങ്ങനെ സഹായിക്കാം?

## Call 1 — successful booking

| Turn | Speaker | Utterance | Expected result |
| --- | --- | --- | --- |
| 1 | Caller | നാളെ ഉച്ചയ്ക്ക് 2 മണിക്ക് അപ്പോയിന്റ്മെന്റ് വേണം | Resolves tomorrow at 14:00, `check_availability`, offers the slot |
| 2 | Agent | `<date> at 14:00 is available.` | State `awaiting_name` |
| 3 | Caller | എന്റെ പേര് മീര കൃഷ്ണൻ | Extracts "മീര കൃഷ്ണൻ", asks to confirm |
| 4 | Agent | `Confirming മീര കൃഷ്ണൻ, <date> at 14:00, Nila Family Clinic (synthetic demo). Shall I book it?` | State `awaiting_confirmation` |
| 5 | Caller | അതെ, ബുക്ക് ചെയ്യാം | Calls `book_slot`, books 14:00, returns a reference |
| 6 | Agent | `മീര കൃഷ്ണൻ, an appointment at ... has been booked ... (reference N). Thank you!` | State `completed`, call status `completed` |

If the clinic is closed tomorrow, the agent announces the closed day and checks the
next day (up to a week). If 14:00 is already taken (repeat demos), it offers the
nearest open slot; accept it and continue.

## Call 2 — requested slot unavailable, alternative accepted

Requires the seeded 10:00 and 10:30 bookings to still exist.

| Turn | Speaker | Utterance | Expected result |
| --- | --- | --- | --- |
| 1 | Caller | നാളെ രാവിലെ 10 മണിക്ക് വേണം | Resolves tomorrow at 10:00 |
| 2 | Agent | `<date> at 10:00 is taken; the nearest open slot is 11:00.` | Conflict detected; offers 11:00 |
| 3 | Caller | എന്റെ പേര് രാഹുൽ നായർ | Asks to confirm 11:00 |
| 4 | Caller | അതെ, ബുക്ക് ചെയ്യാം | Books 11:00, state `completed` |

The reply wording depends on which slots are booked. What matters is that the agent
reports the conflict and offers a later slot, never books the conflicting time.

## Call 3 — ambiguous request, caller hangs up

| Turn | Speaker | Utterance | Expected result |
| --- | --- | --- | --- |
| 1 | Caller | ഒരു അപ്പോയിന്റ്മെന്റ് വേണം | No date or time; state `clarifying` |
| 2 | Agent | ക്ഷമിക്കണം, ഏത് തീയതിയും സമയവുമാണ് ഉദ്ദേശിച്ചത് എന്ന് വ്യക്തമാക്കാമോ? | Asks for a date and time |
| 3 | Caller | (silence, then disconnect) | `hangup()` records a failed call with summary `Caller hung up before completing the request.` |

If the caller answers with an unparseable request twice (default
`max_clarifications = 2`), the agent records `date_unresolved`, ends the call as
`failed`, and offers a human handoff. It never guesses a slot.

## Pronunciation checks

Model configuration: Gnani Prisma `prisma-v3.0` (`ml-IN`) for STT, Timbre `timbre-v2.5`
for TTS. Before the demo, read each line once and confirm the transcript matches.

| Malayalam | Rough pronunciation | Watch for |
| --- | --- | --- |
| നമസ്കാരം | na-mas-KAA-ram | Greeting is spoken as one word, not "namas-karam" |
| അപ്പോയിന്റ്മെന്റ് | ap-POINT-ment | Loanword; do not transcribe as "appointment" in the Malayalam field |
| നാളെ | NAA-le | Means tomorrow, not "today" (ഇന്ന്) |
| രാവിലെ | RAA-vi-le | Morning marker; keeps 10 മണി at 10:00, not 22:00 |
| ഉച്ചയ്ക്ക് | uch-CHAI-kk | Afternoon marker; shifts 2 മണി to 14:00 |
| മണി | MA-ni | "o'clock"; required after the hour number |
| മീര കൃഷ്ണൻ | MEE-ra KRISH-nan | Name must be captured whole in `caller_name` |
| രാഹുൽ നായർ | RAA-hul NAA-yar | Name must be captured whole |
| അതെ | a-THE | Confirmation; maps to "yes" |
| ബുക്ക് ചെയ്യാം | BOOK chey-YAAM | Confirmation; triggers `book_slot` |
| വ്യക്തമാക്കാമോ | vyak-tha-MAAK-kaa-mo | Clarification prompt; the reply must include it |

Also check that "ഒന്ന്" through "പന്ത്രണ്ട്" resolve to 1–12, and that "പത്തര" resolves
to 10:30. The resolver tests cover these mappings (`tests/test_resolver.py`).

## What to show on the dashboard

Open `/admin/ui` after the calls. The Calls tab refreshes every 10 seconds (the
**Live** toggle pauses it). Open each call to show the resolved date/time, the
`check_availability` / `book_slot` arguments and results, latency, and the final
outcome. Phone numbers stay masked (`+919000000010` is shown as `+********0010`) and the
status cards show recordings as `disabled`.
