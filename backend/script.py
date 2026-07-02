"""Script helpers — turning a pasted block of text into the lines the brain will
restyle. Kept tiny and pure so it's easy to test and reason about.

A script can be a plain read (no labels = one voice) or a conversation, where a
line is written `SPEAKER: text` and each speaker gets their own voice."""

import re

# A speaker label: a short name at the very start, then a colon and a space, then
# the line. Requiring colon+space (and disallowing sentence punctuation in the
# name) keeps things like "Wait, it's 3:00" or "ratio 16:9" from looking like a
# speaker. Names may have letters/digits/spaces/apostrophes/hyphens, up to ~20 chars.
_SPEAKER_RE = re.compile(r"^([\w '\-]{1,20}):\s+(.+)$")


def split_lines(block: str) -> list[str]:
    """Split a pasted script into clean lines: one per line break, trimmed, with
    blank / whitespace-only lines dropped. (CRLF and CR endings are handled.)"""
    return [line.strip() for line in block.splitlines() if line.strip()]


def parse_script(block: str) -> list[dict]:
    """Turn a script block into speaker-attributed lines: one {speaker, text} per
    line. A line written `NAME: text` gets that speaker; any other line has
    speaker None (the default/narrator voice)."""
    result = []
    for line in split_lines(block):
        match = _SPEAKER_RE.match(line)
        if match:
            result.append({"speaker": match.group(1).strip(), "text": match.group(2).strip()})
        else:
            result.append({"speaker": None, "text": line})
    return result


MAX_GENERATED_LINES = 12

# Decoration LLMs sneak into "plain text": leading list numbers/bullets.
_NUMBERING_RE = re.compile(r"^(\d+[.)]|[-*•])\s+")


def clean_generated(raw: str) -> str:
    """Sanitize an LLM-written script into plain performable lines: no markdown
    fences, headings, numbering, or blank rows — and never longer than
    MAX_GENERATED_LINES, however chatty the model felt."""
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("```"):
            continue
        if line.startswith("#") or (line.startswith("**") and line.endswith("**")):
            continue  # a heading, not a spoken line
        lines.append(_NUMBERING_RE.sub("", line))
    return "\n".join(lines[:MAX_GENERATED_LINES])


def speakers(parsed: list[dict]) -> list[str]:
    """The distinct named speakers, in first-seen order — what the UI needs to
    ask which voice each character should use. Unlabeled (None) lines are not
    speakers."""
    seen = []
    for line in parsed:
        name = line["speaker"]
        if name and name not in seen:
            seen.append(name)
    return seen
