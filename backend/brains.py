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
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from delivery import verify_delivery
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
    "- delivery (string): THE MOST IMPORTANT KEY. The line rewritten as a "
    "performance: the user's words EXACTLY — never add, remove, or change a "
    "word — but with inline audio tags in [brackets] placed at the exact beat "
    "where the emotion lives (not just at the start), plus expressive "
    "punctuation: … for hesitation, — for a break, CAPS for a hit word. "
    "1-3 tags, placed where they belong.\n"
    "- tags (array of 0-4 strings): the tags you used in the delivery.\n"
    "Allowed tags (both keys), ONLY from: "
    + ", ".join(sorted(TAG_WHITELIST))
    + ".\n"
    "- stability (0.0-1.0): LOW (0.0-0.3) = raw, intense, emotional — use it "
    "for strong feelings. HIGH (0.6-0.9) = steady, even, controlled.\n"
    "- style (0.0-1.0): LOW = plain, natural. HIGH = theatrical, stylized.\n"
    "- speed (0.7-1.2): 1.0 = normal, lower = slower, higher = faster.\n"
    "- volume (0.1-1.0): 1.0 = normal, lower for soft/whisper/intimate.\n"
    "- notes (string): a short phrase (max 6 words) describing your reading.\n\n"
    "The delivery carries the emotion; the numbers carry energy and pace. "
    "Output only the JSON object, no prose."
)

