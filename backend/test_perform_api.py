"""Tests for POST /perform — the self-correcting read as an API. Everything
heavy is faked (brain, voice engine, DSP, stitcher): what's under test is the
wiring — plan comes from the brain, takes are salted, the ears' energies flow
through the judge, retries escalate, and the report tells the whole story."""

import pytest
from fastapi.testclient import TestClient

import main


class FakeBrain:
    """interpret_script plans every line; interpret handles redirects."""

    def __init__(self, stabilities):
        self.stabilities = stabilities
        self.redirect_directions = []

    def _result(self, stability):
        return {
            "settings": {"stability": stability, "style": 0.5, "speed": 1.0, "volume": 1.0},
            "tags": [],
            "notes": "",
            "delivery": None,
            "brain": "fake",
        }

    def interpret_script(self, lines, direction, hints=None):
        return [self._result(s) for s in self.stabilities[: len(lines)]]

    def interpret(self, line, direction, script=None, index=0):
        self.redirect_directions.append(direction)
        return self._result(0.1)  # the retry goes rawer


class FakeVoiceEngine:
    def __init__(self):
        self.calls = []  # (text, take, api_key)
        self.n = 0

    def render(self, text, settings, tags, voice="", delivery="", api_key="", take=0):
        self.n += 1
        self.calls.append({"text": text, "take": take, "api_key": api_key, "voice": voice})
        return {"audio_id": f"clip{self.n}", "ext": "wav", "engine": "fake", "cached": False}


@pytest.fixture
def stage(monkeypatch, tmp_path):
    """A rigged production: pass `energies` (in render order) and a brain."""

    def build(energies, stabilities=(0.2,)):
        brain = FakeBrain(list(stabilities))
        engine = FakeVoiceEngine()
        queue = list(energies)
        monkeypatch.setattr(main, "brain_engine", brain)
        monkeypatch.setattr(main, "voice_engine", engine)
        monkeypatch.setattr(main, "profile", lambda audio: {"energy": queue.pop(0)})
        monkeypatch.setattr(main.cache, "read", lambda key, ext: b"audio")
        monkeypatch.setattr(main.cache, "has", lambda key, ext: False)
        monkeypatch.setattr(main.cache, "write", lambda key, ext, data: None)
        monkeypatch.setattr(main.cache, "path", lambda key, ext: tmp_path / f"{key}.{ext}")
        monkeypatch.setattr(main, "stitch", lambda paths, pause_ms=400, volumes=None: (b"t", []))
        monkeypatch.setattr(main, "timeline", lambda paths, pause_ms=400: [])
        return brain, engine, TestClient(main.app)

    return build


def test_a_clean_read_performs_each_line_once(stage):
    # Two lines, both land on take 1 (targets 0.8 and 0.1).
    brain, engine, client = stage(energies=[0.75, 0.15], stabilities=[0.2, 0.9])

    response = client.post("/perform", json={"script": "One.\nTwo.", "direction": "build"})

    assert response.status_code == 200
    body = response.json()
    assert body["captions"] is True
    report = body["report"]
    assert report["total_lines"] == 2
    assert report["passed_lines"] == 2
    assert report["total_renders"] == 2
    assert [line["kept_take"] for line in report["lines"]] == [1, 1]
    assert all(line["takes"][0]["action"] == "plan" for line in report["lines"])
    assert brain.redirect_directions == []


def test_a_flat_take_gets_a_fresh_reroll(stage):
    brain, engine, client = stage(energies=[0.3, 0.75])

    response = client.post("/perform", json={"script": "Stop it.", "direction": "furious"})

    report = response.json()["report"]
    assert report["total_renders"] == 2
    line = report["lines"][0]
    assert [t["action"] for t in line["takes"]] == ["plan", "reroll"]
    assert line["kept_take"] == 2
    assert line["passed"] is True
    # The re-roll went out with a fresh take number — a real re-render.
    assert [c["take"] for c in engine.calls] == [0, 1]


def test_escalation_reaches_the_brain_with_the_miss_note(stage):
    # Raw energies: flat, then better-but-short, then the redirect lands
    # (calibrated: 0.0 -> 0.29 -> 0.94 against target 0.8).
    brain, engine, client = stage(energies=[0.3, 0.55, 0.78])

    response = client.post("/perform", json={"script": "Stop it.", "direction": "furious"})

    line = response.json()["report"]["lines"][0]
    assert [t["action"] for t in line["takes"]] == ["plan", "reroll", "redirect"]
    assert line["passed"] is True
    # The redirect carried the judge's note, numbers and all.
    assert len(brain.redirect_directions) == 1
    assert "flatter" in brain.redirect_directions[0]
    assert "furious" in brain.redirect_directions[0]  # the scene note survives


def test_perform_forwards_the_visitors_key_to_every_render(stage):
    brain, engine, client = stage(energies=[0.75])

    client.post(
        "/perform",
        json={"script": "One."},
        headers={"X-ElevenLabs-Key": "visitor-key"},
    )

    assert all(c["api_key"] == "visitor-key" for c in engine.calls)


def test_cast_routes_speaker_lines_to_their_voices(stage):
    brain, engine, client = stage(energies=[0.75, 0.75], stabilities=[0.2, 0.2])

    client.post(
        "/perform",
        json={"script": "NORA: Hey.\nELI: Hi.", "cast": {"NORA": "v-nora"}, "voice": "v-narr"},
    )

    assert [c["voice"] for c in engine.calls] == ["v-nora", "v-narr"]


def test_empty_script_is_a_400(stage):
    _, _, client = stage(energies=[])
    assert client.post("/perform", json={"script": "   "}).status_code == 400


def test_take_budget_is_clamped_to_the_loops_three_stages(stage):
    # Always failing, always improving (dodges futility): must stop at 3.
    # (Calibrated: 0.14 -> 0.29 -> 0.43 against target 0.8.)
    brain, engine, client = stage(energies=[0.5, 0.55, 0.6])

    response = client.post(
        "/perform", json={"script": "Stop it.", "direction": "furious", "max_takes": 99}
    )

    assert response.json()["report"]["total_renders"] == 3
    assert len(engine.calls) == 3
