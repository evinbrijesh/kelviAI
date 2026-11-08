# Gnani Integration Notes

**Last updated:** November 8, 2026
**Investigated by:** Evin

## Available APIs (Documented)

### Speech-to-Text - Gnani Prisma
- **Prisma v2.5** (default) - Transcription in specified language
- **Prisma v3.0** - Multilingual with automatic language detection
- **Modes**: REST (up to 30s), Realtime (WebSocket), Batch (long files)
- **Base URL**: `https://api.vachana.ai`
- **Endpoint**: `/stt/v3`
- **Auth**: `X-API-Key-ID` header
- **Documentation**: https://docs.gnani.ai/api/STT/overview.md

### Text-to-Speech - Gnani Timbre
- **Timbre v2.5** (recommended, v2.0 deprecated)
- **Modes**: REST, Streaming (SSE), Realtime (WebSocket)
- **Base URL**: `https://api.vachana.ai`
- **Endpoint**: `/api/v1/tts/inference`
- **Voice catalog** available for selection
- **Documentation**: https://docs.gnani.ai/api/TTS/tts-inference.md

### Voice Cloning
- Embeddings, REST, Streaming, Realtime modes available
- Clone from short reference audio sample

### Integrations
- **LiveKit plugin**: https://docs.gnani.ai/livekit/introduction.md
- **Pipecat plugin**: https://docs.gnani.ai/pipecat/introduction.md

## Not Available/Undocumented

### Warp
- **Status**: NOT found in official documentation
- **Impact**: Cannot use Warp as the primary real-time layer
- **Decision**: Use documented Speech APIs + LiveKit/Pipecat for real-time integration
- **Future**: Keep adapter interface for Warp if it becomes available

### Evon
- **Status**: NOT found in official documentation
- **Impact**: No Gnani date/time resolution API available
- **Decision**: Implement custom date/time resolver or use alternative (OpenAI/Anthropic with Indian language support)
- **Future**: Keep adapter interface for Evon if it becomes available

## Live Path Strategy (Path B)

Since Warp is undocumented, we will:
1. Use **Prisma (STT) + Timbre (TTS)** for voice processing
2. Use **LiveKit or Pipecat** for real-time audio streaming
3. Keep **adapter interfaces** for Warp/Evon for future compatibility
4. Focus on **local simulation** as the guaranteed demo path
5. Live demo will use the documented Speech API path

## Language Support

- 10 documented languages: Bengali (`bn-IN`), English (`en-IN`), Gujarati (`gu-IN`),
  Hindi (`hi-IN`), Kannada (`kn-IN`), Malayalam (`ml-IN`), Marathi (`mr-IN`),
  Punjabi (`pa-IN`), Tamil (`ta-IN`), and Telugu (`te-IN`)
- Native-script output supported
- Automatic language detection on Prisma v3.0 with `language_code: indic-auto`
- The multilingual implementation is documented under "Multilingual behavior" below

## Next Steps

1. Test API key and quota via Quick Start
2. Verify Malayalam support level
3. Decide between LiveKit vs Pipecat for real-time integration
4. Implement adapter interfaces for:
   - STT (Prisma primary, Warp stub)
   - TTS (Timbre primary, Warp stub)
   - Date/time resolution (custom primary, Evon stub)

## Local verification — November 1

### Verified locally

- `agent.yaml` loads as UTF-8 on Windows (the Malayalam greeting previously crashed cp1252).
- Malformed `agent.yaml` sections raise a short configuration error, not a `KeyError`.
- Malayalam date/time resolution for നാളെ, ഇന്ന്, മറ്റന്നാൾ with time expressions
  (10 മണി, 10:30, ഒന്നര, രാത്രി, ഉച്ചയ്ക്ക്), pinned to `Asia/Kolkata`.
- PostgreSQL 16 schema created from SQLAlchemy models: `calls`, `call_events`,
  `calendars`, `bookings`.
- Synthetic seed data is idempotent across restarts (5 calls, 3 bookings, 1 calendar).
- A partial unique index prevents two confirmed bookings for the same calendar slot
  while allowing a cancelled slot to be rebooked.
