"""Fountain screenplay import — the parser behind "instant table read".

Fountain (fountain.io) is the plain-text screenplay format every serious
screenwriting tool can export (Highland, WriterDuet, Final Draft). This module
turns a .fountain document into Cue's native script format so a writer can
paste a real draft and hear it performed.

The parts of the spec that actually bite, all handled here:
- character extensions — DEV, DEV (V.O.) and DEV (CONT'D) are ONE character
- parentheticals — `(quietly)` under a cue is direction, never spoken
- notes [[...]] and boneyard /* ... */ must vanish entirely
- forced elements — `.INSERT` is a scene, `@McCLANE` is a character, `>` is
  a transition, `> centered <` is action
- an all-caps line is only a character cue if dialogue actually follows it

Deliberately out of scope (parsed gracefully, not specially rendered): dual
dialogue plays sequentially, FDX/PDF import, in-app screenplay editing."""

import re

# Comments-to-the-crew that must never reach the voice.
_BONEYARD_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_NOTE_RE = re.compile(r"\[\[.*?\]\]", re.DOTALL)

# *emphasis* and _underline_ style the page, not the speech.
_EMPHASIS_RE = re.compile(r"[*_]")

_TITLE_KEY_RE = re.compile(
    r"(?i)^(title|credit|author|authors|source|draft date|contact|copyright|notes|revision)\s*:"
)
_SCENE_RE = re.compile(r"(?i)^(INT|EXT|EST|INT\.?/EXT|I/E)[.\s]")
_TRANSITION_RE = re.compile(r"^[A-Z0-9 .'\-]+TO:$")

# What Cue's own `NAME: line` parser allows in a name (no periods, no commas).
_UNSAFE_NAME_RE = re.compile(r"[^\w '\-]")


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", _EMPHASIS_RE.sub("", text)).strip()


def _is_all_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def _cue_speaker(line: str) -> str | None:
    """The character name if this line is a character cue, else None. Handles
    extensions (`DEV (V.O.)`), the dual-dialogue marker (`MAYA ^`), and forced
    mixed-case cues (`@McCLANE`)."""
    forced = line.startswith("@")
    core = line[1:] if forced else line
    name = re.sub(r"\([^)]*\)", "", core).replace("^", "").strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        return None
    if not forced and not _is_all_caps(name):
        return None
    return name


def parse_fountain(text: str) -> dict:
    """Parse a Fountain document into {"title", "elements"}. Each element is
    {"type": "scene" | "action" | "dialogue", "speaker", "text", "hint"} —
    speaker and hint are None except on dialogue."""
    text = _BONEYARD_RE.sub("", text)
    text = _NOTE_RE.sub("", text)
    lines = [line.strip() for line in text.splitlines()]

    title = None
    i = 0

    # Title page: a leading block of `Key: value` pairs, ended by a blank line.
    if lines and lines[0] and _TITLE_KEY_RE.match(lines[0]):
        while i < len(lines) and lines[i]:
            match = _TITLE_KEY_RE.match(lines[i])
            if match and match.group(1).lower() == "title":
                title = _clean_text(lines[i].split(":", 1)[1]) or None
            i += 1

    elements: list[dict] = []
    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue
        prev_blank = i == 0 or not lines[i - 1]

        # Scene headings (INT./EXT. or forced with a leading dot).
        if _SCENE_RE.match(line):
            elements.append({"type": "scene", "speaker": None, "text": _clean_text(line), "hint": None})
            i += 1
            continue
        if line.startswith(".") and len(line) > 1 and line[1].isalnum():
            elements.append(
                {"type": "scene", "speaker": None, "text": _clean_text(line[1:]), "hint": None}
            )
            i += 1
            continue

        # Structure that is read by nobody: sections (#), synopses / page
        # breaks (=), and transitions (CUT TO: or a forced >).
        if line.startswith("#") or line.startswith("="):
            i += 1
            continue
        if line.startswith(">") and line.endswith("<"):
            # Centered text is action, minus its markers.
            centered = _clean_text(line[1:-1])
            if centered:
                elements.append({"type": "action", "speaker": None, "text": centered, "hint": None})
            i += 1
            continue
        if line.startswith(">") or (_TRANSITION_RE.match(line) and prev_blank):
            i += 1
            continue

        # Character cue: after a blank line, with dialogue right under it.
        speaker = _cue_speaker(line) if prev_blank else None
        if speaker and i + 1 < len(lines) and lines[i + 1]:
            hints: list[str] = []
            spoken: list[str] = []
            j = i + 1
            while j < len(lines) and lines[j]:
                block_line = lines[j]
                if block_line.startswith("(") and block_line.endswith(")"):
                    hint = _clean_text(block_line[1:-1])
                    if hint:
                        hints.append(hint)
                else:
                    # A ~lyric line is sung dialogue; drop only the marker.
                    spoken.append(block_line[1:] if block_line.startswith("~") else block_line)
                j += 1
            dialogue_text = _clean_text(" ".join(spoken))
            if dialogue_text:
                elements.append(
                    {
                        "type": "dialogue",
                        "speaker": speaker,
                        "text": dialogue_text,
                        "hint": "; ".join(hints) or None,
                    }
                )
            i = j
            continue

        # Everything else: an action block — consecutive lines, one paragraph.
        block: list[str] = []
        j = i
        while j < len(lines) and lines[j]:
            block.append(lines[j])
            j += 1
        action_text = _clean_text(" ".join(block))
        if action_text:
            elements.append({"type": "action", "speaker": None, "text": action_text, "hint": None})
        i = j

    return {"title": title, "elements": elements}


def characters(parsed: dict) -> list[str]:
    """The distinct speaking characters, in first-appearance order. Extensions
    were already stripped by the parser, so DEV (V.O.) has merged into DEV."""
    seen: list[str] = []
    for element in parsed["elements"]:
        name = element["speaker"]
        if name and name not in seen:
            seen.append(name)
    return seen


def _safe_name(name: str) -> str:
    """A speaker name Cue's own `NAME: line` parser will accept: no periods or
    other punctuation outside [word ' -], at most 20 characters."""
    return re.sub(r"\s+", " ", _UNSAFE_NAME_RE.sub("", name)).strip()[:20].strip()


def to_cue_script(parsed: dict, include_action: bool = False) -> str:
    """Convert parsed elements into Cue's native script text: dialogue becomes
    `NAME: line` (or `NAME (hint): line` carrying the parenthetical as a
    per-line direction), and, when asked, action and scene headings become
    unlabeled narrator lines."""
    out: list[str] = []
    for element in parsed["elements"]:
        if element["type"] == "dialogue":
            name = _safe_name(element["speaker"])
            if not name:
                continue
            if element["hint"]:
                out.append(f"{name} ({element['hint']}): {element['text']}")
            else:
                out.append(f"{name}: {element['text']}")
        elif include_action:
            out.append(element["text"])
    return "\n".join(out)
