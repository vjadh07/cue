"""Voice settings schema + the clean() safety net.

A 'brain' (LLM or the keyword fallback) proposes settings, but we never trust
them blindly: clean() coerces, clamps, defaults, and rounds so anything weird
(a hallucinated number, a string, a missing key) becomes a safe value before it
reaches the voice engine.

- stability: 0..1   low = emotional/variable, high = steady/flat
- style:     0..1   low = plain,              high = exaggerated/performed
- speed:     0.7..1.2 (ElevenLabs' supported window)
- volume:    0.1..1.0 (applied at playback)
"""

DEFAULTS = {"stability": 0.5, "style": 0.3, "speed": 1.0, "volume": 1.0}

RANGES = {
    "stability": (0.0, 1.0),
    "style": (0.0, 1.0),
    "speed": (0.7, 1.2),
    "volume": (0.1, 1.0),
}


def clean(raw: dict) -> dict:
    """Return a valid settings dict no matter what `raw` contains."""
    result = {}
    for key, (low, high) in RANGES.items():
        value = raw.get(key)
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = DEFAULTS[key]  # missing or non-numeric -> default
        result[key] = round(min(high, max(low, number)), 2)
    return result
