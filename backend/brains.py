"""Brains — the swappable interpreters that turn a plain-English direction into
voice settings. Same idea as the voice providers: one interface, many backends.

- OllamaBrain: a local LLM (free, offline). Built first.
- GroqBrain: a cloud LLM, added later as the smarter default.

Every brain exposes: a name, and interpret(line, direction) -> {settings, notes}.
The settings are always run through settings.clean(), so a bad LLM answer can
never produce out-of-range values.
"""

import json

import httpx

from direction import interpret as keyword_interpret
from settings import clean

# The director brief. Definitions are explicit because the whole point is that
# the model maps a vibe onto these specific dials the way a director would.
SYSTEM_PROMPT = (
    "You are a voice director for a text-to-speech engine. Given a line and a "
    "plain-English performance direction, output ONLY a JSON object describing "
    "how to perform the line.\n\n"
    "Keys:\n"
    "- stability (0.0-1.0): HIGH = steady, even, flat, controlled. "
    "LOW = emotional, variable, intense.\n"
    "- style (0.0-1.0): LOW = plain, natural, understated. "
    "HIGH = theatrical, characterful, stylized.\n"
    "- speed (0.7-1.2): 1.0 = normal, lower = slower, higher = faster.\n"
    "- volume (0.1-1.0): 1.0 = normal, lower for soft/whisper/intimate.\n"
    "- notes (string): a short phrase (max 6 words) describing your reading.\n\n"
    "Guidance: calm/tired/resigned/flat/deadpan -> higher stability, lower style. "
    "excited/dramatic/panicked/emotional -> lower stability, higher style. "
    "whisper/soft/intimate -> lower volume. urgent -> faster, gentle -> slower.\n"
    "Output only the JSON object, no prose."
)

# Two examples to anchor both the format and the interpretation.
FEW_SHOT = [
    {"role": "user", "content": 'Line: "Run."\nDirection: frantic and terrified'},
    {
        "role": "assistant",
        "content": '{"stability": 0.2, "style": 0.75, "speed": 1.2, "volume": 1.0, "notes": "fast, panicked"}',
    },
    {"role": "user", "content": 'Line: "It is what it is."\nDirection: tired and resigned, flat'},
    {
        "role": "assistant",
        "content": '{"stability": 0.85, "style": 0.2, "speed": 0.9, "volume": 0.85, "notes": "flat, weary"}',
    },
]


class OllamaBrain:
    """Local LLM via Ollama. Free, offline, no quota."""

    name = "ollama"

    def __init__(self, model: str = "qwen2.5:7b", url: str = "http://localhost:11434") -> None:
        self.model = model
        self.url = url

    def interpret(self, line: str, direction: str) -> dict:
        # No direction = neutral read; don't spend an LLM call on it.
        if not direction.strip():
            return {"settings": clean({}), "notes": ""}

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *FEW_SHOT,
            {"role": "user", "content": f'Line: "{line}"\nDirection: {direction}'},
        ]
        response = httpx.post(
            f"{self.url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "format": "json",  # force valid JSON output
                "messages": messages,
            },
            timeout=60.0,
        )
        response.raise_for_status()

        data = json.loads(response.json()["message"]["content"])
        notes = str(data.get("notes", ""))[:80]
        return {"settings": clean(data), "notes": notes}


class KeywordBrain:
    """The Step 2 keyword matcher, as the deterministic final fallback. Needs no
    network or model, so it never fails — but it only knows speed and volume,
    leaving stability/style neutral."""

    name = "keyword"

    def interpret(self, line: str, direction: str) -> dict:
        result = keyword_interpret(direction)
        cleaned = clean(
            {
                "speed": result["settings"]["speed"],
                "volume": result["settings"]["volume"],
            }
        )
        matched = result["matched"]
        notes = "matched: " + ", ".join(matched) if matched else ""
        return {"settings": cleaned, "notes": notes}


class BrainEngine:
    """Tries each brain in order (cloud, then local, then keyword), falling back
    on any failure. If somehow all fail, returns a neutral read rather than
    erroring — the line should always be speakable."""

    def __init__(self, brains: list) -> None:
        self.brains = brains

    def interpret(self, line: str, direction: str) -> dict:
        for brain in self.brains:
            try:
                result = brain.interpret(line, direction)
            except Exception:
                continue  # this brain is down — try the next
            return {**result, "brain": brain.name}

        return {"settings": clean({}), "notes": "", "brain": "none"}
