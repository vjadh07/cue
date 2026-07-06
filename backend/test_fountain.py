"""Tests for the Fountain screenplay importer — the parser that turns a real
.fountain screenplay into Cue's native script format, so a screenwriter can
paste a draft and hear a table read. Covers the spec's hostile corners:
character extensions ((V.O.), (CONT'D)) that must merge into one character,
parentheticals that are direction rather than spoken text, notes and boneyard
that must vanish, forced elements, and transitions."""

from fastapi.testclient import TestClient

import main
from fountain import characters, parse_fountain, to_cue_script

# A small screenplay exercising most of the format at once.
GOLDEN = """\
Title: _**The Last Pour**_
Credit: Written by
Author: V. Jadhav
Draft date: 1/1/2026

INT. COFFEE SHOP - NIGHT

The place is empty. MAYA wipes the counter. A bell RINGS as DEV enters,
soaked from the rain.

MAYA
We're closed.

DEV (O.S.)
(quietly)
The sign says open.

MAYA (CONT'D)
The sign lies.

[[maybe cut this beat]]

DEV
(beat, then softer)
I'm not here for coffee.

/* an old draft of this scene said
DEV: I'm here for you.
which was too much */

> BURN TO: <

.INSERT - THE SIGN

It flickers: OPEN. OPEN. CLOSED.

CUT TO:

# Act Two

= Maya decides to hear him out.

MAYA ^
(almost laughing)
Then you picked a *terrible* night.

@McCLANE
Yippee ki-yay.

THE END
"""


# --- parse_fountain: elements and title ---


def test_title_is_extracted_and_unstyled():
    parsed = parse_fountain(GOLDEN)
    assert parsed["title"] == "The Last Pour"


def test_dialogue_speakers_and_texts():
    parsed = parse_fountain(GOLDEN)
    dialogue = [e for e in parsed["elements"] if e["type"] == "dialogue"]
    assert [(d["speaker"], d["text"]) for d in dialogue] == [
        ("MAYA", "We're closed."),
        ("DEV", "The sign says open."),
        ("MAYA", "The sign lies."),
        ("DEV", "I'm not here for coffee."),
        ("MAYA", "Then you picked a terrible night."),
        ("McCLANE", "Yippee ki-yay."),
    ]


def test_extensions_merge_into_one_character():
    """DEV and DEV (O.S.), MAYA and MAYA (CONT'D) are the same characters."""
    parsed = parse_fountain(GOLDEN)
    assert characters(parsed) == ["MAYA", "DEV", "McCLANE"]


def test_parentheticals_become_hints_not_spoken_text():
    parsed = parse_fountain(GOLDEN)
    dialogue = [e for e in parsed["elements"] if e["type"] == "dialogue"]
    assert dialogue[1]["hint"] == "quietly"
    assert dialogue[3]["hint"] == "beat, then softer"
    assert dialogue[0]["hint"] is None
    for d in dialogue:
        assert "(" not in d["text"]


def test_notes_and_boneyard_vanish_entirely():
    parsed = parse_fountain(GOLDEN)
    all_text = " ".join(e["text"] for e in parsed["elements"])
    assert "maybe cut this beat" not in all_text
    assert "too much" not in all_text
    assert "here for you" not in all_text  # the boneyard's old draft never leaks


def test_transitions_sections_synopses_are_dropped():
    parsed = parse_fountain(GOLDEN)
    all_text = " ".join(e["text"] for e in parsed["elements"])
    assert "CUT TO:" not in all_text
    assert "Act Two" not in all_text
    assert "hear him out" not in all_text


def test_scene_headings_are_kept_as_scene_elements():
    parsed = parse_fountain(GOLDEN)
    scenes = [e["text"] for e in parsed["elements"] if e["type"] == "scene"]
    assert "INT. COFFEE SHOP - NIGHT" in scenes
    assert "INSERT - THE SIGN" in scenes  # forced with a leading dot


def test_action_blocks_join_their_lines():
    parsed = parse_fountain(GOLDEN)
    actions = [e["text"] for e in parsed["elements"] if e["type"] == "action"]
    assert any("bell RINGS as DEV enters, soaked from the rain." in a for a in actions)


def test_emphasis_markers_are_stripped_from_spoken_text():
    parsed = parse_fountain(GOLDEN)
    dialogue = [e for e in parsed["elements"] if e["type"] == "dialogue"]
    assert dialogue[4]["text"] == "Then you picked a terrible night."


def test_all_caps_action_line_is_not_a_character_cue():
    """THE END has no dialogue under it, so it's action, not a speaker."""
    parsed = parse_fountain(GOLDEN)
    assert "THE END" not in characters(parsed)


def test_plain_text_without_fountain_structure_is_all_action():
    parsed = parse_fountain("Just a line.\n\nAnother line.")
    assert [e["type"] for e in parsed["elements"]] == ["action", "action"]
    assert parsed["title"] is None


# --- to_cue_script: converting to Cue's native format ---


def test_dialogue_converts_to_speaker_lines_with_hints():
    script = to_cue_script(parse_fountain(GOLDEN))
    lines = script.splitlines()
    assert "MAYA: We're closed." in lines
    assert "DEV (quietly): The sign says open." in lines
    assert "MAYA: The sign lies." in lines


def test_action_is_excluded_by_default_and_included_on_request():
    parsed = parse_fountain(GOLDEN)
    without = to_cue_script(parsed)
    assert "soaked from the rain" not in without

    with_action = to_cue_script(parsed, include_action=True)
    assert "soaked from the rain." in with_action
    assert "INT. COFFEE SHOP - NIGHT" in with_action


def test_speaker_names_are_safe_for_cue_parsing():
    """Names with periods (MRS. HUGHES) must survive the round trip into
    Cue's own NAME: line parser, which allows no periods in names."""
    parsed = parse_fountain("MRS. HUGHES\nDinner is served.\n")
    script = to_cue_script(parsed)
    assert script == "MRS HUGHES: Dinner is served."


# --- the endpoint ---


def test_import_endpoint_returns_script_title_and_characters():
    client = TestClient(main.app)
    response = client.post("/import/fountain", json={"text": GOLDEN})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "The Last Pour"
    assert data["characters"] == ["MAYA", "DEV", "McCLANE"]
    assert "MAYA: We're closed." in data["script"]
    assert data["dialogue_lines"] == 6
    assert data["action_lines"] > 0


def test_import_endpoint_can_include_action_as_narration():
    client = TestClient(main.app)
    response = client.post("/import/fountain", json={"text": GOLDEN, "include_action": True})
    assert "soaked from the rain." in response.json()["script"]


def test_import_endpoint_rejects_empty_and_unperformable_input():
    client = TestClient(main.app)
    assert client.post("/import/fountain", json={"text": "   "}).status_code == 400
