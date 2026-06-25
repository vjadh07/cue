"""The direction interpreter — Cue's 'brain' for Step 2.

Turns a plain-English note ("warm and slow") into settings for the browser
voice (speed, pitch, volume). This is deliberately pure logic: no web, no AI.
It scans the note for known keywords, nudges the relevant knob for each match,
and clamps the result to a safe range. In Step 4 an AI can replace or feed this.
"""

import re

# The voice starts neutral; matched keywords push these values up or down.
NEUTRAL = {"speed": 1.0, "pitch": 1.0, "volume": 1.0}

# Each keyword nudges one knob by a fixed amount. Synonyms share an effect.
# Browser volume maxes at 1.0 (the default), so only words that *lower* volume
# do anything audible — loudness gets real control with ElevenLabs in Step 3.
KEYWORDS: dict[str, tuple[str, float]] = {
    # Speed (how fast the line is read)
    "slow": ("speed", -0.3),
    "slowly": ("speed", -0.3),
    "calm": ("speed", -0.3),
    "relaxed": ("speed", -0.3),
    "fast": ("speed", +0.4),
    "quick": ("speed", +0.4),
    "quickly": ("speed", +0.4),
    "urgent": ("speed", +0.4),
    # Pitch (how high or low the voice sits)
    "warm": ("pitch", -0.25),
    "deep": ("pitch", -0.25),
    "low": ("pitch", -0.25),
    "bright": ("pitch", +0.25),
    "excited": ("pitch", +0.25),
    "cheerful": ("pitch", +0.25),
    # Volume (only downward is audible in the browser)
    "soft": ("volume", -0.3),
    "gentle": ("volume", -0.3),
    "quiet": ("volume", -0.3),
    "whisper": ("volume", -0.6),
}

# Safe bounds so a stack of keywords can't produce a broken or silent voice.
CLAMPS = {
    "speed": (0.5, 2.0),
    "pitch": (0.5, 1.8),
    "volume": (0.1, 1.0),
}


def interpret(direction: str) -> dict:
    """Read a plain-English direction and return voice settings + matched words.

    Returns: {"settings": {"speed", "pitch", "volume"}, "matched": [words]}
    """
    settings = dict(NEUTRAL)
    matched: list[str] = []

    # Pull out lowercase word tokens, ignoring punctuation and spacing.
    for token in re.findall(r"[a-z]+", direction.lower()):
        if token in KEYWORDS:
            knob, delta = KEYWORDS[token]
            settings[knob] += delta
            matched.append(token)

    # Keep every knob inside its safe range, and round off float noise.
    for knob, (low, high) in CLAMPS.items():
        settings[knob] = round(min(max(settings[knob], low), high), 2)

    return {"settings": settings, "matched": matched}
