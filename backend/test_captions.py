"""Tests for captions — SRT/VTT subtitle files generated from the stitcher's
timeline. The stitcher knows every clip's exact duration and every pause, so
the captions are pure timing math: no rendering, no credits, frame-accurate."""

from captions import srt, vtt

CUES = [
    {"start_ms": 0, "end_ms": 1500, "speaker": "MAYA", "text": "We're closed."},
    {"start_ms": 1900, "end_ms": 4200, "speaker": "DEV", "text": "The sign says open."},
    {"start_ms": 4600, "end_ms": 6000, "speaker": None, "text": "The rain gets louder."},
]


def test_srt_blocks_are_numbered_and_timed():
    out = srt(CUES)
    blocks = out.strip().split("\n\n")
    assert len(blocks) == 3
    assert blocks[0].splitlines() == [
        "1",
        "00:00:00,000 --> 00:00:01,500",
        "MAYA: We're closed.",
    ]
    assert blocks[1].splitlines()[0] == "2"
    assert blocks[1].splitlines()[1] == "00:00:01,900 --> 00:00:04,200"


def test_srt_speakerless_cue_is_bare_text():
    out = srt(CUES)
    assert "The rain gets louder." in out
    assert "None:" not in out


def test_srt_handles_hour_scale_timestamps():
    out = srt([{"start_ms": 3661001, "end_ms": 3662002, "speaker": None, "text": "hi"}])
    assert "01:01:01,001 --> 01:01:02,002" in out


def test_vtt_has_header_and_dot_separators():
    out = vtt(CUES)
    lines = out.splitlines()
    assert lines[0] == "WEBVTT"
    assert lines[1] == ""
    assert "00:00:00.000 --> 00:00:01.500" in out
    assert "MAYA: We're closed." in out


def test_empty_cues_still_produce_valid_files():
    assert srt([]) == ""
    assert vtt([]) == "WEBVTT\n"
