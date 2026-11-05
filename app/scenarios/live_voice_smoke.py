import asyncio
import logging
import sys
import time

from app.config import load_config
from app.llm.gnani_adapters import GnaniSTTAdapter, GnaniTTSAdapter

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("live_voice_smoke")


async def run_live_smoke() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    config = load_config()

    if not config.gnani.api_key_id or config.gnani.api_key_id.startswith("your"):
        logger.error("GNAI_API_KEY_ID is not configured in .env. Aborting live smoke test.")
        return 1

    print("==================================================")
    print("   VaaniKit Live Speech End-to-End Verification   ")
    print("==================================================")
    print(f"Provider:    {config.model.provider}")
    print(f"Base URL:    {config.gnani.base_url}")
    print(f"TTS Model:   {config.model.tts.model} (Voice: {config.model.tts.voice})")
    print(f"STT Model:   {config.model.stt.model} (Language: {config.model.stt.language})")
    print("--------------------------------------------------")

    tts = GnaniTTSAdapter(config.gnani, config.model.tts)
    stt = GnaniSTTAdapter(config.gnani, config.model.stt)

    test_phrase = "നമസ്കാരം, വാണികിറ്റ് ലൈവ് വോയ്സ് പരിശോധന."
    # The phrase is Malayalam, so TTS needs a concrete language; STT keeps
    # indic-auto below to verify automatic detection.
    tts_language = "ml-IN"
    print(f"1. Synthesizing Malayalam TTS ({tts_language}): '{test_phrase}'...")

    try:
        t0 = time.perf_counter()
        tts_res = await tts.synthesize(test_phrase, language=tts_language)
        tts_time = round((time.perf_counter() - t0) * 1000, 2)
        print(f"   [OK] TTS synthesized in {tts_time} ms")
        print(f"   Audio size:  {len(tts_res.audio)} bytes")
        print(f"   Format:      {tts_res.format.upper()} @ {tts_res.sample_rate} Hz")
    except Exception as exc:
        print(f"   [FAILED] TTS synthesis failed: {exc}")
        await tts.close()
        await stt.close()
        return 1

    print("\n2. Transcribing audio through Gnani STT...")
    try:
        t1 = time.perf_counter()
        stt_res = await stt.transcribe(tts_res.audio, language=config.model.stt.language)
        stt_time = round((time.perf_counter() - t1) * 1000, 2)
        print(f"   [OK] STT transcribed in {stt_time} ms")
        print(f"   Transcript:  '{stt_res.text}'")
        print(f"   Language:    {stt_res.language}")
    except Exception as exc:
        print(f"   [FAILED] STT transcription failed: {exc}")
        await tts.close()
        await stt.close()
        return 1

    await tts.close()
    await stt.close()

    print("--------------------------------------------------")
    print("✓ Live speech round-trip verified successfully!")
    print("==================================================")
    return 0


def main() -> None:
    code = asyncio.run(run_live_smoke())
    sys.exit(code)


if __name__ == "__main__":
    main()