- Admin JSON endpoints return masked phone numbers only.
- `/health` returns 503 in about 3 seconds when PostgreSQL is stopped, and recovers
  automatically when it returns.
- `docker compose up` starts PostgreSQL and the API as one healthy unit.

### Verified live against the Gnani API (November 3, 2026)

A Gnani API key was configured and both speech endpoints were exercised with
synthetic TTS audio. Confirmed behavior:

- `X-API-Key-ID` alone authenticates requests; the API returns `401` without it.
- `POST /stt/v3` expects multipart fields `audio_file`, `model`, and
  `language_code` (`ml-IN` accepted; `indic-auto` also documented). The response
  contains `transcript`, `detected_language_code`, and `success`; it does not return
  `confidence` or `duration_ms`, so the adapter leaves those at zero.
- `POST /api/v1/tts/inference` requires `text`, `model`, `voice`, `speed`, `language`,
  and `audio_config` (`sample_rate` 48000, `num_channels` 1, `sample_width` 2,
  `encoding` `linear_pcm`, `container` `wav`). It returns `audio/wav` bytes.
- Timbre v2.5 Malayalam voices are **Reshma** and **Riyaan**. The placeholder voice
  `default` is rejected with `400`; `agent.yaml` now uses `Reshma`.
- A TTS → STT round trip with `timbre-v2.5` and `prisma-v3.0` detected `ml-IN` and
  transcribed the Malayalam greeting correctly.

No audio was written to disk or committed; only in-memory synthetic speech was used.
The local simulation remains the guaranteed demo path (Path B).

## Multilingual behavior — November 5, 2026

The speech-adapter implementation supports every documented language without
adding undocumented parameters. Live verification is limited to the languages
explicitly listed below.

### Speech-to-text

- `agent.yaml` sends `language_code: indic-auto` on every `/stt/v3` request.
- Prisma returns `transcript` in the spoken script and `detected_language_code`
  (verified value: `ml-IN` for Malayalam audio).
- The adapter normalizes the detected code (`app/llm/language.py`) and forwards it
  to the agent session; an unrecognized code falls back to the session language.

### Reply language

- Voice turns: the detected STT language wins, so the reply text and TTS audio both
  use the caller's language.
- Text and simulation turns: the Unicode script of the utterance is detected
  (Devanagari defaults to Hindi, refined to Marathi using distinctive keywords).
  The first detection locks that language for the call so a Latin-script name turn
  cannot flip an Indic call to English.
- The greeting is emitted before any caller audio, so it uses `agent.language`
  (default `ml-IN`). Every later reply uses `app/agent/replies.py` templates for the
  caller's language; unsupported languages fall back to Malayalam.

### Text-to-speech

- Timbre requires a documented voice per language; the adapter resolves
  `tts.voices[language]`, then the built-in default, then `tts.voice`.
- Defaults: bn Kirra, en Kaveri, gu Falak, hi Nalini, kn Saanvi, ml Reshma,
  mr Zahira, pa Mehuli, ta Asmita, te Suhana.
- Language and voice are sent together so the synthesized audio matches the reply
  text; the audio config (48 kHz mono linear PCM WAV) is unchanged.

### Date/time resolver

- The deterministic resolver (`app/llm/custom_resolver.py`) gained lexicons for
  relative days, day periods, number words 1–12, clock markers, and half-hour
  prefixes in all ten languages, plus native-digit normalization and
  `DD/MM/YYYY` support.
- The caller's language is searched first, then the remaining languages, so
  mixed-language input still resolves. ISO output, confidence values, and
  `Asia/Kolkata` grounding are unchanged.

### Stage 2 browser demo and code-mixed parsing (November 8, 2026)

- `/demo` is separate from the Stage 1 admin dashboard. AudioWorklet captures
  mono PCM in memory, resamples to 16 kHz, and sends 16-bit WAV to the existing
  voice API. Turns auto-send after 25 seconds; ending a call discards unsent audio.
- The resolver recognizes focused romanized Hinglish, Manglish, Tanglish and
  Benglish booking phrases. Native scripts and provider language hints still
  take priority. Name capture strips trailing copulas; negated confirmations
  do not invoke `book_slot`. This is phrase-based support, not general NLP.
