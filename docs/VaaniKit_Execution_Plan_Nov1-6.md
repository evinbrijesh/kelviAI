# VaaniKit — Two-Person Execution Plan

**Project:** VaaniKit
**Repository:** [github.com/evinbrijesh/vaanikit](https://github.com/evinbrijesh/vaanikit)
**Owners:** Evin (A) and Athul (B)
**Planning window:** November 1–6, 2026, IST
**Submission deadline:** November 10, 2026, 11:59 PM IST
**Target:** Feature-complete, demo-ready freeze by November 6, leaving November 7–10 for exams, final editing, posting, and submission

## Current situation

The repository is public, uses Apache-2.0, has the initial scaffold, and currently has only two commits. Both contributors are available full-time and are comfortable learning any part of the stack. Work will happen in one repository using feature branches and pull requests.

The PRD remains the source of truth. The MVP is an Indian-language-first starter kit with a Malayalam-focused appointment-booking demo, a configurable tool registry, persistence, observability, local simulation, and one live voice path if the required integrations are available.

The most important unresolved dependency is the exact real-time voice and telephony integration. The official Gnani documentation currently exposes Speech APIs, Agent Builder, and Agent Builder Platform APIs, while the PRD requires Warp as the primary real-time layer. Do not invent undocumented API parameters. Resolve this on Day 1. If the exact Warp path is unavailable, preserve the PRD architecture and ship the fully working local simulation plus the most defensible documented live path available through the registered Gnani access.

## Ownership model

Ownership means the person creates the branch, implements the feature, adds tests, and opens the pull request. The other person reviews it. Neither person should merge their own pull request.

### Evin — Platform, model integration, and release owner

Evin owns:

- `agent.yaml` schema and configuration loading
- Gnani credential and API smoke tests
- Warp/Evon integration investigation
- Evon date/time resolver and structured schemas
- Agent session orchestration and model adapter interfaces
- Provider/model integration contracts
- End-to-end integration coordination
- Deployment and release configuration
- Demo script, architecture explanation, and final technical narrative

Evin is also the final owner of the release branch, but Athul must review release-critical changes.

### Athul — Data, tools, observability, and frontend owner

Athul owns:

- PostgreSQL setup and database models
- Migrations or reproducible initialization
- Tool registry
- Availability, booking, cancellation, and transfer tools
- Transaction safety and overlap prevention
- Call and tool-event persistence
- Admin UI
- Local simulation scenarios and fixtures
- Data masking, synthetic data, and privacy checks
- UI screenshots and demo data preparation

Athul is also the final owner of the admin experience, but Evin must review changes affecting the agent contract or data model.

### Shared responsibilities

Both contributors must:

- Review pull requests within 30 minutes when possible.
- Run the full test suite before merging.
- Never commit secrets, real phone numbers, private recordings, or real patient/customer data.
- Document integration discoveries in `docs/integration-notes.md`.
- Pair on all end-to-end tests and the live demo rehearsal.
- Keep the local simulation path working after every major merge.

## Repository workflow

Use `main` only for reviewed, working code.

```bash
git checkout main
git pull --ff-only

git checkout -b feat/<short-description>
# implement and test
git add .
git commit -m "feat: <description>"
git push -u origin feat/<short-description>
# open a pull request into main
```

Recommended branch names:

- `feat/config-loader`
- `feat/database-tools`
- `feat/evon-resolver`
- `feat/local-simulation`
- `feat/admin-ui`
- `feat/voice-provider`
- `feat/deployment`
- `test/e2e-hardening`
- `docs/demo-and-readme`

Every pull request must include:

1. What changed.
2. How to run it.
3. Tests run.
4. Any known limitation.
5. A screenshot or terminal output for UI/integration work where useful.

## Priority rules

### P0: Must be complete by November 6

- Deterministic local simulation.
- Malayalam appointment scenario.
- `agent.yaml` validation.
- Evon date/time resolution or a clearly isolated fallback resolver for simulation.
- Availability and transactional booking.
- Call, event, calendar, and booking persistence.
- Admin calls/bookings/detail views.
- Tool registry with one-function-style extension.
- One live voice path if technically available.
- Masked phone numbers and synthetic demo data.
- Tests, README, architecture, setup instructions, and recorded backup demo.

### P1: Only after P0 is stable

- Second language configuration.
- A second telephony provider.
- Optional recordings with consent.
- Google Calendar adapter.
- Advanced silence handling.
- Hosted one-command deployment polish.

### Explicitly defer

- Multi-tenant accounts.
- Visual flow builder.
- Enterprise authentication.
- Full VaaniLab evaluation platform.
- Support for every Indian language.
- Real customer data.
- Medical advice or diagnosis.

## Day-by-day plan

## November 1 — Foundation and integration gate

**Objective:** Make the project runnable locally and remove unknowns before building around them.

### Evin

1. Create `docs/integration-notes.md`.
2. Verify the registered Gnani account, API key process, quota, and available model access.
3. Read the official documentation for the exact available Warp, Evon, Prisma, and Timbre interfaces.
4. Implement startup configuration validation with safe error messages.
5. Implement `agent.yaml` loading and schema validation.
6. Create model adapter interfaces so the rest of the code does not depend directly on undocumented API details.
7. Add a minimal FastAPI health endpoint.

### Athul

1. Implement Docker Compose PostgreSQL.
2. Define the initial SQLAlchemy models for `calls`, `call_events`, `calendars`, and `bookings`.
3. Add database initialization/migration support.
4. Implement the tool registry contract.
5. Add initial synthetic clinic/calendar fixtures.
6. Create a basic admin UI shell or API endpoints for calls and bookings.

### Joint checkpoint — November 1, 18:00 IST

Decide the live-path strategy based only on verified documentation:

- **Path A:** Warp and one telephony provider are usable; proceed with live integration.
- **Path B:** Gnani Speech APIs are available but Warp is not documented/accessible; use a modular documented Speech API path for the live demo while keeping the Warp adapter interface and recording the limitation.
- **Path C:** Credentials or telephony are blocked; make local simulation the guaranteed demo and continue the live adapter only if it does not threaten P0.

Do not let an unverified live integration consume the entire project. By the end of Day 1, the local app must start and the database must initialize.

**Exit criteria:**

```bash
make dev
curl http://localhost:8000/health
make simulate SCENARIO=appointment-malayalam
```

The final command may still be a skeleton, but it must execute through the application rather than being a placeholder script.

## November 2 — Core booking flow and deterministic simulation

**Objective:** Complete the full local business workflow without live telephony.

### Evin

1. Implement Evon structured date/time resolution.
2. Define and validate the normalized result schema:
   - date
   - time or time window
   - timezone
   - confidence
   - explanation
3. Add Malayalam test phrases, including relative dates and time expressions.
4. Implement the generic agent/session state machine interface.
5. Add call-summary adapter/schema.

### Athul

1. Implement `check_availability`.
2. Implement transactional `book_slot`.
3. Implement `cancel_booking`.
4. Implement safe `transfer_to_human` stub.
5. Add overlap prevention and duplicate-booking tests.
6. Implement structured call-event logging.
7. Build the `appointment-malayalam` simulation scenario.

### Joint integration

Run this complete flow locally:

```text
Malayalam utterance
→ date/time normalization
→ availability check
→ collect caller name
→ repeat and confirm
→ transactional booking
→ summary
→ persisted call events
```

**Exit criteria:** a clean simulation creates exactly one confirmed booking, records all important events, and produces a readable summary. This is the first non-negotiable demo milestone.

## November 3 — Agent behavior, admin page, and first end-to-end review

**Objective:** Make the system understandable and observable to a judge.

### Evin

1. Connect the generic session state machine to the chosen documented Gnani model path.
2. Pass language, greeting, persona, rules, and declared tools from `agent.yaml`.
3. Enforce that the agent can call only configured tools.
4. Add low-confidence clarification behavior.
5. Add timeout and malformed-model-output handling.
6. Write the first end-to-end integration test around the local session.

### Athul

1. Complete the calls list.
2. Complete the bookings list.
3. Complete call details with chronological tool events.
4. Show resolved date/time, outcome, summary, and errors.
5. Mask phone numbers in every UI view.
6. Add clear empty/loading/error states.
7. Add a seeded fictional clinic dataset.

### Joint checkpoint — November 3 evening

Record a screen capture of the local simulation. If the flow is not understandable without explanation, simplify the UI and output before adding more features.

**Exit criteria:** an evaluator can run the simulation and inspect the call, booking, summary, tool arguments, and tool results without opening the database manually.

## November 4 — Live voice path and deployment

**Objective:** Get one live voice route working without damaging the reliable local path.

### Evin

1. Implement the selected model/session adapter from verified documentation.
2. Implement or complete the provider-neutral voice session interface.
3. Integrate the chosen telephony provider behind `app/providers/`.
4. Verify webhook authentication/verification options.
5. Add codec/sample-rate diagnostics and explicit timeouts.
6. Deploy the backend to the available public environment.

### Athul

1. Add or complete the frontend deployment.
2. Verify that deployed admin data loads correctly.
3. Add a live-call status or latest-call refresh view if time allows.
4. Prepare Malayalam scripted prompts and pronunciation checks.
5. Prepare synthetic caller/clinic fixtures and remove accidental real data.
6. Test phone masking and recording-disabled behavior.

### Joint integration

Run at least three live or simulated calls:

1. Successful Malayalam booking.
2. Unavailable slot with alternative.
3. Ambiguous time or caller hangup.

If live integration fails for reasons outside your control, stop debugging by a fixed cutoff and preserve local simulation as the official demo path. A technically honest, deterministic fallback is better than a fragile fake live demo.

**Exit criteria:** either three consecutive live rehearsals pass, or the local simulation is fully polished and the live limitation is documented honestly.

## November 5 — Hardening, security, testing, and documentation

**Objective:** Turn the prototype into a credible open-source submission.

### Evin

1. Complete the README quickstart.
2. Add the architecture diagram and model/provider explanation.
3. Document supported Malayalam flow and limitations.
4. Complete model error, timeout, and fallback behavior.
5. Add deployment instructions.
6. Review every external integration for undocumented assumptions.
7. Prepare the final technical explanation and contribution split.

### Athul

1. Complete unit and integration tests.
2. Test concurrent booking attempts.
3. Test invalid/low-confidence date/time.
4. Test tool timeout and unknown-tool rejection.
5. Test caller hangup and no-slot outcomes.
6. Run a privacy/security review:
   - no secrets in Git
   - `.env` ignored
   - phone numbers masked
   - recordings off by default
   - no real patient/customer data
   - admin page labeled non-production
7. Add a clean-machine setup test.

### Joint review

Use this checklist:

- Can a new developer reach local simulation in ten minutes?
- Does Malayalam appointment booking work repeatedly?
- Is every model claim supported by actual usage?
- Is every important failure visible in the admin page?
- Can one new tool be added without editing the core call loop?
- Does the project avoid pretending to be production-secure?
- Does the README explain exactly what works and what does not?

**Exit criteria:** feature freeze candidate with no known P0 blocker.

## November 6 — Freeze, demo, and submission package

**Objective:** Stop adding features and produce the evidence needed for submission.

### Morning: final build

- Merge only release-critical pull requests.
- Run the complete test suite.
- Run database initialization from a clean environment.
- Run the Malayalam simulation from the README.
- Run the live call three times if available.
- Verify the deployed URL and admin page.

### Afternoon: demo assets

Prepare:

1. A 60-second public demo.
2. A longer backup demo showing setup and architecture.
3. Screenshots of the admin page.
4. A repository README with setup instructions.
5. An architecture diagram.
6. A short written project explanation.
7. The exact Gnani models/APIs used.
8. A contribution statement:
   - Evin: platform, model integration, session orchestration, deployment.
   - Athul: database, tools, admin UI, simulation, testing/privacy.

### Evening: freeze

- Tag the final commit: `v0.1.0-hackathon`.
- Create a GitHub release if the repository is stable.
- Record the final demo from the exact commit/tag.
- Do not introduce new features after the freeze.
- Use November 7–10 only for exam-friendly final edits, social posting, and submission.

## Data acquisition and privacy plan

The PRD and competition terms require fictional/synthetic demo data. Do not collect real patient records, customer phone numbers, Aadhaar/PAN/account numbers, or private recorded calls for the repository or public demo.

For Malayalam testing, use three safe layers:

1. **Synthetic text fixtures:** Write Malayalam appointment utterances yourselves using fictional names, fake numbers, and a fictional clinic.
2. **Staged team recordings:** If voice audio is necessary for local testing, record only Evin and Athul reading scripted phrases, with both contributors consenting. Keep the files outside Git or in ignored local directories. Do not publish or submit the raw recordings unless the rules explicitly permit it.
3. **Synthetic noise:** Mix the staged speech with generated or freely licensed background-noise samples such as traffic, fan, market, and household noise. Record the source and license for any external audio.

The public demo should preferably use synthetic or staged data, not real users. “Realistic conditions” means realistic language, interruptions, accents, noise, and timing—not real personal data.

## Critical-path dependencies

These must be resolved early:

1. Gnani API account and credits.
2. Exact available models and API interfaces.
3. Warp access/protocol, if available.
4. One telephony provider and media-stream protocol.
5. Public deployment endpoint.
6. Malayalam behavior and audio path.
7. PostgreSQL deployment/persistence.

If any dependency remains unknown after the November 1 checkpoint, isolate it behind an adapter and continue with the deterministic simulation. Never block database, tools, UI, tests, or documentation on telephony.

## Definition of done for November 6

VaaniKit is ready to freeze when:

- `make dev` starts the local environment.
- `make simulate SCENARIO=appointment-malayalam` completes successfully.
- A Malayalam appointment request is normalized safely.
- Availability and booking are transactional.
- Overlapping bookings are prevented.
- Calls, events, bookings, and summaries persist.
- The admin page explains what happened.
- Phone numbers are masked.
- The tool registry rejects undeclared tools.
- Tests cover configuration, date/time, booking, masking, events, and simulation.
- The live path works three times, or the local fallback is polished and clearly documented.
- README setup works from a clean environment.
- No secrets or private data are in Git.
- The final demo uses fictional/staged data and contains no misleading claims.

## References

[1]: https://github.com/evinbrijesh/vaanikit "VaaniKit GitHub repository"
[2]: https://docs.gnani.ai/ "Gnani AI developer documentation"
[3]: https://www.gnani.ai/great-indian-ai-internship-registration-form "Great Indian AI Internship Challenge participation terms"
