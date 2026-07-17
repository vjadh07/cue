"""Tests for the local clone registry — where a user's voice lives when Cue
clones it: on THEIR disk, as a wav + an index entry, never anywhere else."""

import io

from pydub import AudioSegment

import clones
from test_listen import tone_wav


def _measure(path):
    return AudioSegment.from_file(path)


def test_add_clone_stores_wav_and_registers_it(tmp_path):
    entry = clones.add_clone("My voice", tone_wav(220), clones_dir=tmp_path)

    assert entry["name"] == "My voice"
    assert len(entry["id"]) == 16
    stored = clones.clone_path(entry["id"], clones_dir=tmp_path)
    assert stored is not None and stored.exists()
    assert stored.suffix == ".wav"


def test_list_clones_returns_registered_voices_in_order(tmp_path):
    a = clones.add_clone("Me", tone_wav(220), clones_dir=tmp_path)
    b = clones.add_clone("Me, tired", tone_wav(330), clones_dir=tmp_path)

    listed = clones.list_clones(clones_dir=tmp_path)
    assert [c["id"] for c in listed] == [a["id"], b["id"]]
    assert [c["name"] for c in listed] == ["Me", "Me, tired"]


def test_any_decodable_audio_is_normalized_to_wav(tmp_path):
    """Browsers record webm/opus; whatever comes in is stored as wav so the
    voice engine can always read it back."""
    entry = clones.add_clone("Me", tone_wav(220), clones_dir=tmp_path)
    data = clones.clone_path(entry["id"], clones_dir=tmp_path).read_bytes()
    assert data[:4] == b"RIFF"  # a real wav container


def test_undecodable_audio_is_rejected(tmp_path):
    try:
        clones.add_clone("Me", b"not audio at all", clones_dir=tmp_path)
        assert False, "expected a ValueError for garbage audio"
    except ValueError:
        pass


def test_stored_sample_is_mono(tmp_path):
    """A stereo browser recording is folded to mono — the voice encoder wants
    one channel, and a clean mono reference clones better."""
    stereo = AudioSegment.from_file(io.BytesIO(tone_wav(220))).set_channels(2)
    entry = clones.add_clone("Me", stereo.export(format="wav").read(), clones_dir=tmp_path)
    assert _measure(clones.clone_path(entry["id"], clones_dir=tmp_path)).channels == 1


def test_leading_and_trailing_silence_is_trimmed(tmp_path):
    """Dead air and breaths at the ends dilute the reference; they're trimmed."""
    padded = (
        AudioSegment.silent(duration=500)
        + AudioSegment.from_file(io.BytesIO(tone_wav(220, seconds=0.5)))
        + AudioSegment.silent(duration=500)
    )
    entry = clones.add_clone("Me", padded.export(format="wav").read(), clones_dir=tmp_path)
    stored = _measure(clones.clone_path(entry["id"], clones_dir=tmp_path))
    # 1500ms in, ~500ms of real speech out (with a little slack).
    assert len(stored) < 900


def test_quiet_recording_is_normalized_louder(tmp_path):
    """A quietly-recorded sample is brought up to a consistent level so the
    encoder hears it clearly."""
    quiet = clones.add_clone("Me", tone_wav(220, amplitude=0.03), clones_dir=tmp_path)
    stored = _measure(clones.clone_path(quiet["id"], clones_dir=tmp_path))
    original = AudioSegment.from_file(io.BytesIO(tone_wav(220, amplitude=0.03)))
    assert stored.dBFS > original.dBFS + 6


def test_delete_removes_the_wav_and_the_index_entry(tmp_path):
    keep = clones.add_clone("Keep me", tone_wav(220), clones_dir=tmp_path)
    drop = clones.add_clone("Drop me", tone_wav(330), clones_dir=tmp_path)

    assert clones.delete_clone(drop["id"], clones_dir=tmp_path) is True

    # The dropped voice's file and registry entry are both gone...
    assert clones.clone_path(drop["id"], clones_dir=tmp_path) is None
    assert [c["id"] for c in clones.list_clones(clones_dir=tmp_path)] == [keep["id"]]
    # ...and the other voice is untouched.
    assert clones.clone_path(keep["id"], clones_dir=tmp_path) is not None


def test_deleting_an_unknown_clone_reports_false(tmp_path):
    assert clones.delete_clone("feedfeedfeedfeed", clones_dir=tmp_path) is False


def test_unknown_clone_has_no_path(tmp_path):
    assert clones.clone_path("feedfeedfeedfeed", clones_dir=tmp_path) is None


def test_empty_registry_lists_nothing(tmp_path):
    assert clones.list_clones(clones_dir=tmp_path) == []