# Two examples to anchor the format, the inline delivery, and the interpretation.
FEW_SHOT = [
    {"role": "user", "content": 'Line: "Run."\nDirection: frantic and terrified'},
    {
        "role": "assistant",
        "content": '{"delivery": "[terrified] RUN!", "tags": ["terrified", "shouting"], "stability": 0.15, "style": 0.8, "speed": 1.2, "volume": 1.0, "notes": "panicked, urgent"}',
    },
    {"role": "user", "content": 'Line: "It is what it is."\nDirection: tired and resigned, flat'},
    {
        "role": "assistant",
        "content": '{"delivery": "[sighs] It is… what it is.", "tags": ["sighs", "tired"], "stability": 0.8, "style": 0.2, "speed": 0.9, "volume": 0.85, "notes": "flat, weary"}',
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


class RateLimited(RuntimeError):
    """A provider's rate window is exhausted (final 429 after waiting it out).
    Typed so orchestration can tell 'the window is empty, stop asking' from
    'this brain is broken, try the next'."""


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


def _clean_plan(data: dict, line: str | None) -> dict:
    """One raw LLM plan into a safe {settings, tags, notes, delivery} dict.
    Everything goes through the cleaners — and the delivery through
    verify_delivery against the original line — so a bad answer can't yield
    out-of-range settings, off-whitelist tags, or a delivery that changes the
    user's words."""
    raw_delivery = str(data.get("delivery") or "")
    return {
        "settings": clean(data),
        "tags": clean_tags(data.get("tags")),
        "notes": str(data.get("notes", ""))[:80],
        "delivery": verify_delivery(line, raw_delivery) if line else None,
    }


def _parse_director_json(content: str, line: str | None = None) -> dict:
    """Turn an LLM's single-line JSON reply into a safe plan. The reply format
    is the same regardless of which model produced it, so every LLM brain
    parses through here."""
    return _clean_plan(json.loads(content), line)


# Long scripts go to the brain in batches. The per-line path sends the whole
# script with EVERY line's call — O(n^2) tokens, which trips Groq's free-tier
# limits somewhere around 40-60 lines. Past the threshold, one call plans
# BATCH_SIZE lines at once with a windowed excerpt for continuity and the
# script's total length for arc position: O(n) tokens, 10x fewer calls.
BATCH_THRESHOLD = 40  # up to this many lines, the per-line path (best quality)
BATCH_SIZE = 10  # lines planned per LLM call in batch mode
BATCH_WINDOW = 5  # neighbor lines shown around a batch for continuity


def _build_batch_messages(
    lines: list[str],
    direction: str,
    start: int,
    count: int,
    hints: list[str | None] | None = None,
) -> list[dict]:
    """The chat for one batch: the director brief, then ONE windowed excerpt
    with the lines to perform marked ">" (each with its own hint folded in).
    Deliberately lean — no few-shot anchors, no line listed twice — because
    the free tier meters tokens per minute and every batch call pays this
    prompt again. The model answers with a "plans" array."""
    total = len(lines)
    end = min(start + count, total)
    lo = max(0, start - BATCH_WINDOW)
    hi = min(total, end + BATCH_WINDOW)

    def hint_for(i: int) -> str:
        hint = hints[i] if hints and i < len(hints) else None
        return f" (note for this line: {hint})" if hint else ""

    excerpt = "\n".join(
        f"{i + 1}. {'> ' if start <= i < end else ''}{lines[i]}{hint_for(i) if start <= i < end else ''}"
        for i in range(lo, hi)
    )
    user = (
        f"A script of {total} lines is performed under one direction. Excerpt "
        f"(lines {lo + 1}-{hi}), with the lines to perform marked \">\":\n{excerpt}\n\n"
        f"Direction (applies to the whole script): {direction}\n\n"
        f"Perform the marked lines {start + 1}-{end}. Output ONLY a JSON object "
        'of the form {"plans": [...]}: EXACTLY one plan object per marked line, '
        f"in order ({end - start} plans), each with the keys described above. "
        "Judge every line's delivery from where it sits in the whole script's arc."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _parse_batch_json(content: str, batch_lines: list[str]) -> list[dict]:
    """Turn a batched reply into one safe plan per line. The count must match
    exactly — a model that dropped or invented a line poisons every position
    after it, so the caller falls back rather than guess the alignment."""
    plans = json.loads(content).get("plans")
    if not isinstance(plans, list) or len(plans) != len(batch_lines):
        raise ValueError("batch reply did not match the batch")
    return [
        _clean_plan(plan if isinstance(plan, dict) else {}, line)
        for plan, line in zip(plans, batch_lines)
    ]


class OllamaBrain:
    """Local LLM via Ollama. Free, offline, no quota."""

    name = "ollama"

    def __init__(self, model: str = "qwen2.5:7b", url: str = "http://localhost:11434") -> None:
        self.model = model
        self.url = url

    def ready(self) -> bool:
        """Is the local Ollama server answering? A quick local ping, nothing
        loaded, nothing spent."""
        try:
            return httpx.get(f"{self.url}/api/tags", timeout=1.5).status_code == 200
        except Exception:
            return False

    def interpret(
        self, line: str, direction: str, script: list[str] | None = None, index: int = 0
    ) -> dict:
        # No direction = neutral read; don't spend an LLM call on it.
        if not direction.strip():
            return {"settings": clean({}), "tags": [], "notes": "", "delivery": None}

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
        return _parse_director_json(response.json()["message"]["content"], line)

    def interpret_batch(
        self,
        batch: list[str],
        direction: str,
        script: list[str] | None = None,
        start: int = 0,
        hints: list[str | None] | None = None,
    ) -> list[dict]:
        """Plan a whole batch of lines in one call (long-script mode)."""
        if not direction.strip():
            return [{"settings": clean({}), "tags": [], "notes": "", "delivery": None} for _ in batch]
        response = httpx.post(
            f"{self.url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "format": "json",
                "messages": _build_batch_messages(script or batch, direction, start, len(batch), hints),
            },
            timeout=120.0,  # ten plans is a long answer for a local model
        )
        response.raise_for_status()
        return _parse_batch_json(response.json()["message"]["content"], batch)

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

    def ready(self) -> bool:
        """A key is configured. Deliberately not a live call: /status must
        never spend quota."""
        return bool(self.api_key)

    def _post(self, payload: dict, timeout: float) -> httpx.Response:
        """POST to Groq, waiting out one short 429. The free tier meters
        tokens per minute AND per day, and Retry-After tells which wall this
        is: a few seconds means the minute window (worth sleeping out — the
        server's number is exact), hundreds of seconds means the daily cap
        (live-observed 900-1026s; no user waits that out, hand off to the
        fallback chain immediately). Exactly one wait per call: more
        compounds catastrophically when a failed batch falls back to ten
        per-line calls (live-observed as a multi-minute hang). Any other
        error fails fast: a 500 is not a rate window."""
        for attempt in range(2):
            response = httpx.post(
                self.url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=timeout,
            )
            if response.status_code != 429:
                response.raise_for_status()
                return response
            if attempt == 1:
                break
            try:
                delay = float(response.headers.get("retry-after", ""))
            except ValueError:
                delay = 3.0  # transient 429 with no hint: brief pause
            if delay > 60.0:
                break  # the daily wall, not the minute window
            time.sleep(delay)
        raise RateLimited("groq rate window exhausted")

    def interpret(
        self, line: str, direction: str, script: list[str] | None = None, index: int = 0
    ) -> dict:
        # No direction = neutral read; don't spend an API call (or need a key).
        if not direction.strip():
            return {"settings": clean({}), "tags": [], "notes": "", "delivery": None}

        # No key -> raise so BrainEngine moves on to the local Ollama brain.
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY not set")

        response = self._post(
            {
                "model": self.model,
                "messages": _build_messages(line, direction, script, index),
                "response_format": {"type": "json_object"},  # force valid JSON
                "temperature": 0.7,
            },
            timeout=30.0,
        )
        return _parse_director_json(response.json()["choices"][0]["message"]["content"], line)

    def interpret_batch(
        self,
        batch: list[str],
        direction: str,
        script: list[str] | None = None,
        start: int = 0,
        hints: list[str | None] | None = None,
    ) -> list[dict]:
        """Plan a whole batch of lines in one call (long-script mode)."""
        if not direction.strip():
            return [{"settings": clean({}), "tags": [], "notes": "", "delivery": None} for _ in batch]
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY not set")
        response = self._post(
            {
                "model": self.model,
                "messages": _build_batch_messages(script or batch, direction, start, len(batch), hints),
                "response_format": {"type": "json_object"},
                "temperature": 0.7,
            },
            timeout=60.0,
        )
        return _parse_batch_json(response.json()["choices"][0]["message"]["content"], batch)

    def chat(self, messages: list[dict]) -> dict:
        """One writer's-room turn: full chat history in, {message, script} out."""
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY not set")
        response = self._post(
            {
                "model": self.model,
                "messages": _writer_messages(messages),
                "response_format": {"type": "json_object"},
                "temperature": 0.9,  # writing wants more spark than directing
            },
            timeout=30.0,
        )
        return _parse_writer_json(response.json()["choices"][0]["message"]["content"])


class KeywordBrain:
    """The Step 2 keyword matcher, as the deterministic final fallback. Needs no
    network or model, so it never fails — but it only knows speed and volume,
    leaving stability/style neutral."""

    name = "keyword"

    def ready(self) -> bool:
        return True  # no network, no model: it cannot be down

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
        return {"settings": cleaned, "tags": [], "notes": notes, "delivery": None}


class BrainEngine:
    """Tries each brain in order (cloud, then local, then keyword), falling back
    on any failure. If somehow all fail, returns a neutral read rather than
    erroring — the line should always be speakable."""

    def __init__(self, brains: list) -> None:
        self.brains = brains

    def status(self) -> list[dict]:
        """Each brain's own cheap self-check, in fallback-chain order."""
        return [{"name": brain.name, "ready": brain.ready()} for brain in self.brains]

    def interpret(
        self,
        line: str,
        direction: str,
        script: list[str] | None = None,
        index: int = 0,
        _skip: frozenset = frozenset(),
    ) -> dict:
        for brain in self.brains:
            if brain.name in _skip:
                continue  # its rate window is known-empty; don't hammer it
            try:
                result = brain.interpret(line, direction, script=script, index=index)
            except Exception:
                continue  # this brain is down — try the next
            return {**result, "brain": brain.name}

        return {"settings": clean({}), "tags": [], "notes": "", "delivery": None, "brain": "none"}

    def interpret_script(
        self, lines: list[str], direction: str, hints: list[str | None] | None = None
    ) -> list[dict]:
        """Restyle a whole script under one direction.

        Short scripts (up to BATCH_THRESHOLD lines): each line is interpreted
        with the full script passed in as context, so the brain can read the
        arc — the highest-quality path, concurrent across a few workers.

        Long scripts: batch mode. One call plans BATCH_SIZE lines at once (a
        windowed excerpt keeps continuity, the total length gives arc
        position), so a 100-line script costs 10 calls instead of 100 calls
        each carrying all 100 lines. A failed batch falls back per line with
        a windowed context, so a bad chunk can't sink the read.

        `hints` carries optional per-line direction (a screenplay
        parenthetical like `(quietly)`): folded into that one line only."""

        def line_direction(index: int) -> str:
            hint = hints[index] if hints and index < len(hints) else None
            if not hint:
                return direction
            return f"{direction}. This line: {hint}" if direction else f"This line: {hint}"

        if len(lines) <= BATCH_THRESHOLD:
            with ThreadPoolExecutor(max_workers=4) as pool:
                return list(
                    pool.map(
                        lambda pair: self.interpret(
                            pair[1], line_direction(pair[0]), script=lines, index=pair[0]
                        ),
                        enumerate(lines),
                    )
                )

        def plan_chunk(start: int) -> list[dict]:
            batch = lines[start : start + BATCH_SIZE]
            rate_limited: set[str] = set()
            for brain in self.brains:
                if not hasattr(brain, "interpret_batch"):
                    continue
                try:
                    plans = brain.interpret_batch(
                        batch, direction, script=lines, start=start, hints=hints
                    )
                except RateLimited:
                    # The window is empty, not the brain broken. Remember it:
                    # asking it again once per line is pure amplification.
                    rate_limited.add(brain.name)
                    continue
                except Exception:
                    continue  # this brain couldn't do the batch — try the next
                return [{**plan, "brain": brain.name} for plan in plans]
            # No brain could batch: per line, with a window instead of the
            # whole script (batch mode exists to escape O(n^2); the fallback
            # must not sneak it back in).
            fallback = []
            for offset, line in enumerate(batch):
                index = start + offset
                lo = max(0, index - BATCH_WINDOW)
                window = lines[lo : index + BATCH_WINDOW + 1]
                fallback.append(
                    self.interpret(
                        line,
                        line_direction(index),
                        script=window,
                        index=index - lo,
                        _skip=frozenset(rate_limited),
                    )
                )
            return fallback

        # Sequential on purpose: batch calls are ~10x the tokens of a
        # single-line call and the free tier meters tokens PER MINUTE, so
        # spreading the calls over real time is what makes them all land.
        # Parallel batches just burn the window faster and 429 each other.
        return [
            plan
            for start in range(0, len(lines), BATCH_SIZE)
            for plan in plan_chunk(start)
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
