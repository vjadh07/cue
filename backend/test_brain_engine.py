"""Tests for BrainEngine (fallback across brains) and KeywordBrain (the
deterministic final fallback). Fake brains exercise the orchestration without
calling a real LLM.
"""

from brains import BrainEngine, KeywordBrain, _parse_director_json
from settings import DEFAULTS

S = {"stability": 0.4, "style": 0.6, "speed": 1.1, "volume": 0.9}


# --- _parse_director_json: the shared LLM-reply parser used by Ollama + Groq ---


def test_parse_director_json_builds_clean_result():
    content = (
        '{"tags": ["sarcastic", "sighs"], "stability": 0.3, "style": 0.7, '
        '"speed": 1.1, "volume": 0.9, "notes": "smug, dry"}'
    )
    result = _parse_director_json(content)
    assert result["settings"] == {"stability": 0.3, "style": 0.7, "speed": 1.1, "volume": 0.9}
    assert result["tags"] == ["sarcastic", "sighs"]
    assert result["notes"] == "smug, dry"


def test_parse_director_json_filters_unknown_tags_and_clamps():
    # "banana" isn't whitelisted; speed is out of range; stability is missing.
    content = '{"tags": ["sarcastic", "banana", "EXCITED"], "speed": 5.0, "notes": "x"}'
    result = _parse_director_json(content)
    assert result["tags"] == ["sarcastic", "excited"]  # banana dropped, case-normalized
    assert result["settings"]["speed"] == 1.2  # clamped to the supported max
    assert result["settings"]["stability"] == 0.5  # missing -> default


def test_parse_director_json_truncates_long_notes():
    content = '{"notes": "' + "x" * 200 + '"}'
    result = _parse_director_json(content)
    assert len(result["notes"]) == 80


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
