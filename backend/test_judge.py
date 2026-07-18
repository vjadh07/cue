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
