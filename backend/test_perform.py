"""Tests for the performance loop — the brain of /perform. All dependencies
are injected callables, so these tests run on fakes: no audio, no LLM, no
network. What's under test is pure directing policy: escalate re-roll then
re-direct, spend at most the take budget, stop early on a pass, keep the best
take, and know when an engine simply can't get there."""

import pytest

from judge import TOLERANCE
from perform import arc_correlation, perform_line

PLAN = {
    "settings": {"stability": 0.2, "style": 0.8, "speed": 1.0, "volume": 1.0},
    "tags": ["angry"],
    "delivery": "STOP… IT!",
}
# planned_intensity(PLAN) = 1 - 0.2 = 0.8


class FakeStage:
    """A rigged stage: renders return scripted energies, and every call is
    recorded so tests can assert exactly what the loop did."""

    def __init__(self, energies, redirect_plan=None, redirect_error=None):
        self.energies = list(energies)  # energy measured for each successive render
        self.renders = []  # (plan, take) per render call
        self.redirect_hints = []
        self.redirect_plan = redirect_plan or {**PLAN, "delivery": "STOP IT ALREADY!"}
        self.redirect_error = redirect_error
        self._measured = {}

    def render(self, plan, take):
        self.renders.append((plan, take))
        audio_id = f"clip-{len(self.renders)}"
        self._measured[audio_id] = self.energies[len(self.renders) - 1]
        return {"audio_id": audio_id, "ext": "wav", "engine": "fake", "cached": False}

    def measure(self, audio_id, ext):
        return self._measured[audio_id]

    def redirect(self, hint):
        self.redirect_hints.append(hint)
        if self.redirect_error:
            raise self.redirect_error
        return self.redirect_plan


def run(stage, **kwargs):
    return perform_line(
        text="Stop it.",
        plan=PLAN,
        render=stage.render,
        measure=stage.measure,
        redirect=stage.redirect,
        **kwargs,
    )


def test_a_good_first_take_ends_the_loop_immediately():
    stage = FakeStage(energies=[0.75])  # within 0.25 of target 0.8

    result = run(stage)

    assert len(result["takes"]) == 1
    assert result["takes"][0]["action"] == "plan"
    assert result["kept"] == 0
    assert result["passed"] is True
    assert stage.redirect_hints == []  # never bothered the brain


def test_a_flat_take_gets_a_reroll_and_a_passing_reroll_wins():
    stage = FakeStage(energies=[0.3, 0.7])

    result = run(stage)

    assert [t["action"] for t in result["takes"]] == ["plan", "reroll"]
    assert result["kept"] == 1
    assert result["passed"] is True
    # The re-roll rendered the SAME plan on a fresh take number.
    assert stage.renders[1][0] == PLAN
    assert [take for _, take in stage.renders] == [0, 1]


def test_a_failed_reroll_escalates_to_a_redirect_with_the_miss_note():
    # Flat, slightly better but still flat, then the redirect lands.
    stage = FakeStage(energies=[0.3, 0.4, 0.75])

    result = run(stage)

    assert [t["action"] for t in result["takes"]] == ["plan", "reroll", "redirect"]
    assert result["kept"] == 2
    assert result["passed"] is True
    # The brain got the best take's miss note, numbers included.
    assert len(stage.redirect_hints) == 1
    assert "flatter" in stage.redirect_hints[0] and "0.4" in stage.redirect_hints[0]
    # The redirected plan is what got rendered on take 3.
    assert stage.renders[2][0]["delivery"] == "STOP IT ALREADY!"


def test_the_target_never_drifts_when_a_redirect_changes_the_settings():
    # The redirect makes the settings calmer — but the scene still needs 0.8.
    calmer = {**PLAN, "settings": {**PLAN["settings"], "stability": 0.9}}
    stage = FakeStage(energies=[0.3, 0.35, 0.5], redirect_plan=calmer)

    result = run(stage)

    targets = {t["score"]["target"] for t in result["takes"]}
    assert targets == {0.8}


def test_futility_guard_stops_spending_when_the_engine_cant_emote():
    # Piper-like: flat, and the re-roll moves nothing. Far off target.
    stage = FakeStage(energies=[0.30, 0.31])

    result = run(stage)

    assert [t["action"] for t in result["takes"]] == ["plan", "reroll"]
    assert result["engine_limited"] is True
    assert result["passed"] is False
    assert stage.redirect_hints == []  # the third take was NOT spent


def test_nothing_passes_keeps_the_best_take_honestly():
    stage = FakeStage(energies=[0.2, 0.45, 0.1])

    result = run(stage)

    assert result["passed"] is False
    assert result["kept"] == 1  # 0.45 is closest to 0.8
    assert result["engine_limited"] is False
    assert len(result["takes"]) == 3


def test_take_budget_is_respected():
    stage = FakeStage(energies=[0.3])

    result = run(stage, max_takes=1)

    assert len(result["takes"]) == 1
    assert result["passed"] is False
    assert stage.redirect_hints == []


def test_tolerance_is_adjustable():
    stage = FakeStage(energies=[0.3])

    result = run(stage, tolerance=0.6)

    assert result["passed"] is True
    assert len(result["takes"]) == 1


def test_a_broken_brain_still_ships_the_best_so_far():
    stage = FakeStage(energies=[0.3, 0.4], redirect_error=RuntimeError("brain down"))

    result = run(stage)

    assert [t["action"] for t in result["takes"]] == ["plan", "reroll"]
    assert result["kept"] == 1
    assert result["passed"] is False


def test_every_take_carries_its_audio_and_score():
    stage = FakeStage(energies=[0.3, 0.7])

    result = run(stage)

    for take in result["takes"]:
        assert take["audio_id"].startswith("clip-")
        assert take["ext"] == "wav"
        assert set(take["score"]) == {"target", "measured", "delta", "passed", "hint"}


# --- arc_correlation: the scene-level report number ---


def test_arc_correlation_is_high_when_measured_tracks_planned():
    assert arc_correlation([0.1, 0.4, 0.7, 0.9], [0.15, 0.42, 0.65, 0.88]) == pytest.approx(
        1.0, abs=0.05
    )


def test_arc_correlation_is_none_without_variance_or_enough_lines():
    assert arc_correlation([0.5, 0.5, 0.5], [0.2, 0.6, 0.9]) is None  # flat plan
    assert arc_correlation([0.8], [0.7]) is None  # one line is not an arc