- Browser control tests used synthetic microphone streams and mocked speech
  responses for booking, permission denial, unsent-audio discard, failed requests,
  blocked autoplay, keyboard activation and the automatic turn limit. These
  tests are not evidence of live provider accuracy or a physical microphone test.

### Verification

The November 5 implementation made no additional live calls. On November 8,
synthetic Hindi speech was fed through a browser MediaStream and the real
AudioWorklet, Prisma v3.0 and Timbre v2.5 path. Three turns reached
`awaiting_name`, `awaiting_confirmation`, then `completed`. The saved fictional
name was exactly `आशा डेमो`, with a confirmed appointment and a masked empty phone.
Microphone tracks were stopped after each turn; playback completed without
browser console errors. Temporary synthetic WAV fixtures were removed.

This is a live-provider test with synthetic speech, not a physical-microphone,
noise robustness, or four-language code-mixed accuracy benchmark. Live evidence
currently covers Malayalam and Hindi only. Other language behavior is covered
by deterministic tests (`tests/test_language.py`, `tests/test_resolver.py`,
`tests/test_multilingual_agent.py`, `tests/test_voice_session.py`,
`tests/test_gnani_adapters.py`). All 318 tests passed, along with Ruff, Mypy
(40 source files), JavaScript syntax checks, the three-call rehearsal and the
Malayalam simulation.

### Stage 2 interface delivery gate

Scope: the new `/demo` page. The existing dashboard's approved AMOLED black,
mint accent, Redaction 50 display, Inter Tight body and mono labels are retained.
The declared direction remains ENERGY 2 / RHYTHM 2 / MOTION 1. Controls and
conversation are separate because recording needs a stable action area while
transcripts grow. Spacing uses 24px within the workspace and 48px between desktop
columns to separate actions from evidence. One bounded control surface contains
the call lifecycle; transcripts remain an open chronological list. No decorative
assets or new motion were introduced.

Hard gate:
- R-02 PASS: new page copy contains no em dashes.
- R-03 PASS: completed conversation checked at 320, 390, 650, 820, 950, 1280 and 1440px without horizontal overflow; buttons are 48px and navigation 44px high.
- R-17 PASS: only actual model names, call states, recording timer and returned booking reference are displayed.
- R-18 PASS: no testimonials or social-proof section exists.
- R-23 PASS: established brand direction and requested separate demo navigation retained; no new logo, avatar or illustration generated.
- R-24 PASS: Call dashboard navigates to the existing `/admin/ui` page.
- R-25 PASS: measured contrast is 8.60:1 for muted text on the control surface, 16.93:1 for body text, and 14.50:1 for primary-button text.
- R-26 PASS: Start opens a session; Record captures; Send posts a WAV; End discards unsent audio and hangs up; native audio plays and pauses; dashboard link navigates.
- R-27 PASS: empty conversation, starting/processing states and visible permission/provider/request errors were exercised.
- R-28 PASS: no FAQ exists.
- R-32 PASS: Tab reaches navigation and Start with a visible 2px outline; keyboard Enter activated Start in the controlled test.
- R-33 PASS: interface implemented directly in HTML and JavaScript, without source-patching scripts.
- R-34 PASS: only the requested fixed dark theme is shipped; no incomplete toggle exists.
- R-35 PASS: local server and browser exercised; three-turn real-provider booking completed; desktop/mobile screenshots inspected; no console errors.
- R-36 PASS: no unmeasured performance, security or compliance claims appear.
- R-37 PASS: page retains the owner's established black/mint and typographic direction.
- R-38 PASS: fictional identities and bookings are explicitly labeled synthetic/non-production, not presented as customers.
- R-39 PASS: native named buttons, links and audio; pointer/disabled and hover/active states; document language, title and landmarks; zoom allowed; reduced-motion emulation shows zero animations.
- R-40 PASS: no image/video/iframe or render-blocking third-party script; guidance reserves space; no unmeasured Web Vitals claims.

