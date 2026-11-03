import io
import wave

import pytest

from app.bridge.audio_utils import (
    AudioValidationError,
    inspect_wav_header,
    validate_audio_bytes,
    wrap_pcm_in_wav,
)


def make_dummy_wav(sample_rate: int = 16000, num_samples: int = 1600) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * num_samples)
    return buffer.getvalue()


def test_inspect_wav_header_valid() -> None:
    data = make_dummy_wav(sample_rate=16000, num_samples=3200)
    info = inspect_wav_header(data)
    assert info.sample_rate == 16000
    assert info.channels == 1
    assert info.sample_width == 2
    assert info.num_frames == 3200
    assert round(info.duration_seconds, 2) == 0.2


def test_inspect_wav_header_too_short() -> None:
    with pytest.raises(AudioValidationError, match="too short"):
        inspect_wav_header(b"RIFFtiny")


def test_inspect_wav_header_invalid_content() -> None:
    with pytest.raises(AudioValidationError, match="Malformed WAV"):
        inspect_wav_header(b"RIFF" + b"\x00" * 40)


def test_wrap_pcm_in_wav() -> None:
    pcm = b"\x01\x00" * 800
    wav_bytes = wrap_pcm_in_wav(pcm, sample_rate=8000, channels=1, sample_width=2)
    assert wav_bytes.startswith(b"RIFF")
    info = inspect_wav_header(wav_bytes)
    assert info.sample_rate == 8000
    assert info.num_frames == 800


def test_wrap_pcm_empty_raises() -> None:
    with pytest.raises(AudioValidationError, match="empty PCM"):
        wrap_pcm_in_wav(b"")


def test_validate_audio_bytes() -> None:
    valid, msg = validate_audio_bytes(b"")
    assert not valid
    assert "empty" in msg

    valid, msg = validate_audio_bytes(b"short", min_bytes=44)
    assert not valid
    assert "below threshold" in msg

    wav = make_dummy_wav(16000, 160)
    valid, msg = validate_audio_bytes(wav)
    assert valid
    assert "Valid WAV" in msg
