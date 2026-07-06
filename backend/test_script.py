"""Tests for the script parsing — turning a pasted script block into clean lines,
and into speaker-attributed lines for conversational scripts. Pure logic, so a
straight test-first target."""

from script import clean_generated, parse_script, speakers, split_lines


def test_splits_on_newlines():
    assert split_lines("a\nb\nc") == ["a", "b", "c"]


def test_drops_blank_and_whitespace_only_lines():
    assert split_lines("a\n\n   \nb") == ["a", "b"]


def test_trims_whitespace_around_each_line():
    assert split_lines("  hello  \n\tworld\t") == ["hello", "world"]


def test_handles_crlf_line_endings():
    assert split_lines("a\r\nb") == ["a", "b"]


def test_empty_or_blank_block_is_empty_list():
    assert split_lines("") == []
    assert split_lines("   \n  \n") == []


# --- parse_script: each line gets an optional speaker ---


def test_unlabeled_lines_have_no_speaker():
    assert parse_script("We did it.\nAfter all this time.") == [
        {"speaker": None, "text": "We did it.", "hint": None},
        {"speaker": None, "text": "After all this time.", "hint": None},
    ]


def test_labeled_lines_split_speaker_from_text():
    assert parse_script("ALICE: Where were you?\nBOB: ...out.") == [
        {"speaker": "ALICE", "text": "Where were you?", "hint": None},
        {"speaker": "BOB", "text": "...out.", "hint": None},
    ]


def test_mixed_labeled_and_unlabeled():
    assert parse_script("It was late.\nALICE: Where were you?") == [
        {"speaker": None, "text": "It was late.", "hint": None},
        {"speaker": "ALICE", "text": "Where were you?", "hint": None},
    ]


def test_speaker_name_can_contain_spaces():
    assert parse_script("Mr Smith: hello") == [{"speaker": "Mr Smith", "text": "hello", "hint": None}]


def test_a_colon_inside_a_sentence_is_not_a_speaker():
    # No speaker label: the time has a colon but it isn't "NAME: text".
    line = "Wait, it's 3:00 already"
    assert parse_script(line) == [{"speaker": None, "text": line, "hint": None}]


def test_colon_without_following_space_is_not_a_speaker():
    assert parse_script("ratio 16:9 looks right") == [
        {"speaker": None, "text": "ratio 16:9 looks right", "hint": None}
    ]


# --- speakers: the distinct named speakers, in first-seen order ---


def test_speakers_lists_distinct_names_in_order():
    parsed = parse_script("ALICE: hi\nBOB: yo\nALICE: again\nnarration here")
    assert speakers(parsed) == ["ALICE", "BOB"]


def test_speakers_empty_when_no_labels():
    assert speakers(parse_script("just a plain read")) == []


# --- clean_generated: sanitizing an LLM-written script ---


def test_clean_generated_strips_markdown_fences_and_blanks():
    raw = "```\nALICE: Hi.\n\nBOB: Hey.\n```"
    assert clean_generated(raw) == "ALICE: Hi.\nBOB: Hey."


def test_clean_generated_drops_headings_and_numbering():
    raw = "**The Scene**\n1. ALICE: Hi.\n2. BOB: Hey."
    assert clean_generated(raw) == "ALICE: Hi.\nBOB: Hey."


def test_clean_generated_caps_length():
    raw = "\n".join(f"Line {i}." for i in range(30))
    assert len(clean_generated(raw).splitlines()) == 12


def test_clean_generated_empty_input_is_empty():
    assert clean_generated("```\n\n```") == ""


# --- hints: a parenthetical after the name is direction, never spoken ---


def test_speaker_hint_is_extracted_not_spoken():
    assert parse_script("DEV (quietly): The sign says open.") == [
        {"speaker": "DEV", "text": "The sign says open.", "hint": "quietly"}
    ]


def test_hint_speakers_still_merge_with_plain_ones():
    parsed = parse_script("DEV (quietly): hey\nDEV: hey again")
    assert speakers(parsed) == ["DEV"]
