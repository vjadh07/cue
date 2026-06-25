"""Tests for the audio cache — the disk store that lets identical renders be
reused instead of re-generated (which is what protects the API quota).
These describe the behavior before the code exists.
"""

from cache import AudioCache


def test_key_is_deterministic(tmp_path):
    cache = AudioCache(tmp_path)
    assert cache.key("piper", 1.0, "hello") == cache.key("piper", 1.0, "hello")


def test_key_changes_with_each_input(tmp_path):
    cache = AudioCache(tmp_path)
    base = cache.key("piper", 1.0, "hello")
    assert cache.key("elevenlabs", 1.0, "hello") != base  # engine matters
    assert cache.key("piper", 0.7, "hello") != base       # speed matters
    assert cache.key("piper", 1.0, "goodbye") != base     # text matters


def test_key_is_a_64_char_hex_hash(tmp_path):
    cache = AudioCache(tmp_path)
    key = cache.key("piper", 1.0, "hello")
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


def test_has_is_false_before_write_true_after(tmp_path):
    cache = AudioCache(tmp_path)
    key = cache.key("piper", 1.0, "hello")
    assert cache.has(key, "wav") is False
    cache.write(key, "wav", b"fake-audio")
    assert cache.has(key, "wav") is True


def test_write_then_read_round_trips(tmp_path):
    cache = AudioCache(tmp_path)
    key = cache.key("piper", 1.0, "hello")
    cache.write(key, "wav", b"fake-audio-bytes")
    assert cache.read(key, "wav") == b"fake-audio-bytes"


def test_different_extensions_do_not_collide(tmp_path):
    cache = AudioCache(tmp_path)
    key = cache.key("piper", 1.0, "hello")
    cache.write(key, "wav", b"wav-data")
    assert cache.has(key, "mp3") is False
