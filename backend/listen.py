"""Listen — the booth's ears. Measures a rendered clip the way a director
hears it: how loud, how high, how bright, how long.

Pure numpy over raw samples (pydub decodes the file; numpy was already here
for the music beds). No ML, no external analysis service — a take is judged
by signal, deterministically:

- loudness_db   RMS level in dBFS (0 = full scale; speech sits around -20)
- pitch_hz      median fundamental over voiced frames, by autocorrelation
- brightness_hz spectral centroid — where the energy sits in the spectrum
                (a shout is brighter than a murmur at the same loudness)
- energy        the 0..1 intensity number the arc chart plots, from loudness
- duration_ms   clip length

This is what lets Cue *check the take*: direction said "build from calm to
furious" — did the energy actually climb?"""

import io

import numpy as np
from pydub import AudioSegment

FRAME_MS = 40
HOP_MS = 20
# Human speech fundamentals live here; the autocorrelation search is bounded
# to this band so harmonics and room noise can't masquerade as the voice.
PITCH_MIN_HZ = 60
PITCH_MAX_HZ = 500
# Frames quieter than this (relative to the clip's loudest frame) are treated
# as pauses: no pitch is read off them.
VOICED_FLOOR_DB = -30
# The energy ramp: -40 dBFS and below reads as 0 (whisper-quiet), -5 as 1.
ENERGY_DB_LOW = -40.0
ENERGY_DB_HIGH = -5.0


def _samples(audio_bytes: bytes) -> tuple[np.ndarray, int]:
    """Decode any audio file into mono float samples in [-1, 1] + sample rate."""
    segment = AudioSegment.from_file(io.BytesIO(audio_bytes)).set_channels(1)
    samples = np.array(segment.get_array_of_samples(), dtype=np.float64)
    full_scale = float(1 << (8 * segment.sample_width - 1))
    return samples / full_scale, segment.frame_rate


def _frames(samples: np.ndarray, rate: int) -> np.ndarray:
    """Slice the clip into overlapping frames (rows). Short clips get one frame."""
    frame = int(rate * FRAME_MS / 1000)
    hop = int(rate * HOP_MS / 1000)
    if len(samples) < frame:
        return samples.reshape(1, -1) if len(samples) else np.zeros((1, 1))
    count = 1 + (len(samples) - frame) // hop
    index = np.arange(frame)[None, :] + hop * np.arange(count)[:, None]
    return samples[index]


def _rms_db(x: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(x))))
    if rms <= 1e-9:
        return -100.0
    return 20.0 * float(np.log10(rms))


def _frame_pitch(frame: np.ndarray, rate: int) -> float | None:
    """Fundamental frequency of one frame by autocorrelation: the lag at which
    the signal best matches a shifted copy of itself is the period."""
    frame = frame - frame.mean()
    if _rms_db(frame) < -60:
        return None
    corr = np.correlate(frame, frame, mode="full")[len(frame) - 1 :]
    if corr[0] <= 0:
        return None
    corr = corr / corr[0]  # normalize so peak strength is comparable
    lag_min = int(rate / PITCH_MAX_HZ)
    lag_max = min(int(rate / PITCH_MIN_HZ), len(corr) - 1)
    if lag_min >= lag_max:
        return None
    window = corr[lag_min:lag_max]
    best = int(np.argmax(window))
    # A real period correlates strongly; noise doesn't. 0.5 is a conservative
    # voiced/unvoiced gate for clean synthesized speech.
    if window[best] < 0.5:
        return None
    return rate / float(lag_min + best)


def _spectral_centroid(samples: np.ndarray, rate: int) -> float:
    """The 'center of mass' of the spectrum — perceptual brightness."""
    spectrum = np.abs(np.fft.rfft(samples))
    if spectrum.sum() <= 1e-9:
        return 0.0
    freqs = np.fft.rfftfreq(len(samples), d=1.0 / rate)
    return float((freqs * spectrum).sum() / spectrum.sum())


def profile(audio_bytes: bytes) -> dict:
    """Measure one clip. Returns loudness_db, pitch_hz (None when nothing is
    voiced), brightness_hz, energy (0..1), duration_ms."""
    samples, rate = _samples(audio_bytes)
    duration_ms = int(len(samples) / rate * 1000)

    loudness_db = _rms_db(samples)

    frames = _frames(samples, rate)
    frame_levels = np.array([_rms_db(f) for f in frames])
    loudest = float(frame_levels.max()) if len(frame_levels) else -100.0

    pitches = []
    for frame, level in zip(frames, frame_levels):
        if level < loudest + VOICED_FLOOR_DB:
            continue  # a pause, not the voice
        f0 = _frame_pitch(frame, rate)
        if f0 is not None:
            pitches.append(f0)
    pitch_hz = float(np.median(pitches)) if pitches else None

    brightness_hz = _spectral_centroid(samples, rate)

    # Loudness mapped onto 0..1 — the single intensity number the arc plots.
    energy = (loudness_db - ENERGY_DB_LOW) / (ENERGY_DB_HIGH - ENERGY_DB_LOW)
    energy = float(np.clip(energy, 0.0, 1.0))

    return {
        "loudness_db": round(loudness_db, 1),
        "pitch_hz": round(pitch_hz, 1) if pitch_hz is not None else None,
        "brightness_hz": round(brightness_hz, 1),
        "energy": round(energy, 3),
        "duration_ms": duration_ms,
    }
