import io
import wave
from dataclasses import dataclass


@dataclass(frozen=True)
class WavInfo:
    sample_rate: int
    channels: int
    sample_width: int
    num_frames: int
    duration_seconds: float


class AudioValidationError(ValueError):
    """Raised when audio payload is malformed or invalid."""


def inspect_wav_header(audio_bytes: bytes) -> WavInfo:
    """Inspect and extract format properties from WAV audio bytes."""
    if len(audio_bytes) < 44:
        raise AudioValidationError(f"Audio payload too short ({len(audio_bytes)} bytes)")

    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            sample_rate = wf.getframerate()
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            num_frames = wf.getnframes()
            duration = num_frames / float(sample_rate) if sample_rate > 0 else 0.0

            return WavInfo(
                sample_rate=sample_rate,
                channels=channels,
                sample_width=sample_width,
                num_frames=num_frames,
                duration_seconds=duration,
            )
    except (wave.Error, EOFError) as exc:
        raise AudioValidationError(f"Malformed WAV payload: {exc}") from exc


def wrap_pcm_in_wav(
    pcm_bytes: bytes,
    *,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Wrap raw linear PCM bytes in a standard RIFF/WAVE container."""
    if not pcm_bytes:
        raise AudioValidationError("Cannot wrap empty PCM stream in WAV")

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)

    return buffer.getvalue()


MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB payload limit


def validate_audio_bytes(
    audio_bytes: bytes, min_bytes: int = 44, max_bytes: int = MAX_AUDIO_BYTES
) -> tuple[bool, str]:
    """Validate audio bytes without raising, returning boolean and diagnostic reason."""
    if not audio_bytes:
        return False, "Audio payload is empty"
    if len(audio_bytes) < min_bytes:
        return False, (
            f"Payload size ({len(audio_bytes)} bytes) below threshold ({min_bytes} bytes)"
        )
    if len(audio_bytes) > max_bytes:
        return False, (
            f"Payload size ({len(audio_bytes)} bytes) exceeds maximum limit ({max_bytes} bytes)"
        )

    if audio_bytes[:4] == b"RIFF":
        try:
            info = inspect_wav_header(audio_bytes)
            return True, (
                f"Valid WAV ({info.sample_rate}Hz, {info.channels}ch, "
                f"{info.duration_seconds:.2f}s)"
            )
        except AudioValidationError as err:
            return False, str(err)

    return True, f"Raw audio bytes detected ({len(audio_bytes)} bytes)"
