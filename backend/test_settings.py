"""Tests for settings.clean() — the safety net that turns whatever a brain
returns (a good LLM, a confused LLM, or garbage) into valid voice settings.
Nothing downstream should ever see an out-of-range or missing value.
"""

from settings import clean, clean_tags, DEFAULTS


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


def test_clean_tags_keeps_known_tags():
    assert clean_tags(["sarcastic", "sighs"]) == ["sarcastic", "sighs"]


def test_clean_tags_drops_unknown_tags():
    # The whitelist is the safety net: junk can't get read aloud as text.
    assert clean_tags(["sarcastic", "banana"]) == ["sarcastic"]


def test_clean_tags_handles_non_list():
    assert clean_tags("sarcastic") == []
    assert clean_tags(None) == []


def test_clean_tags_normalizes_case_and_brackets():
    assert clean_tags(["[Sarcastic]", "WHISPERS"]) == ["sarcastic", "whispers"]


def test_clean_tags_dedupes():
    assert clean_tags(["sighs", "sighs"]) == ["sighs"]


def test_clean_tags_caps_at_max():
    from settings import MAX_TAGS

    tags = ["excited", "sad", "angry", "happy", "tired", "calm"]
    assert clean_tags(tags) == tags[:MAX_TAGS]


def test_clean_tags_ignores_non_strings():
    assert clean_tags(["sad", 5, None]) == ["sad"]
