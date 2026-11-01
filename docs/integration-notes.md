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
