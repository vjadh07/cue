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
from script import clean_generated
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


# The writer's-room brief: a conversational screenwriter (the reverse of
# directing — here the brain writes the material, the user then directs it).
# Replies are structured JSON so the app can tell chat from material.
WRITER_PROMPT = (
    "You are the writer's-room assistant for Cue, a voice-direction tool. The "
    "user chats with you to develop a short script to be performed aloud; you "
    "draft and revise it as the conversation goes.\n\n"
    "Always reply with ONLY a JSON object with two keys:\n"
    '- "message": one or two conversational sentences (what you did, or a '
    "question if you genuinely need an answer before writing).\n"
    '- "script": the complete current draft whenever you write or revise '
    "material, else null. Always the FULL script, not a diff.\n\n"
    "Script rules:\n"
    "- 4-10 short lines, each on its own row.\n"
    "- Dialogue lines are written `NAME: line` (short uppercase names).\n"
    "- Narration lines are plain text with no label.\n"
    "- No stage directions, headings, markdown, numbering, or surrounding quotes.\n"
    "- Every line must be speakable and emotionally distinct, with an arc."
)


def _writer_messages(messages: list[dict]) -> list[dict]:
    return [{"role": "system", "content": WRITER_PROMPT}, *messages]


def _parse_writer_json(content: str) -> dict:
    """Turn the writer's JSON reply into {message, script|None}. The script goes
    through clean_generated like any generated material, so markdown or an
    over-long draft can't reach the Script box."""
    data = json.loads(content)
    script = clean_generated(str(data.get("script") or ""))
    return {
        "message": str(data.get("message", ""))[:400],
        "script": script or None,
    }


def _build_messages(
    line: str, direction: str, script: list[str] | None = None, index: int = 0
) -> list[dict]:
    """The chat the model sees: the director brief, the two anchors, then the
    line to perform. Shared by every LLM brain (Ollama, Groq).

    With no `script`, it's a single line on its own. With a `script` (the whole
    list of lines) it shows the model the full script and marks which line to
    perform, so one direction can ramp across the arc instead of hitting every
    line the same."""
    if script:
        numbered = "\n".join(f"{i + 1}. {text}" for i, text in enumerate(script))
        user = (
            f"Full script for context:\n{numbered}\n\n"
            f"Direction (applies to the whole script): {direction}\n\n"
            f'Now perform line {index + 1}: "{line}"\n'
            "Output the JSON for THIS line only, judging its delivery from where "
            "it sits in the script's arc."
        )
    else:
        user = f'Line: "{line}"\nDirection: {direction}'
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *FEW_SHOT,
        {"role": "user", "content": user},
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

    def interpret(
        self, line: str, direction: str, script: list[str] | None = None, index: int = 0
    ) -> dict:
        # No direction = neutral read; don't spend an LLM call on it.
        if not direction.strip():
            return {"settings": clean({}), "tags": [], "notes": ""}

        response = httpx.post(
            f"{self.url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "format": "json",  # force valid JSON output
                "messages": _build_messages(line, direction, script, index),
            },
            timeout=60.0,
        )
        response.raise_for_status()
        return _parse_director_json(response.json()["message"]["content"])

    def chat(self, messages: list[dict]) -> dict:
        """One writer's-room turn: full chat history in, {message, script} out."""
        response = httpx.post(
            f"{self.url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "format": "json",
                "messages": _writer_messages(messages),
            },
            timeout=60.0,
        )
        response.raise_for_status()
        return _parse_writer_json(response.json()["message"]["content"])


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

    def interpret(
        self, line: str, direction: str, script: list[str] | None = None, index: int = 0
    ) -> dict:
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
                "messages": _build_messages(line, direction, script, index),
                "response_format": {"type": "json_object"},  # force valid JSON
                "temperature": 0.7,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return _parse_director_json(response.json()["choices"][0]["message"]["content"])

    def chat(self, messages: list[dict]) -> dict:
        """One writer's-room turn: full chat history in, {message, script} out."""
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY not set")
        response = httpx.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": _writer_messages(messages),
                "response_format": {"type": "json_object"},
                "temperature": 0.9,  # writing wants more spark than directing
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return _parse_writer_json(response.json()["choices"][0]["message"]["content"])


class KeywordBrain:
    """The Step 2 keyword matcher, as the deterministic final fallback. Needs no
    network or model, so it never fails — but it only knows speed and volume,
    leaving stability/style neutral."""

    name = "keyword"

    def interpret(
        self, line: str, direction: str, script: list[str] | None = None, index: int = 0
    ) -> dict:
        # Keyword matching is per-line only — it can't use the script's arc, so
        # script/index are accepted (to match the interface) but ignored.
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

    def interpret(
        self, line: str, direction: str, script: list[str] | None = None, index: int = 0
    ) -> dict:
        for brain in self.brains:
            try:
                result = brain.interpret(line, direction, script=script, index=index)
            except Exception:
                continue  # this brain is down — try the next
            return {**result, "brain": brain.name}

        return {"settings": clean({}), "tags": [], "notes": "", "brain": "none"}

    def interpret_script(self, lines: list[str], direction: str) -> list[dict]:
        """Restyle a whole script under one direction. Each line is interpreted
        with the full script passed in as context, so the brain can read the arc
        (a line's place in the script) — not just the line alone. Fallback still
        happens per line, so one slow/failing line can't sink the rest."""
        return [
            self.interpret(line, direction, script=lines, index=i)
            for i, line in enumerate(lines)
        ]

    def chat(self, messages: list[dict]) -> dict:
        """One writer's-room turn. Only LLM brains can write (the keyword
        matcher has no chat), so unlike interpret there's no safe neutral
        answer — if every writer fails, that's an error the caller must surface."""
        for brain in self.brains:
            if not hasattr(brain, "chat"):
                continue
            try:
                return brain.chat(messages)
            except Exception:
                continue  # this writer is down — try the next
        raise RuntimeError("no brain available to write a script")
