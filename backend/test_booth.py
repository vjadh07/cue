"""Tests for the booth endpoints: /analyze (measure a rendered take) and
/retake (give one line a director's note and get a fresh interpretation)."""

import hashlib

from fastapi.testclient import TestClient

import main
from test_listen import tone_wav

KEY = hashlib.sha256(b"booth-test").hexdigest()


def client():
    return TestClient(main.app)


# --- /analyze: the measurements of one cached clip ---


def test_analyze_measures_a_cached_clip():
    main.cache.write(KEY, "wav", tone_wav(220, seconds=1.0))

    response = client().post(
        "/analyze", json={"audio_id": KEY, "ext": "wav", "text": "three little words"}
    )

    assert response.status_code == 200
    data = response.json()
    assert abs(data["pitch_hz"] - 220) < 8
    assert data["energy"] > 0.4
    assert abs(data["duration_ms"] - 1000) < 60
    # 3 words over ~1s. (Punctuation-free word count over duration.)
    assert 2.0 < data["words_per_sec"] < 4.0


def test_analyze_unknown_clip_is_404():
    missing = hashlib.sha256(b"never-rendered").hexdigest()
    assert client().post("/analyze", json={"audio_id": missing, "ext": "wav"}).status_code == 404


def test_analyze_rejects_non_hash_ids():
    response = client().post("/analyze", json={"audio_id": "../../etc/passwd", "ext": "wav"})
    assert response.status_code == 404


# --- /retake: one line, one note, a new performance ---


class NoteBrain:
    def __init__(self):
        self.seen = None

    def interpret(self, line, direction, script=None, index=0):
        self.seen = {"line": line, "direction": direction, "script": script, "index": index}
        return {
            "settings": {"stability": 0.2, "style": 0.7, "speed": 1.0, "volume": 1.0},
            "tags": ["whispers"],
            "notes": "colder now",
            "delivery": "[whispers] Stop it.",
            "brain": "fake",
        }


def test_retake_folds_the_note_into_that_lines_direction(monkeypatch):
    brain = NoteBrain()
    monkeypatch.setattr(main, "brain_engine", brain)

    response = client().post(
        "/retake",
        json={
            "script": ["It is fine.", "Stop it."],
            "index": 1,
            "direction": "quiet menace",
            "note": "colder, done crying",
        },
    )

    assert response.status_code == 200
    assert brain.seen["line"] == "Stop it."
    assert brain.seen["index"] == 1
    assert brain.seen["script"] == ["It is fine.", "Stop it."]
    assert brain.seen["direction"] == "quiet menace. This line: colder, done crying"
    assert response.json()["tags"] == ["whispers"]
    assert response.json()["delivery"] == "[whispers] Stop it."


def test_retake_note_alone_works_without_a_global_direction(monkeypatch):
    brain = NoteBrain()
    monkeypatch.setattr(main, "brain_engine", brain)

    response = client().post(
        "/retake",
        json={"script": ["Stop it."], "index": 0, "direction": "", "note": "softer"},
    )

    assert response.status_code == 200
    assert brain.seen["direction"] == "This line: softer"


def test_read_lists_its_per_line_clips_for_the_booth(monkeypatch, tmp_path):
    """The booth analyzes each line of a full read — so /read must say which
    cached clip belongs to which line, in order."""

    class FakeEngine:
        def __init__(self):
            self.n = 0

        def render(self, text, settings, tags, voice="", delivery="", api_key=""):
            self.n += 1
            return {"audio_id": f"{self.n:064d}"[:64].replace("0", "a"), "ext": "mp3", "engine": "fake", "cached": False}

    monkeypatch.setattr(main, "voice_engine", FakeEngine())
    monkeypatch.setattr(main, "stitch", lambda paths, pause_ms=400, volumes=None: (b"track", []))
    monkeypatch.setattr(main, "timeline", lambda paths, pause_ms=400: [])
    monkeypatch.setattr(main.cache, "has", lambda key, ext: False)
    monkeypatch.setattr(main.cache, "write", lambda key, ext, data: None)
    monkeypatch.setattr(main.cache, "path", lambda key, ext: tmp_path / f"{key}.{ext}")

    response = client().post("/read", json={"lines": [{"text": "one"}, {"text": "two"}]})

    assert response.status_code == 200
    clips = response.json()["clips"]
    assert len(clips) == 2
    assert all(c["ext"] == "mp3" for c in clips)


def test_retake_requires_a_note_and_a_valid_index(monkeypatch):
    brain = NoteBrain()
    monkeypatch.setattr(main, "brain_engine", brain)

    no_note = client().post(
        "/retake", json={"script": ["hi"], "index": 0, "direction": "", "note": "  "}
    )
    assert no_note.status_code == 400

    bad_index = client().post(
        "/retake", json={"script": ["hi"], "index": 4, "direction": "", "note": "softer"}
    )
    assert bad_index.status_code == 400
