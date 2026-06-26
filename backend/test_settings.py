"""Tests for settings.clean() — the safety net that turns whatever a brain
returns (a good LLM, a confused LLM, or garbage) into valid voice settings.
Nothing downstream should ever see an out-of-range or missing value.
"""

from settings import clean, DEFAULTS


def test_valid_settings_pass_through():
    raw = {"stability": 0.3, "style": 0.8, "speed": 0.9, "volume": 0.5}
    assert clean(raw) == {"stability": 0.3, "style": 0.8, "speed": 0.9, "volume": 0.5}


def test_out_of_range_values_are_clamped():
    raw = {"stability": 9000, "style": -5, "speed": 5.0, "volume": 0.0}
    result = clean(raw)
    assert result["stability"] == 1.0
    assert result["style"] == 0.0
    assert result["speed"] == 1.2   # ElevenLabs speed ceiling
    assert result["volume"] == 0.1  # volume floor


def test_speed_below_floor_is_clamped():
    assert clean({"speed": 0.1})["speed"] == 0.7


def test_missing_keys_get_defaults():
    assert clean({}) == DEFAULTS


def test_non_numeric_values_fall_back_to_default():
    result = clean({"stability": "high", "speed": None, "style": "lots"})
    assert result["stability"] == DEFAULTS["stability"]
    assert result["speed"] == DEFAULTS["speed"]
    assert result["style"] == DEFAULTS["style"]


def test_extra_keys_are_ignored():
    result = clean({"stability": 0.5, "notes": "hi", "foo": 1})
    assert set(result.keys()) == {"stability", "style", "speed", "volume"}


def test_values_are_rounded_to_two_decimals():
    assert clean({"stability": 0.333333})["stability"] == 0.33
