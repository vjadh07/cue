"""Tests for listen — the booth's ears. Pure-numpy DSP over rendered clips:
loudness, pitch (autocorrelation), spectral brightness. Synthesized tones give
exact ground truth: a 220Hz sine IS 220Hz, a -20dB tone IS quieter than a
-6dB one, silence has no pitch. No models, no credits, no network."""

import io
import wave

import numpy as np

from listen import profile

RATE = 22050


def tone_wav(freq: float, seconds: float = 1.0, amplitude: float = 0.5) -> bytes:
    """A mono 16-bit WAV of a pure sine — ground truth for the analyzer."""
    t = np.arange(int(seconds * RATE)) / RATE
    samples = (amplitude * 32767 * np.sin(2 * np.pi * freq * t)).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


def silence_wav(seconds: float = 0.5) -> bytes:
    return tone_wav(440, seconds, amplitude=0.0)


# --- the profile: one clip in, its measurements out ---


def test_pitch_of_a_pure_tone_is_the_tone():
    p = profile(tone_wav(220))
    assert p["pitch_hz"] is not None
    assert abs(p["pitch_hz"] - 220) < 8

    p = profile(tone_wav(440))
    assert abs(p["pitch_hz"] - 440) < 12


def test_silence_has_no_pitch():
    assert profile(silence_wav())["pitch_hz"] is None


def test_louder_tone_measures_louder():
    quiet = profile(tone_wav(220, amplitude=0.05))
    loud = profile(tone_wav(220, amplitude=0.5))
    assert loud["loudness_db"] > quiet["loudness_db"] + 15  # ~20dB apart


def test_loudness_is_negative_dbfs_for_a_half_scale_tone():
    p = profile(tone_wav(220, amplitude=0.5))
    assert -12 < p["loudness_db"] < -3  # a 0.5 sine sits near -9 dBFS RMS


def test_brightness_follows_frequency():
    dark = profile(tone_wav(220))
    bright = profile(tone_wav(1760))
    assert bright["brightness_hz"] > dark["brightness_hz"] * 3


def test_duration_is_reported():
    p = profile(tone_wav(220, seconds=1.5))
    assert abs(p["duration_ms"] - 1500) < 60


def test_energy_is_a_zero_to_one_intensity():
    """The single number the arc chart plots: quiet ~ 0-ish, loud ~ 1-ish."""
    quiet = profile(tone_wav(220, amplitude=0.02))
    loud = profile(tone_wav(220, amplitude=0.9))
    assert 0.0 <= quiet["energy"] < loud["energy"] <= 1.0
    assert loud["energy"] > 0.7
    assert quiet["energy"] < 0.45
