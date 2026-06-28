"""Tests for the audio cache — the disk store that lets identical renders be
reused instead of re-generated (which is what protects the API quota).
"""

from cache import AudioCache

# A representative settings dict (the shape brains produce after cleaning).
S = {"stability": 0.5, "style": 0.3, "speed": 1.0, "volume": 1.0}
NO_TAGS: list = []


def settings(**overrides):
    return {**S, **overrides}


def test_key_is_deterministic(tmp_path):
    cache = AudioCache(tmp_path)
    assert cache.key("piper", S, "hello", NO_TAGS) == cache.key("piper", S, "hello", NO_TAGS)


def test_key_changes_with_each_input(tmp_path):
    cache = AudioCache(tmp_path)
    base = cache.key("piper", S, "hello", NO_TAGS)
    assert cache.key("elevenlabs", S, "hello", NO_TAGS) != base               # engine
    assert cache.key("piper", settings(speed=0.7), "hello", NO_TAGS) != base   # speed
    assert cache.key("piper", settings(stability=0.9), "hello", NO_TAGS) != base  # stability
    assert cache.key("piper", settings(style=0.9), "hello", NO_TAGS) != base   # style
    assert cache.key("piper", S, "goodbye", NO_TAGS) != base                   # text
    assert cache.key("piper", S, "hello", ["sarcastic"]) != base               # tags


def test_voice_changes_the_key(tmp_path):
    # A different ElevenLabs voice is a different render, so it must key apart.
    cache = AudioCache(tmp_path)
    base = cache.key("elevenlabs", S, "hello", NO_TAGS)  # default voice
    assert cache.key("elevenlabs", S, "hello", NO_TAGS, voice="abc") != base
    assert cache.key("elevenlabs", S, "hello", NO_TAGS, voice="abc") == cache.key(
        "elevenlabs", S, "hello", NO_TAGS, voice="abc"
    )


def test_volume_does_not_affect_the_key(tmp_path):
    # Volume is applied at playback, so it must not change the cached render.
    cache = AudioCache(tmp_path)
    assert cache.key("piper", S, "hello", NO_TAGS) == cache.key(
        "piper", settings(volume=0.3), "hello", NO_TAGS
    )


def test_key_is_a_64_char_hex_hash(tmp_path):
    cache = AudioCache(tmp_path)
    key = cache.key("piper", S, "hello", NO_TAGS)
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


def test_has_is_false_before_write_true_after(tmp_path):
    cache = AudioCache(tmp_path)
    key = cache.key("piper", S, "hello", NO_TAGS)
    assert cache.has(key, "wav") is False
    cache.write(key, "wav", b"fake-audio")
    assert cache.has(key, "wav") is True


def test_write_then_read_round_trips(tmp_path):
    cache = AudioCache(tmp_path)
    key = cache.key("piper", S, "hello", NO_TAGS)
    cache.write(key, "wav", b"fake-audio-bytes")
    assert cache.read(key, "wav") == b"fake-audio-bytes"


def test_different_extensions_do_not_collide(tmp_path):
    cache = AudioCache(tmp_path)
    key = cache.key("piper", S, "hello", NO_TAGS)
    cache.write(key, "wav", b"wav-data")
    assert cache.has(key, "mp3") is False
