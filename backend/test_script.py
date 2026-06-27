"""Tests for split_lines — turning a pasted script block into clean lines.
Pure logic, so it's a straight test-first target."""

from script import split_lines


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
