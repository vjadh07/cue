"""The judge — the performance loop's ears.

Pure scoring, no I/O: given the emotional target a plan implied and the
energy the booth actually measured in the rendered audio, decide whether the
take landed. When it didn't, the verdict carries a director's note (`hint`)
written to feed straight back to the brain as the retry's direction — the
ears telling the mouth exactly how the take missed.

Kept deliberately tiny and numeric so it doubles as a standalone evals
primitive: audio in (via listen.profile), verdict out.
"""

# How far measured energy may sit from the target and still count as landed.
# Calibrated against live booth measurements: a genuinely directed take lands
# well inside 0.25; a flat read against a hot target misses by ~0.5.
TOLERANCE = 0.25

# Raw booth energy compresses all speech into a narrow band — every TTS
# normalizes loudness, so emotion moves the number only within ~0.45..0.8
# (live anchors: a calm read measured ~0.54, a shouted take ~0.71). The
# targets speak full 0..1, so the judge stretches the speech band onto it.
SPEECH_FLOOR = 0.45
SPEECH_CEIL = 0.8


def calibrate(raw_energy: float) -> float:
    """Map raw booth energy onto the target's 0..1 scale."""
    scaled = (raw_energy - SPEECH_FLOOR) / (SPEECH_CEIL - SPEECH_FLOOR)
    return round(min(1.0, max(0.0, scaled)), 3)


def planned_intensity(settings: dict) -> float:
    """The emotional intensity a plan implies, 0..1. Matches the shipped
    Booth chart exactly (planned = 1 - stability), so the loop, the chart,
    and the report all speak the same scale."""
    return round(min(1.0, max(0.0, 1.0 - settings["stability"])), 3)


def judge_take(measured_energy: float, target: float, tolerance: float = TOLERANCE) -> dict:
    """Score one take. Returns {target, measured, delta, passed, hint} —
    hint is None on a pass, otherwise the note for the retry."""
    measured = round(measured_energy, 3)
    goal = round(target, 3)
    delta = round(measured - goal, 3)
    passed = abs(delta) <= tolerance

    hint = None
    if not passed:
        if delta < 0:
            hint = (
                f"the last take came out flatter than directed "
                f"(energy {measured} vs target {goal}): push the intensity, more heat"
            )
        else:
            hint = (
                f"the last take came out hotter than directed "
                f"(energy {measured} vs target {goal}): pull it back, calmer, more controlled"
            )

    return {"target": goal, "measured": measured, "delta": delta, "passed": passed, "hint": hint}