Purpose gate:
- R-01 PASS: black and mint retain the approved identity; mint highlights the primary action, not background decoration.
- R-04 PASS: no generic icon set is used.
- R-06 PASS: display face retains identity, sans supports transcript readability, mono distinguishes operational labels.
- R-07 PASS: no decorative grid or background pattern is added.
- R-08 PASS: no decorative button arrows are added.
- R-09 PASS: model/state facts are ordinary labels, not promotional capsule badges.
- R-10 PASS: no glassmorphism is used.
- R-12 PASS: no floating shadows are used.
- R-13 PASS: no decorative glow is used.
- R-14 PASS: one call-control surface and an open transcript reflect different content roles, not repeated feature cards.
- R-19 PASS: only interaction feedback is used; reduced motion removes the active-button translation.
- R-22 PASS: no generic illustrations are used.

Liveliness:
- Dials PASS: ENERGY 2 / RHYTHM 2 / MOTION 1 retained from the declared dashboard direction.
- Consistency PASS: assertive display type, separated action/transcript composition and restrained interaction feedback match those dials.
- Focal point PASS: the headline introduces the task; the mint Start action leads the operational workspace.
- Whitespace PASS: 24px internal and 48px desktop-column gaps distinguish grouping from separation.
- Accent PASS: one mint accent identifies the primary action and agent/booking evidence.
- Identity PASS: Redaction display type and the black/mint palette connect both demo stages.
- Design read PASS: the established operations-demo direction was retained, not replaced with a new template aesthetic.

Craftsmanship and quality locks:
- C-1 PASS: color, layout, typography, spacing and surface choices have reasons recorded above.
- C-2 PASS: every interactive element has exercised behavior as listed under R-26.
- C-3 PASS: sections serve recording, conversation, model/state facts or demo privacy guidance.
- C-4 PASS: permission denial, too-short capture, provider failure, uncertain turn, blocked autoplay and unsent-audio discard preserve usable controls.
- C-5 PASS: synthetic data and measured verification are distinguished from real-user accuracy claims.
- R-05 PASS: a recording workspace and chronological transcript replace a landing-page feature template.
- R-11 PASS: 20px control surface, 12px playback surface and 8px buttons have distinct roles, not uniform pills.
- R-15 PASS: Start demo call, Record your turn, Send this turn and End call name their actions.
- R-16 PASS: no generic AI marketing buzzwords appear.
- R-20 PASS: regional-language transcript and established typography/palette give the operational page its identity.
- R-21 PASS: fixed dark mode follows the owner's AMOLED preference, not an assumed technical aesthetic.
- R-29 PASS: neutral surfaces and one mint accent form the active palette.
- R-30 PASS: the page extends the existing VaaniKit identity, not a cloned product layout.
- R-31 PASS: major visual decisions have one-line reasons recorded above.

## Provider limits and rate handling — November 8, 2026

Figures below are the documented limits. Request-rate and concurrency numbers appear
only in the Gnani console at app.gnani.ai; no usage or credits API is documented.

### Prisma STT

- REST transcription (`/stt/v3`) accepts up to 30 seconds of audio per request.
- Streaming sessions run up to 15 minutes with a 60-second idle timeout. The idle
  window is configurable with `x-idle-timeout-sec` from 5 to 900 seconds.
- Batch jobs accept up to 4 hours per file, 100 files per job, and 10 MB per file.
- Overload answers `429` with a `RATE_LIMITED` error. No `Retry-After` header is
  documented.

### Timbre TTS

- One active request per API key. Concurrent requests are not queued by the provider.
- A rejected request answers `429`; no retry hint is documented.

### Handling in the adapters

- `app/llm/gnani_adapters.py` wraps both endpoints in `_post_with_retry`: up to three
  attempts, sleeping 0.5 s then 1 s, capped at 4 s. A `Retry-After` header in whole
  seconds is honored when present and capped at the same 4 s.
- The TTS adapter holds an `asyncio.Lock`, so overlapping voice turns queue for the
  single active Timbre slot instead of racing into `429`.
- Once the attempts are exhausted the original `429` response reaches
  `raise_for_status()` and surfaces as an error, so the caller never receives
  unhandled retries.
- The lock is per process. Running several API workers against one key still needs a
  shared queue or a single TTS worker.
- Tests: `tests/test_gnani_adapters.py` covers STT retry, the bounded TTS failure, and
  serialized concurrent TTS calls.

