# Kelvi AI: voice agents that listen in Indian languages

Kelvi AI (കേൾവി, "hearing" in Malayalam) is an open-source Python framework for building voice agents in Indian languages, with a clinic booking assistant built on it as the reference app. It runs on Gnani's speech stack: Prisma v3.0 for speech recognition, Evon v3.3 for reasoning and Timbre v2.5 for the voice.

## The problem

People book a doctor or chase a delivery in the language they think in, and they switch languages mid-sentence: "kal subah 11 baje", "naale raavile 10 mani". A voice bot that expects clean English, or one language at a time, mishears these callers or sends them to a human queue.

## What we built

- **Clinic assistant.** Checks free slots and books appointments. Callers speak Hindi, Malayalam or a mix, and it replies in their language.
- **Delivery support agent.** Tracks an order in Malayalam and cancels it only after the caller confirms out loud.
- **Operations dashboard.** Lists every call with its resolved date and time, the tools it ran and the booking it created.
- **Engine X-Ray.** Shows, for each turn, the detected language, the resolved slot, the tool called and how long each step took.

## How it works

Each turn runs caller audio → Prisma STT → Kelvi engine → tool → Timbre TTS. Dates, times and yes/no answers go through deterministic rules. Unclear phrasing goes to Evon, and if Evon does not answer within 2 seconds the engine uses the rules' result instead.

A tool is a Python function with a decorator. Tools that change data, such as booking or cancelling, set `requires_confirmation=True`, so the agent asks the caller first, in their language. Negative answers are checked before positive ones, so "nahi, book mat karo" never counts as a yes. `kelvi init my-agent --template delivery` scaffolds a new agent.

## What we can show

- Both calls in our demo video are live round trips through Gnani's APIs.
- 368 automated tests pass (`pytest`), including code-mixed date phrases in Hindi, Malayalam, Tamil and Bengali.
- Phone numbers are masked, call recording is off and all demo data is synthetic.

## Limits and next steps

This is a non-production prototype. The demo runs in a browser rather than on a phone line, and the caller voices in our video are synthetic. Next we want to test with real microphones and phone lines, more real speakers, and more languages.

## Team

- **Athul Sunil Kumar:** data layer and booking tools, observability and the dashboard, privacy safeguards, demo media.
- **Evin Brijesh:** platform, Gnani speech and reasoning integration, the Kelvi framework, web pages.

**Code:** https://github.com/evinbrijesh/kelviAI (Apache 2.0) · **Demo video:** [add YouTube link after upload] · **Run it:** see the Quickstart in the README.
