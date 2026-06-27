"""Brains — the swappable interpreters that turn a plain-English direction into
voice settings. Same idea as the voice providers: one interface, many backends.

- OllamaBrain: a local LLM (free, offline). Built first.
- GroqBrain: a cloud LLM, added later as the smarter default.

Every brain exposes: a name, and interpret(line, direction) -> {settings, notes}.
The settings are always run through settings.clean(), so a bad LLM answer can
never produce out-of-range values.
"""

import json
import os

import httpx

from direction import interpret as keyword_interpret
from settings import clean, clean_tags, TAG_WHITELIST

# The director brief. Definitions are explicit because the whole point is that
# the model maps a vibe onto these specific dials the way a director would.
SYSTEM_PROMPT = (
    "You are a voice director for an expressive text-to-speech engine. Given a "
    "line and a plain-English performance direction, output ONLY a JSON object "
    "describing how to perform the line.\n\n"
    "Keys:\n"
    "- tags (array of 0-3 strings): audio tags that make the voice ACT out the "
    "tone. THIS is what carries the emotion. Choose ONLY from: "
    + ", ".join(sorted(TAG_WHITELIST))
    + ". Pick the ones that best capture the feeling; use [] if none fit.\n"
    "- stability (0.0-1.0): HIGH = steady, even, controlled. LOW = variable, intense.\n"
    "- style (0.0-1.0): LOW = plain, natural. HIGH = theatrical, stylized.\n"
    "- speed (0.7-1.2): 1.0 = normal, lower = slower, higher = faster.\n"
    "- volume (0.1-1.0): 1.0 = normal, lower for soft/whisper/intimate.\n"
    "- notes (string): a short phrase (max 6 words) describing your reading.\n\n"
    "The tags carry the emotion; the numbers carry energy and pace. "
    "Output only the JSON object, no prose."
)

# Two examples to anchor the format, the tags, and the interpretation.
FEW_SHOT = [
    {"role": "user", "content": 'Line: "Run."\nDirection: frantic and terrified'},
    {
        "role": "assistant",
        "content": '{"tags": ["shouting", "fearful"], "stability": 0.2, "style": 0.8, "speed": 1.2, "volume": 1.0, "notes": "panicked, urgent"}',
    },
    {"role": "user", "content": 'Line: "It is what it is."\nDirection: tired and resigned, flat'},
    {
        "role": "assistant",
        "content": '{"tags": ["tired", "sighs"], "stability": 0.85, "style": 0.2, "speed": 0.9, "volume": 0.85, "notes": "flat, weary"}',
    },
]


def _build_messages(line: str, direction: str) -> list[dict]:
    """The chat the model sees: the director brief, the two anchors, then this
    line + direction. Identical for every LLM brain (Ollama, Groq), so they
    share it."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *FEW_SHOT,
        {"role": "user", "content": f'Line: "{line}"\nDirection: {direction}'},
    ]


def _parse_director_json(content: str) -> dict:
    """Turn an LLM's JSON reply into a safe {settings, tags, notes} dict. The
    reply format is the same regardless of which model produced it, so every LLM
    brain parses through here. Everything goes through the cleaners, so a bad
    answer can't yield out-of-range settings or off-whitelist tags."""
    data = json.loads(content)
    return {
        "settings": clean(data),
        "tags": clean_tags(data.get("tags")),
        "notes": str(data.get("notes", ""))[:80],
    }


class OllamaBrain:
    """Local LLM via Ollama. Free, offline, no quota."""

    name = "ollama"

    def __init__(self, model: str = "qwen2.5:7b", url: str = "http://localhost:11434") -> None:
        self.model = model
        self.url = url

    def interpret(self, line: str, direction: str) -> dict:
        # No direction = neutral read; don't spend an LLM call on it.
        if not direction.strip():
            return {"settings": clean({}), "tags": [], "notes": ""}

        response = httpx.post(
            f"{self.url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "format": "json",  # force valid JSON output
                "messages": _build_messages(line, direction),
            },
            timeout=60.0,
        )
        response.raise_for_status()
        return _parse_director_json(response.json()["message"]["content"])


class GroqBrain:
    """Cloud LLM via Groq's OpenAI-compatible API. Groq runs models on custom
    hardware, so a reply lands in well under a second — that's why it goes first,
    ahead of the slower local Ollama. Needs a free GROQ_API_KEY; if it's missing
    or the call fails, BrainEngine falls back to Ollama, then the keyword brain."""

    name = "groq"

    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        url: str = "https://api.groq.com/openai/v1/chat/completions",
    ) -> None:
        self.model = model
        self.url = url
        # main.py loads .env before constructing the brains, so the key is here.
        self.api_key = os.environ.get("GROQ_API_KEY", "")

    def interpret(self, line: str, direction: str) -> dict:
        # No direction = neutral read; don't spend an API call (or need a key).
        if not direction.strip():
            return {"settings": clean({}), "tags": [], "notes": ""}

        # No key -> raise so BrainEngine moves on to the local Ollama brain.
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY not set")

        response = httpx.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": _build_messages(line, direction),
                "response_format": {"type": "json_object"},  # force valid JSON
                "temperature": 0.7,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return _parse_director_json(response.json()["choices"][0]["message"]["content"])


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
        # The keyword brain can't produce audio tags — it only knows speed/volume.
        return {"settings": cleaned, "tags": [], "notes": notes}


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

        return {"settings": clean({}), "tags": [], "notes": "", "brain": "none"}
