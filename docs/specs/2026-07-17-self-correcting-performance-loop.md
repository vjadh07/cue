# The self-correcting performance loop

*Spec, 2026-07-17. Decisions locked with Viraj: escalating retries (re-roll,
then re-direct), 3 takes max per line, API first with a studio toggle after,
and on a miss we always ship the best take with an honest report.*

## What it is

`POST /perform`: send a script and a direction; Cue plans the performance,
renders it, listens to every line with its own DSP, and re-takes the lines
that missed the emotional target, escalating from a cheap re-roll to a smart
re-direct, until they land or the budget is spent. Returns one produced track
(with captions) plus a per-take report of everything it tried and measured.

One sentence for the pitch: voice generation that checks its own work.

## Why

Every TTS wrapper can generate speech. Almost nobody can answer "did the
emotion actually land?" Cue already has the two halves nobody else has: a
director brain that turns intent into per-line markup, and the booth's ears
that measure rendered audio (loudness, pitch, energy) with plain DSP. This
loop wires mouth to ears: plan, act, observe, self-correct. The report doubles
as "evals for voice", the missing primitive in the 2026 voice stack.

## The three parts

### 1. The ears: `judge.py` (pure, no I/O)

- `planned_intensity(settings) -> float` — the emotional target implied by
  the brain's plan. Matches the shipped Booth chart exactly: `1 - stability`,
  clamped to 0..1. (Style could refine this later; consistency first.)
- `judge_take(measured_energy, target, tolerance=0.25) -> verdict` where
  verdict is `{target, measured, delta, passed, hint}`.
  - `delta = measured - target`; `passed = |delta| <= tolerance`.
  - `hint` is None when passed; otherwise a director's note written to feed
    straight back to the brain: too low -> "came out flatter than directed
    (energy X vs target Y): push the intensity, more heat"; too high ->
    "came out hotter than directed (energy X vs target Y): pull it back,
    calmer, more controlled".
- Tolerance 0.25 default: calibrated against live measurements (a directed
  "STOP IT!" measured energy 0.708 vs implied target ~0.8 — a good take
  should pass with room; a flat 0.3 vs target 0.8 must fail).
- Measured energy comes from the existing `listen.profile` (0..1). The judge
  takes numbers, not audio, so its tests are instant; callers compose
  `profile()` + `judge_take()`.

### 2. The mouth: existing pieces, composed

- Render: `voice_engine.render(...)` as today.
- Re-direct: same composition as `/retake` — the brain re-reads the one line
  with the whole script for arc context and the direction becomes
  `"{direction}. This line: {hint}"`. The judge's hint IS the note.

### 3. The brain: `perform.py` (the loop)

Per line, with `max_takes = 3` and `tolerance = 0.25` (request-overridable):

1. Take 1: render the planned markup. Judge it. Pass -> keep, stop.
2. Take 2 (re-roll): same markup, fresh render (see cache salt below).
   Judge. Pass -> keep, stop.
   - Futility guard: if the re-roll moved |delta| by < 0.03 AND the best
     |delta| is still > 1.5x tolerance, the engine can't get there (e.g.
     Piper has no emotion controls). Keep best, mark `engine_limited`,
     stop — don't spend the third take.
3. Take 3 (re-direct): brain rewrites delivery/settings given the hint;
   render, judge.
4. Keep the best take overall = smallest |delta| (a passed take short-
   circuits earlier). Never error on a miss: ship best + `passed: false`.

Lines run sequentially (rate-limit safe; the report counts renders). After
all lines: stitch kept takes with the existing stitcher (music, captions,
volumes all work unchanged).

### The cache-salt detail

Cue's cache is content-addressed, so a re-roll with identical inputs would
return the identical cached clip — a no-op retry. `Engine.render` gains a
`take: int = 0` that enters the cache key (`|t{take}` segment) only when
non-zero. Take 1 keeps today's keys (all existing cache stays warm); re-rolls
render fresh and are themselves cached and reusable by the stitcher.

## API

`POST /perform`

```json
{
  "script": "NORA: You kept the letter.\n...",
  "direction": "build from calm to furious",
  "cast": {"NORA": "voice_id", "ELI": "local:abc..."},
  "voice": "narrator_voice_id",
  "music": "",
  "max_takes": 3,
  "tolerance": 0.25
}
```

Response:

```json
{
  "audio_id": "<stitched track>", "ext": "mp3", "captions": true,
  "report": {
    "passed_lines": 3, "total_lines": 4, "total_renders": 7,
    "arc_correlation": 0.86,
    "lines": [
      {
        "text": "...", "speaker": "NORA", "target": 0.2, "passed": true,
        "engine_limited": false, "kept_take": 1,
        "takes": [
          {"take": 1, "action": "plan", "audio_id": "...",
           "score": {"target": 0.2, "measured": 0.31, "delta": 0.11,
                      "passed": true, "hint": null}}
        ]
      }
    ]
  }
}
```

`X-ElevenLabs-Key` is honored exactly as in `/render` and `/read`.
`arc_correlation` = Pearson between planned and measured across lines
(reported, never a pass criterion; needs 2+ lines and variance, else null).

## Out of scope (v1)

- Parallel line processing (sequential is rate-limit safe and simple).
- Judging anything beyond energy-vs-intensity (pitch/rate targets later).
- Auto-perform in the writer's room; the studio surface is a single
  "direct until it lands" toggle on the full read, built after the API.

## Slices (one commit each, TDD)

1. `judge.py` + tests (pure scoring).
2. Engine `take` salt + tests (a re-roll really re-renders; take 0 keys
   unchanged).
3. `perform.py` loop + tests with fake engine/brain/ears (escalation order,
   budget, early stop, best-take, futility, engine_limited).
4. `POST /perform` + report + stitch/captions wiring + endpoint tests.
5. Live smoke on the free local engine.
6. Studio toggle.
