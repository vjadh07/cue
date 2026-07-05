"""Tests for the music bed — list_music (the beds on offer) and underlay (the
sidechain-style ducking that puts music under a read: intro alone, ducked while
the voice speaks, swelling back for the outro). Measured, not assumed: the
tests generate tones and check loudness region by region."""

import io
import math
import wave

from pydub import AudioSegment

from music import DUCK_DB, INTRO_MS, OUTRO_MS, list_music, underlay

FRAMERATE = 8000


def make_tone_wav(path, seconds, amplitude=12000, freq=220):
    """A constant tone WAV — loud enough to measure."""
    frames = bytearray()
    for i in range(int(seconds * FRAMERATE)):
        sample = int(amplitude * math.sin(2 * math.pi * freq * i / FRAMERATE))
        frames += sample.to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FRAMERATE)
        w.writeframes(bytes(frames))
    return path


def silent_voice(ms):
    """A 'voice track' of silence — so the result's loudness IS the music's,
    which makes the duck directly measurable."""
    return AudioSegment.silent(duration=ms, frame_rate=FRAMERATE)


def to_bytes(segment):
    out = io.BytesIO()
    segment.export(out, format="wav")
    return out.getvalue()


def test_underlay_extends_duration_by_intro_and_outro(tmp_path):
    music = make_tone_wav(tmp_path / "bed.wav", 20)
    voice_ms = 3000

    result = AudioSegment.from_file(io.BytesIO(underlay(to_bytes(silent_voice(voice_ms)), music)))

    expected = INTRO_MS + voice_ms + OUTRO_MS
    assert abs(len(result) - expected) < 150


def test_music_ducks_under_the_voice(tmp_path):
    music = make_tone_wav(tmp_path / "bed.wav", 20)

    result = AudioSegment.from_file(io.BytesIO(underlay(to_bytes(silent_voice(4000)), music)))

    # Sample well away from the fade edges.
    intro = result[200 : INTRO_MS - 500]
    ducked = result[INTRO_MS + 1200 : INTRO_MS + 2800]
    drop = intro.dBFS - ducked.dBFS
    assert DUCK_DB - 4 < drop < DUCK_DB + 4


def test_music_swells_back_for_the_outro(tmp_path):
    music = make_tone_wav(tmp_path / "bed.wav", 30)
    voice_ms = 3000

    result = AudioSegment.from_file(io.BytesIO(underlay(to_bytes(silent_voice(voice_ms)), music)))

    ducked = result[INTRO_MS + 1000 : INTRO_MS + 2500]
    outro = result[INTRO_MS + voice_ms + 800 : INTRO_MS + voice_ms + OUTRO_MS - 700]
    assert outro.dBFS - ducked.dBFS > DUCK_DB - 4  # swelled roughly back up


def test_short_music_loops_to_cover_a_long_read(tmp_path):
    music = make_tone_wav(tmp_path / "bed.wav", 1)  # 1s bed, 6s of voice
    result = AudioSegment.from_file(io.BytesIO(underlay(to_bytes(silent_voice(6000)), music)))
    assert len(result) > 6000  # covered the whole read without erroring


def test_list_music_lists_only_audio_files(tmp_path):
    (tmp_path / "night-drone.mp3").write_bytes(b"x")
    (tmp_path / "warm pad.wav").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")

    tracks = list_music(tmp_path)

    assert {t["id"] for t in tracks} == {"night-drone.mp3", "warm pad.wav"}
    names = {t["name"] for t in tracks}
    assert "night drone" in names and "warm pad" in names


def test_list_music_missing_folder_is_empty():
    from pathlib import Path

    assert list_music(Path("/nonexistent/music")) == []
