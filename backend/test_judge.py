"""Tests for the judge — the loop's ears. Pure scoring: given the emotional
target the plan implied and the energy the booth measured, did the take land,
and if not, what's the director's note for the retry? No audio, no I/O."""

from judge import TOLERANCE, judge_take, planned_intensity

S = {"stability": 0.2, "style": 0.8, "speed": 1.0, "volume": 1.0}


# --- planned_intensity: the target implied by the brain's plan ---


def test_target_matches_the_booth_chart_formula():
    # The shipped Booth chart draws planned intensity as 1 - stability.
    assert planned_intensity({**S, "stability": 0.2}) == 0.8
    assert planned_intensity({**S, "stability": 0.9}) == 0.1


def test_target_is_clamped_to_the_unit_range():
    assert planned_intensity({**S, "stability": -0.4}) == 1.0
    assert planned_intensity({**S, "stability": 1.7}) == 0.0


# --- calibrate: raw booth energy -> the target's 0..1 scale ---
# TTS output is loudness-normalized, so ALL speech measures inside a narrow
# raw band; emotion lives inside it. Calibration stretches that band to the
# unit range the targets speak. Anchors bracket every live measurement to
# date: calm reads 0.54..0.58 raw, full shouts 0.63..0.71 raw. The first
# anchors (0.45..0.8) left hot targets mathematically unreachable: the best
# live shout scored 0.62 against an aim of 0.9 and could never close.


def test_calibration_stretches_the_speech_band():
    from judge import calibrate

    assert calibrate(0.50) == 0.0
    assert calibrate(0.72) == 1.0
    assert calibrate(0.54) < 0.3  # live calm read -> low
    assert calibrate(0.71) > 0.9  # the hottest live shout -> near the top


def test_calibration_clamps_outside_the_band():
    from judge import calibrate

    assert calibrate(0.3) == 0.0
    assert calibrate(0.95) == 1.0


def test_a_real_shout_can_land_a_demanding_target():
    """The regression that moved the anchors: the best live shout (0.667 raw,
    full delivery markup) must be able to pass a 0.9 target. Under the old
    anchors it calibrated to 0.62 and no take could ever close the gap."""
    from judge import calibrate, judge_take

    verdict = judge_take(calibrate(0.667), target=0.9)
    assert verdict["passed"] is True


# --- judge_take: did the take land? ---


def test_a_close_take_passes_with_no_hint():
    verdict = judge_take(measured_energy=0.7, target=0.8)
    assert verdict["passed"] is True
    assert verdict["hint"] is None
    assert verdict["delta"] == -0.1


def test_exactly_at_tolerance_still_passes():
    verdict = judge_take(measured_energy=0.8 - TOLERANCE, target=0.8)
    assert verdict["passed"] is True


def test_a_flat_take_fails_with_a_push_harder_hint():
    verdict = judge_take(measured_energy=0.3, target=0.8)
    assert verdict["passed"] is False
    assert verdict["delta"] == -0.5
    assert "flatter" in verdict["hint"]
    assert "push" in verdict["hint"]
    # The hint carries the numbers, so the brain knows how far off it was.
    assert "0.3" in verdict["hint"] and "0.8" in verdict["hint"]


def test_an_overcooked_take_fails_with_a_pull_back_hint():
    verdict = judge_take(measured_energy=0.9, target=0.2)
    assert verdict["passed"] is False
    assert "hotter" in verdict["hint"]
    assert "pull" in verdict["hint"]


def test_tolerance_is_adjustable_per_call():
    strict = judge_take(measured_energy=0.7, target=0.8, tolerance=0.05)
    assert strict["passed"] is False
    loose = judge_take(measured_energy=0.3, target=0.8, tolerance=0.6)
    assert loose["passed"] is True


def test_verdict_reports_rounded_fields():
    verdict = judge_take(measured_energy=0.33333, target=0.77777)
    assert verdict["measured"] == 0.333
    assert verdict["target"] == 0.778
    assert verdict["delta"] == round(0.333 - 0.778, 3)
