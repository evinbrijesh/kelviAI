# VaaniKit Public Demo & Deployment Specification

This document outlines the architecture, requirements, and design for the judge-facing public deployment of VaaniKit.

---

## 1. Overview & Objectives

The goal is to provide a public, zero-friction HTTPS web application where hackathon judges and evaluators can immediately test the Indian-language voice agent without needing:
- Local installations (Docker, Python, Git)
- Telecom credentials or physical telephony (PSTN/Twilio)
- An API key or account creation

The primary deployed interface is the **browser voice demo (`/demo`)** with an integrated text simulation fallback, connected to live Gnani Prisma STT and Timbre TTS models and a persistent PostgreSQL database.

---

## 2. System Architecture

```text
Judge's Browser (Desktop / Mobile)
   │
   ├── HTTPS GET /
   │     └─► Landing & Demo Interface (/demo)
   │
   ├── AudioWorklet / Microphone (16 kHz Linear PCM WAV)
   │     └─► POST /api/voice/session/{call_sid}/turn
   │
   └── Text Simulation Fallback (JSON utterance)
         └─► POST /api/voice/session/{call_sid}/text-turn
                 │
                 ▼
          FastAPI Backend
                 │
                 ├── Speech Layer: Gnani Prisma v3.0 STT & Timbre v2.5 TTS
                 ├── Core Engine: AgentSession State Machine & DateTimeResolver
                 ├── Persistence: PostgreSQL (Calls, CallEvents, Bookings)
                 └── Observability: Protected Admin Dashboard (/admin/ui)
```

---

## 3. Key Requirements for Public Demo Readiness

### A. Landing Page & Demo Consolidation
- The root route `/` should serve or redirect directly to the judge-ready interactive demo.
- Clean presentation with clear call-to-actions:
  - **Start Demo Call** (Voice mode via microphone)
  - **Text Mode Fallback** (Direct input for environments where microphone access is restricted or noisy)

### B. Text Turn Fallback
- Microphone permissions or audio hardware can occasionally fail on mobile or restrictive corporate browsers.
- Provide a text input on the demo page connected to `/api/voice/session/{call_sid}/text-turn` that drives the exact same `AgentSession` state machine, date/time resolver, availability tools, and database booking pipeline.
- Generates speech audio via Timbre so the user can still listen to the synthesized Malayalam response even when typing their prompt.

### C. Live Status, Alternatives & State Indicators
- Visual step cards showing the agent's progress:
  - *Listening / Transcribing...*
  - *Checking availability...*
  - *Slot conflict detected -> Nearest alternative suggested*
  - *Awaiting confirmation...*
  - *Booking confirmed!*
- Dedicated banner or card when a requested slot is unavailable, clearly displaying the requested time vs. the proposed alternative.

### D. Per-Session Isolation & Safety Guardrails
- Automatic rate-limiting and session timeouts:
  - Maximum 25 seconds per turn (enforced by client AudioWorklet and server payload limits).
  - Maximum 10 minutes session duration.
  - 10 MB maximum audio payload (`MAX_AUDIO_BYTES`).
- Phone numbers masked automatically in all database and visual responses.
- Ephemeral in-memory audio: zero audio recordings stored to disk.
- Explicit non-production disclaimers and synthetic data labeling.

### E. Deployment Checklist
1. Deploy container image to cloud host (e.g. Render, Railway, Fly.io, or VPS) with HTTPS enabled.
2. Configure managed PostgreSQL instance and inject `DATABASE_URL`.
3. Inject `GNAI_API_KEY_ID` as a protected server-side secret.
4. Set `ADMIN_API_KEY` to secure the `/admin/*` routes while leaving `/demo` and `/api/voice/*` public.
5. Verify `/health` returns HTTP 200 `{"status": "ok"}`.
6. Verify microphone capture and audio playback over public HTTPS.
