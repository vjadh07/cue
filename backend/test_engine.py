"""Tests for the Engine — the orchestrator that picks a provider, falls back
when one fails, and skips synthesis entirely on a cache hit. Fake providers
let us test the logic without calling a real voice service.
"""

from cache import AudioCache
from engine import Engine

S = {"stability": 0.5, "style": 0.3, "speed": 1.0, "volume": 1.0}
TAGS = ["sarcastic"]


class FakeProvider:
    def __init__(self, name, ext, fail=False):
        self.name = name
        self.ext = ext
        self.fail = fail
        self.calls = 0
        self.last_voice = None

    def synthesize(self, text, settings, tags, voice=""):
        self.calls += 1
        self.last_voice = voice
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        return f"{self.name}-audio".encode()


def test_uses_first_provider_when_it_works(tmp_path):
    el = FakeProvider("elevenlabs", "mp3")
    piper = FakeProvider("piper", "wav")
    engine = Engine([el, piper], AudioCache(tmp_path))

    result = engine.render("hello", S, TAGS)

    assert result["engine"] == "elevenlabs"
    assert result["cached"] is False
    assert el.calls == 1
    assert piper.calls == 0  # never needed the fallback


def test_falls_back_when_first_provider_fails(tmp_path):
    el = FakeProvider("elevenlabs", "mp3", fail=True)
    piper = FakeProvider("piper", "wav")
    engine = Engine([el, piper], AudioCache(tmp_path))

    result = engine.render("hello", S, TAGS)

    assert result["engine"] == "piper"
    assert result["cached"] is False
    assert el.calls == 1
    assert piper.calls == 1


def test_cache_hit_skips_all_synthesis(tmp_path):
    cache = AudioCache(tmp_path)
    el = FakeProvider("elevenlabs", "mp3")
    piper = FakeProvider("piper", "wav")
    # Pre-seed the cache as if elevenlabs had already rendered this line.
    key = cache.key("elevenlabs", S, "hello", TAGS)
    cache.write(key, "mp3", b"cached-audio")

    engine = Engine([el, piper], cache)
    result = engine.render("hello", S, TAGS)

    assert result["cached"] is True
    assert result["engine"] == "elevenlabs"
    assert result["audio_id"] == key
    assert el.calls == 0  # served from disk, nothing synthesized
    assert piper.calls == 0


def test_miss_writes_result_to_cache(tmp_path):
    cache = AudioCache(tmp_path)
    engine = Engine([FakeProvider("piper", "wav")], cache)

    result = engine.render("hello", S, TAGS)

    assert cache.has(result["audio_id"], "wav") is True


def test_raises_when_all_providers_fail(tmp_path):
    engine = Engine(
        [FakeProvider("elevenlabs", "mp3", fail=True), FakeProvider("piper", "wav", fail=True)],
        AudioCache(tmp_path),
    )
    try:
        engine.render("hello", S, TAGS)
        assert False, "expected an error when every provider fails"
    except RuntimeError:
        pass


def test_render_passes_voice_to_provider(tmp_path):
    el = FakeProvider("elevenlabs", "mp3")
    engine = Engine([el], AudioCache(tmp_path))

    engine.render("hello", S, TAGS, voice="george")

    assert el.last_voice == "george"


def test_different_voice_is_a_different_render(tmp_path):
    # Same line/settings/tags but a different voice must not reuse the cache.
    cache = AudioCache(tmp_path)
    a = Engine([FakeProvider("elevenlabs", "mp3")], cache)
    b = Engine([FakeProvider("elevenlabs", "mp3")], cache)

    r1 = a.render("hello", S, TAGS, voice="george")
    r2 = b.render("hello", S, TAGS, voice="sarah")

    assert r1["audio_id"] != r2["audio_id"]
