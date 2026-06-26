"""Tests for BrainEngine (fallback across brains) and KeywordBrain (the
deterministic final fallback). Fake brains exercise the orchestration without
calling a real LLM.
"""

from brains import BrainEngine, KeywordBrain
from settings import DEFAULTS

S = {"stability": 0.4, "style": 0.6, "speed": 1.1, "volume": 0.9}


class FakeBrain:
    def __init__(self, name, fail=False):
        self.name = name
        self.fail = fail
        self.calls = 0

    def interpret(self, line, direction):
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.name} down")
        return {"settings": S, "tags": ["sarcastic"], "notes": f"{self.name} read"}


def test_uses_first_brain_when_it_works():
    a, b = FakeBrain("groq"), FakeBrain("ollama")
    result = BrainEngine([a, b]).interpret("hi", "warm")
    assert result["brain"] == "groq"
    assert result["settings"] == S
    assert result["tags"] == ["sarcastic"]
    assert a.calls == 1
    assert b.calls == 0


def test_falls_back_when_first_brain_fails():
    a, b = FakeBrain("groq", fail=True), FakeBrain("ollama")
    result = BrainEngine([a, b]).interpret("hi", "warm")
    assert result["brain"] == "ollama"
    assert a.calls == 1
    assert b.calls == 1


def test_all_brains_failing_returns_neutral():
    result = BrainEngine([FakeBrain("groq", fail=True), FakeBrain("ollama", fail=True)]).interpret(
        "hi", "warm"
    )
    assert result["settings"] == DEFAULTS
    assert result["tags"] == []
    assert result["brain"] == "none"


def test_keyword_brain_maps_slow_to_speed():
    result = KeywordBrain().interpret("hi", "slow")
    assert result["settings"]["speed"] == 0.7
    assert "slow" in result["notes"]


def test_keyword_brain_neutral_when_no_keywords():
    result = KeywordBrain().interpret("hi", "")
    assert result["settings"] == DEFAULTS
    assert result["notes"] == ""
