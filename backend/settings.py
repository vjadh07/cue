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


# ElevenLabs v3 audio tags the brain is allowed to use. A whitelist matters: it
# stops the model from emitting arbitrary text that v3 would otherwise read out
# loud as if it were part of the line. Deliberately wide — the tags ARE the
# emotional range — but every entry is a known v3 delivery/emotion cue.
TAG_WHITELIST = {
    # laughter
    "laughs", "laughs harder", "giggles", "chuckles", "snorts",
    # breath
    "sighs", "exhales", "inhales", "gasps", "breathless",
    # quiet
    "whispers", "whispering", "under breath", "muttering", "soft",
    # loud
    "shouting", "yelling", "screaming",
    # breaking
    "crying", "sobbing", "voice breaking", "choked up", "trembling",
    # timing
    "pause", "long pause", "rushed", "drawn out", "slowly", "hesitant",
    # dry
    "sarcastic", "deadpan", "dry", "mocking", "smug",
    # wonder
    "awe", "amazed", "surprised", "shocked", "curious",
    # heat
    "angry", "furious", "frustrated", "annoyed", "irritated",
    # fear
    "nervous", "anxious", "fearful", "terrified", "panicked",
    # light
    "cheerful", "excited", "elated", "happy", "delighted", "playful",
    "teasing", "hopeful", "proud", "relieved", "confident",
    # heavy
    "tired", "weary", "exhausted", "bored", "sad", "sorrowful", "somber",
    "disappointed", "dejected", "embarrassed",
    # tone
    "serious", "grave", "stern", "warm", "warmly", "gently", "soothing",
    "tender", "calm", "cold", "coldly", "menacing", "threatening", "sinister",
    "dramatic", "urgent", "pleading", "desperate",
}

MAX_TAGS = 4


def clean_tags(raw, max_tags: int = MAX_TAGS) -> list[str]:
    """Keep only known tags, normalized and de-duplicated, capped to max_tags."""
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        tag = item.strip().lower().strip("[]").strip()
        if tag in TAG_WHITELIST and tag not in result:
            result.append(tag)
        if len(result) >= max_tags:
            break
    return result
