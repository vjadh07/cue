"""The performance loop — the brain of /perform.

A director's session for one line: render the planned take, LISTEN to it
(the booth's DSP), and if the emotion missed, re-take — first a cheap
re-roll (TTS is stochastic; a fresh render often lands), then a smart
re-direct (the brain rewrites the delivery knowing exactly how the last
take missed). Spend at most the take budget, stop the moment a take
passes, and always keep the best take — a director ships the scene either
way, and the report says honestly what happened.

Dependencies (render / measure / redirect) are injected callables, so this
module is pure policy: no audio, no LLM, no network. main.py wires the real
engine, ears, and brain around it.
"""

import numpy as np

from judge import TOLERANCE, judge_take, planned_intensity

MAX_TAKES = 3

# If a re-roll barely moves the needle while we're still far from the target,
# the engine physically can't get there (Piper has no emotion controls) —
# stop spending takes and say so.
FUTILITY_MIN_GAIN = 0.03
FUTILITY_FAR = 1.5  # "far" = worse than this many tolerances from the target


def perform_line(
    *,
    text: str,
    plan: dict,
    render,
    measure,
    redirect,
    max_takes: int = MAX_TAKES,
    tolerance: float = TOLERANCE,
) -> dict:
    """Direct one line until it lands or the budget is spent.

    plan: {settings, tags, delivery} from the brain's whole-script pass.
    render(plan, take) -> {audio_id, ext, engine, cached}
    measure(audio_id, ext) -> energy 0..1 (the booth's ears)
    redirect(hint) -> a new plan, the brain re-reading the line with the miss note

    Returns {takes, kept, passed, engine_limited, target} where each take is
    {take, action, audio_id, ext, engine, score}.
    """
    # The scene's need comes from the ORIGINAL plan. A retry may turn the
    # knobs, but the target it is judged against never drifts.
    target = planned_intensity(plan["settings"])

    takes: list[dict] = []

    def attempt(action: str, the_plan: dict, take_number: int) -> dict:
        rendered = render(the_plan, take_number)
        energy = measure(rendered["audio_id"], rendered["ext"])
        score = judge_take(energy, target, tolerance)
        entry = {
            "take": len(takes) + 1,
            "action": action,
            "audio_id": rendered["audio_id"],
            "ext": rendered["ext"],
            "engine": rendered.get("engine", ""),
            "score": score,
        }
        takes.append(entry)
        return entry

    def best_index() -> int:
        return min(range(len(takes)), key=lambda i: abs(takes[i]["score"]["delta"]))

    def result(engine_limited: bool = False) -> dict:
        kept = best_index()
        return {
            "takes": takes,
            "kept": kept,
            "passed": takes[kept]["score"]["passed"],
            "engine_limited": engine_limited,
            "target": target,
        }

    # Take 1: the plan as directed.
    first = attempt("plan", plan, 0)
    if first["score"]["passed"] or max_takes <= 1:
        return result()

    # Take 2: the re-roll — same markup, fresh render.
    try:
        reroll = attempt("reroll", plan, 1)
    except Exception:
        return result()  # a broken retry never takes down the line
    if reroll["score"]["passed"]:
        return result()

    # Futility: the re-roll changed almost nothing and we're far off target —
    # this engine can't produce the asked-for emotion. Don't spend take 3.
    gain = abs(first["score"]["delta"]) - abs(reroll["score"]["delta"])
    still_far = abs(takes[best_index()]["score"]["delta"]) > FUTILITY_FAR * tolerance
    if gain < FUTILITY_MIN_GAIN and still_far:
        return result(engine_limited=True)

    if max_takes <= 2:
        return result()

    # Take 3: the re-direct — the brain re-reads the line with the miss note.
    try:
        hint = takes[best_index()]["score"]["hint"]
        new_plan = redirect(hint)
        attempt("redirect", new_plan, 2)
    except Exception:
        return result()  # brain down or render failed — ship the best so far
    return result()


def arc_correlation(planned: list[float], measured: list[float]) -> float | None:
    """How well the measured emotional arc tracked the planned one across a
    scene (Pearson r). Reported, never a pass criterion. None when there's no
    arc to correlate: fewer than two lines, or no variance in either series."""
    if len(planned) < 2 or len(measured) < 2 or len(planned) != len(measured):
        return None
    p = np.array(planned, dtype=float)
    m = np.array(measured, dtype=float)
    if p.std() == 0 or m.std() == 0:
        return None
    return round(float(np.corrcoef(p, m)[0, 1]), 3)
