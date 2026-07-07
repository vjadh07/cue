"""Tests for the local clone registry — where a user's voice lives when Cue
clones it: on THEIR disk, as a wav + an index entry, never anywhere else."""

import clones
from test_listen import tone_wav


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


def test_unknown_clone_has_no_path(tmp_path):
    assert clones.clone_path("feedfeedfeedfeed", clones_dir=tmp_path) is None


def test_empty_registry_lists_nothing(tmp_path):
    assert clones.list_clones(clones_dir=tmp_path) == []
