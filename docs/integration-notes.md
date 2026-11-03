# Gnani Integration Notes

**Last updated:** November 1, 2026
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

- 10 Indian languages plus English
- Native-script output supported
- Automatic language detection on Prisma v3.0
- Malayalam is supported (verify exact support level in quick start)

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
- Synthetic seed data is idempotent across restarts (2 calls, 2 bookings, 1 calendar).
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

