"""Tests for deploy config that shouldn't be hardcoded — the CORS origins the
backend accepts from a browser. Local dev keeps working with no env set;
production points it at the real frontend domain."""

from main import cors_origins


def test_defaults_to_the_local_frontend(monkeypatch):
    monkeypatch.delenv("CUE_CORS_ORIGINS", raising=False)
    assert cors_origins() == ["http://localhost:3000"]


def test_reads_a_comma_separated_list(monkeypatch):
    monkeypatch.setenv("CUE_CORS_ORIGINS", "https://cue.app, https://www.cue.app")
    assert cors_origins() == ["https://cue.app", "https://www.cue.app"]


def test_ignores_blank_entries_and_trims(monkeypatch):
    monkeypatch.setenv("CUE_CORS_ORIGINS", " https://cue.app ,, ")
    assert cors_origins() == ["https://cue.app"]
