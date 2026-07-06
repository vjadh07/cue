"""Tests for stitch — joining per-line clips into one continuous track with
pauses between lines. Input clips are tiny generated WAVs, so the tests spend
no API credits; the output is checked by loading it back and measuring it."""

import io
import wave

from pydub import AudioSegment

from stitch import stitch, stitch_key

FRAMERATE = 8000


def make_wav(path, seconds, amplitude=0):
    """A mono WAV of the given length — a stand-in for a rendered line. A
    non-zero amplitude makes a constant tone whose loudness can be measured."""
    sample = int(amplitude).to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FRAMERATE)
        w.writeframes(sample * int(seconds * FRAMERATE))
    return path


def duration_ms(data: bytes) -> int:
    return len(AudioSegment.from_file(io.BytesIO(data)))


def test_two_clips_are_joined_with_one_pause(tmp_path):
    a = make_wav(tmp_path / "a.wav", 0.5)
    b = make_wav(tmp_path / "b.wav", 0.5)

    track, _ = stitch([a, b], pause_ms=400)

    # 500 + 400 + 500 = 1400ms; mp3 framing adds a little slack.
    assert abs(duration_ms(track) - 1400) < 100


def test_single_clip_gets_no_pause(tmp_path):
    a = make_wav(tmp_path / "a.wav", 0.5)

    track, _ = stitch([a], pause_ms=400)

    assert abs(duration_ms(track) - 500) < 100


def test_result_is_valid_audio_bytes(tmp_path):
    a = make_wav(tmp_path / "a.wav", 0.3)

    track, _ = stitch([a])

    assert isinstance(track, bytes)
    assert len(track) > 0
    duration_ms(track)  # loads back without error = a real audio file


def test_empty_list_is_an_error(tmp_path):
    try:
        stitch([])
        assert False, "expected an error for an empty script"
    except ValueError:
        pass


def test_per_line_volume_is_applied_to_the_track(tmp_path):
    # Two identical tones, but the second line is a quiet one (volume 0.5).
    # In the stitched track its half must be measurably quieter (~-6dB).
    a = make_wav(tmp_path / "a.wav", 0.5, amplitude=16000)
    b = make_wav(tmp_path / "b.wav", 0.5, amplitude=16000)

    data, _ = stitch([a, b], pause_ms=400, volumes=[1.0, 0.5])
    track = AudioSegment.from_file(io.BytesIO(data))

    loud_half = track[0:450]
    quiet_half = track[950:1350]
    drop = loud_half.dBFS - quiet_half.dBFS
    assert 4 < drop < 8  # 0.5 volume = -6dB, with mp3 slack


# --- the timeline: where each line sits in the stitched track ---


def test_stitch_returns_a_segment_per_clip(tmp_path):
    a = make_wav(tmp_path / "a.wav", 0.5)
    b = make_wav(tmp_path / "b.wav", 0.3)
    c = make_wav(tmp_path / "c.wav", 0.7)

    _, segments = stitch([a, b, c], pause_ms=400)

    assert segments == [
        {"start_ms": 0, "end_ms": 500},
        {"start_ms": 900, "end_ms": 1200},
        {"start_ms": 1600, "end_ms": 2300},
    ]


def test_timeline_matches_without_restitching(tmp_path):
    """timeline() computes the same segments from the clips alone — used to
    backfill caption files for tracks that were stitched before captions
    existed."""
    from stitch import timeline

    a = make_wav(tmp_path / "a.wav", 0.5)
    b = make_wav(tmp_path / "b.wav", 0.3)

    _, segments = stitch([a, b], pause_ms=400)
    assert timeline([a, b], pause_ms=400) == segments


# --- stitch_key: the cache id of a stitched track ---


def test_stitch_key_changes_with_volumes():
    assert stitch_key(["aaa", "bbb"], 400, volumes=[1.0, 0.5]) != stitch_key(
        ["aaa", "bbb"], 400, volumes=[1.0, 1.0]
    )


def test_stitch_key_changes_with_music():
    base = stitch_key(["aaa"], 400)
    assert stitch_key(["aaa"], 400, music="night-drone.mp3") != base
    assert stitch_key(["aaa"], 400, music="warm-pad.mp3") != stitch_key(
        ["aaa"], 400, music="night-drone.mp3"
    )


def test_stitch_key_is_deterministic_and_hex():
    key = stitch_key(["aaa", "bbb"], 400)
    assert key == stitch_key(["aaa", "bbb"], 400)
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


def test_stitch_key_changes_with_clips_order_and_pause():
    base = stitch_key(["aaa", "bbb"], 400)
    assert stitch_key(["bbb", "aaa"], 400) != base  # order matters
    assert stitch_key(["aaa", "ccc"], 400) != base  # different clip
    assert stitch_key(["aaa", "bbb"], 200) != base  # different pause
