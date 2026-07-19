"""Tests for /health and /status — the deploy-facing pulse of the backend.

/health is the liveness probe every hosting platform wants: always cheap,
always 200 while the process lives. /status says which brains and voices are
actually ready, for demos and debugging — using only cheap local checks
(booleans, counts): no API quota spent, no key material ever in the body.
"""

import pytest
from fastapi.testclient import TestClient

import main
from brains import BrainEngine, GroqBrain, KeywordBrain, OllamaBrain
from engine import Engine
from providers import ChatterboxProvider, ElevenLabsProvider, PiperProvider


def client():
    return TestClient(main.app)


# --- /health: the liveness probe ---


def test_health_is_always_ok():
    response = client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


# --- ready(): each part's own cheap self-check ---


def test_groq_ready_means_a_key_is_configured():
    brain = GroqBrain()
    brain.api_key = ""
    assert brain.ready() is False
    brain.api_key = "k"
    assert brain.ready() is True


def test_ollama_ready_means_the_server_answers(monkeypatch):
    class Up:
        status_code = 200

    monkeypatch.setattr("brains.httpx.get", lambda url, timeout: Up())
    assert OllamaBrain().ready() is True

    def down(url, timeout):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("brains.httpx.get", down)
    assert OllamaBrain().ready() is False


def test_keyword_brain_is_always_ready():
    assert KeywordBrain().ready() is True


def test_elevenlabs_ready_means_a_host_key_is_configured():
    provider = ElevenLabsProvider()
    provider.api_key = ""
    assert provider.ready() is False
    provider.api_key = "k"
    assert provider.ready() is True


def test_piper_ready_means_the_voice_model_file_exists(monkeypatch, tmp_path):
    monkeypatch.setattr("providers.PIPER_MODEL", tmp_path / "missing.onnx")
    assert PiperProvider().ready() is False
    present = tmp_path / "voice.onnx"
    present.write_bytes(b"onnx")
    monkeypatch.setattr("providers.PIPER_MODEL", present)
    assert PiperProvider().ready() is True


def test_chatterbox_ready_does_not_load_the_model():
    # ready() is a status check, not a warmup: ~2GB of weights must NOT load.
    provider = ChatterboxProvider()
    assert provider.ready() in (True, False)
    assert provider._model is None


# --- status(): the engines' rollups ---


class FakePart:
    def __init__(self, name, up):
        self.name = name
        self._up = up

    def ready(self):
        return self._up


def test_brain_engine_status_reports_each_brain_in_chain_order():
    engine = BrainEngine([FakePart("groq", True), FakePart("keyword", False)])
    assert engine.status() == [
        {"name": "groq", "ready": True},
        {"name": "keyword", "ready": False},
    ]


def test_voice_engine_status_reports_each_provider_in_chain_order():
    engine = Engine([FakePart("elevenlabs", False), FakePart("piper", True)], cache=None)
    assert engine.status() == [
        {"name": "elevenlabs", "ready": False},
        {"name": "piper", "ready": True},
    ]


# --- GET /status: the endpoint ---


@pytest.fixture
def rigged(monkeypatch, tmp_path):
    monkeypatch.setattr(
        main, "brain_engine", BrainEngine([FakePart("groq", True), FakePart("keyword", True)])
    )
    monkeypatch.setattr(
        main, "voice_engine", Engine([FakePart("chatterbox", True)], cache=None)
    )
    monkeypatch.setattr("clones.CLONES_DIR", tmp_path)  # empty registry


def test_status_reports_brains_voices_and_clones(rigged):
    response = client().get("/status")
    assert response.status_code == 200
    body = response.json()
    assert body["brains"] == [
        {"name": "groq", "ready": True},
        {"name": "keyword", "ready": True},
    ]
    assert body["voices"] == [{"name": "chatterbox", "ready": True}]
    assert body["clones"] == 0


def test_status_carries_no_secret_material(rigged, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sk-groq-secret-value")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-eleven-secret-value")
    body = client().get("/status").text
    assert "secret-value" not in body
    assert "api_key" not in body  # booleans only, never the material
