"""Tests for the direction interpreter — the 'brain' that turns a plain-English
note into voice settings. These describe the behavior we want before the code
exists, so each one fails first, then passes once interpret() is built.
"""

from direction import interpret


def test_empty_direction_is_neutral():
    # No direction = the line is read normally, nothing matched.
    result = interpret("")
    assert result["settings"] == {"speed": 1.0, "pitch": 1.0, "volume": 1.0}
    assert result["matched"] == []


def test_slow_lowers_speed():
    result = interpret("slow")
    assert result["settings"]["speed"] == 0.7
    assert result["matched"] == ["slow"]


def test_warm_lowers_pitch():
    result = interpret("warm")
    assert result["settings"]["pitch"] == 0.75
    assert result["matched"] == ["warm"]


def test_whisper_lowers_volume_more_than_soft():
    assert interpret("soft")["settings"]["volume"] == 0.7
    assert interpret("whisper")["settings"]["volume"] == 0.4


def test_words_stack_across_knobs():
    # "warm and slow" should move pitch AND speed; "and" is ignored.
    result = interpret("warm and slow")
    assert result["settings"]["speed"] == 0.7
    assert result["settings"]["pitch"] == 0.75
    assert result["settings"]["volume"] == 1.0
    assert result["matched"] == ["warm", "slow"]


def test_contradictions_blend_not_error():
    # fast (+0.4) and slow (-0.3) sum to a slightly-fast 1.1, no crash.
    result = interpret("fast and slow")
    assert result["settings"]["speed"] == 1.1
    assert result["matched"] == ["fast", "slow"]


def test_unknown_words_are_ignored():
    result = interpret("say it nicely please")
    assert result["settings"] == {"speed": 1.0, "pitch": 1.0, "volume": 1.0}
    assert result["matched"] == []


def test_matching_is_case_insensitive():
    result = interpret("SLOW")
    assert result["settings"]["speed"] == 0.7
    assert result["matched"] == ["slow"]


def test_punctuation_does_not_block_a_match():
    result = interpret("slow!")
    assert result["matched"] == ["slow"]


def test_settings_are_clamped_to_safe_range():
    # Four "slow" would push speed to -0.2; it must clamp at the 0.5 floor.
    result = interpret("slow slow slow slow")
    assert result["settings"]["speed"] == 0.5
