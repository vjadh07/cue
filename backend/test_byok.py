"""Bring-your-own-key: a visitor can supply their own ElevenLabs API key per
request (X-ElevenLabs-Key header) so their reads spend their credits, not the
host's. The key is never stored server-side and never changes the cache key —
the same render is the same audio no matter whose account paid for it.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

import main
from cache import AudioCache
from engine import Engine
from providers import ElevenLabsProvider

S = {"stability": 0.5, "style": 0.3, "speed": 1.0, "volume": 1.0}


class RecordingPost:
    """Stands in for httpx.post and captures the headers it was called with."""

    def __init__(self):
        self.headers = None

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.headers = headers
        request = httpx.Request("POST", url)
        return httpx.Response(200, content=b"audio-bytes", request=request)


def test_provider_uses_override_key_when_given(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "host-key")
    recorder = RecordingPost()
    monkeypatch.setattr("providers.httpx.post", recorder)

    provider = ElevenLabsProvider()
    provider.synthesize("hello", S, [], api_key="visitor-key")

    assert recorder.headers["xi-api-key"] == "visitor-key"


def test_provider_falls_back_to_env_key_without_override(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "host-key")
    recorder = RecordingPost()
    monkeypatch.setattr("providers.httpx.post", recorder)

    provider = ElevenLabsProvider()
    provider.synthesize("hello", S, [])

    assert recorder.headers["xi-api-key"] == "host-key"


def test_provider_works_with_override_even_when_env_key_missing(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    recorder = RecordingPost()
    monkeypatch.setattr("providers.httpx.post", recorder)

    provider = ElevenLabsProvider()
    provider.synthesize("hello", S, [], api_key="visitor-key")

    assert recorder.headers["xi-api-key"] == "visitor-key"


class FakeProvider:
    name = "fake"
    ext = "mp3"

    def __init__(self):
        self.last_api_key = None

    def synthesize(self, text, settings, tags, voice="", delivery="", api_key=""):
        self.last_api_key = api_key
        return b"fake-audio"


def test_engine_passes_api_key_to_provider(tmp_path):
    provider = FakeProvider()
    engine = Engine([provider], AudioCache(tmp_path))

    engine.render("hello", S, [], api_key="visitor-key")

    assert provider.last_api_key == "visitor-key"


def test_api_key_does_not_change_the_cache_key(tmp_path):
    """Same render, different payer -> same audio, served from cache."""
    provider = FakeProvider()
    engine = Engine([provider], AudioCache(tmp_path))

    first = engine.render("hello", S, [], api_key="key-a")
    second = engine.render("hello", S, [], api_key="key-b")

    assert first["audio_id"] == second["audio_id"]
    assert second["cached"] is True


class RecordingEngine:
    """Stands in for main.voice_engine and records the api_key it was given."""

    def __init__(self):
        self.api_keys = []

    def render(self, text, settings, tags, voice="", delivery="", api_key=""):
        self.api_keys.append(api_key)
        return {"audio_id": "a" * 64, "ext": "mp3", "engine": "fake", "cached": False}


@pytest.fixture
def client():
    return TestClient(main.app)


def test_render_endpoint_forwards_header_key(client, monkeypatch):
    engine = RecordingEngine()
    monkeypatch.setattr(main, "voice_engine", engine)

    response = client.post(
        "/render",
        json={"text": "hello"},
        headers={"X-ElevenLabs-Key": "visitor-key"},
    )

    assert response.status_code == 200
    assert engine.api_keys == ["visitor-key"]


def test_render_endpoint_defaults_to_empty_key(client, monkeypatch):
    engine = RecordingEngine()
    monkeypatch.setattr(main, "voice_engine", engine)

    response = client.post("/render", json={"text": "hello"})

    assert response.status_code == 200
    assert engine.api_keys == [""]


def test_read_endpoint_forwards_header_key_to_every_line(client, monkeypatch, tmp_path):
    engine = RecordingEngine()
    monkeypatch.setattr(main, "voice_engine", engine)
    # stitching needs real clip files on disk — fake the whole stitch step
    monkeypatch.setattr(main, "stitch", lambda paths, pause_ms=400, volumes=None: b"track")
    monkeypatch.setattr(main.cache, "has", lambda key, ext: False)
    monkeypatch.setattr(main.cache, "write", lambda key, ext, data: None)
    monkeypatch.setattr(main.cache, "path", lambda key, ext: tmp_path / f"{key}.{ext}")

    response = client.post(
        "/read",
        json={"lines": [{"text": "one"}, {"text": "two"}]},
        headers={"X-ElevenLabs-Key": "visitor-key"},
    )

    assert response.status_code == 200
    assert engine.api_keys == ["visitor-key", "visitor-key"]


def test_voices_endpoint_uses_header_key(client, monkeypatch):
    seen = {}

    def fake_get(url, headers=None, timeout=None):
        seen["key"] = headers["xi-api-key"]
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            json={"voices": [{"voice_id": "v1", "name": "Ada", "category": "premade", "labels": {}}]},
            request=request,
        )

    monkeypatch.setattr("main.httpx.get", fake_get)

    response = client.get("/voices", headers={"X-ElevenLabs-Key": "visitor-key"})

    assert response.status_code == 200
    assert seen["key"] == "visitor-key"
    assert response.json()["voices"][0]["id"] == "v1"


def test_voices_endpoint_rejects_bad_explicit_key(client, monkeypatch):
    """A key the visitor typed in gets a clear 401, not a silent fallback list —
    this is what lets the studio verify a pasted key on the spot. The rejection
    must never echo the key itself."""

    def fake_get(url, headers=None, timeout=None):
        request = httpx.Request("GET", url)
        response = httpx.Response(401, json={"detail": "invalid"}, request=request)
        raise httpx.HTTPStatusError("401", request=request, response=response)

    monkeypatch.setattr("main.httpx.get", fake_get)

    response = client.get("/voices", headers={"X-ElevenLabs-Key": "bad-key"})

    assert response.status_code == 401
    assert "bad-key" not in response.text


class ExplodingEngine:
    """Every render fails — the way Engine fails when all providers are down."""

    def render(self, *args, **kwargs):
        raise RuntimeError("all voice providers failed")


def test_failed_render_is_a_clean_503_that_never_echoes_the_key(monkeypatch):
    monkeypatch.setattr(main, "voice_engine", ExplodingEngine())
    client = TestClient(main.app, raise_server_exceptions=False)

    response = client.post(
        "/render",
        json={"text": "hello"},
        headers={"X-ElevenLabs-Key": "super-secret-key"},
    )

    assert response.status_code == 503
    assert "super-secret-key" not in response.text


def test_failed_read_is_a_clean_503_that_never_echoes_the_key(monkeypatch):
    monkeypatch.setattr(main, "voice_engine", ExplodingEngine())
    client = TestClient(main.app, raise_server_exceptions=False)

    response = client.post(
        "/read",
        json={"lines": [{"text": "hello"}]},
        headers={"X-ElevenLabs-Key": "super-secret-key"},
    )

    assert response.status_code == 503
    assert "super-secret-key" not in response.text
