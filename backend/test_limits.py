"""Tests for input limits — the caps that keep one request from wedging the
server or burning a whole quota: a pasted novel, a 5000-line script, a
gigabyte "recording". Limits are generous for real use, hard 400s past that
(413 for uploads), and the message names the cap so the caller can fix it.
"""

import pytest
from fastapi.testclient import TestClient

import main


def client():
    return TestClient(main.app)


NEUTRAL = {"stability": 0.5, "style": 0.5, "speed": 1.0, "volume": 1.0}


class NeutralBrain:
    def interpret_script(self, lines, direction, hints=None):
        return [
            {"settings": NEUTRAL, "tags": [], "notes": "", "delivery": None, "brain": "fake"}
            for _ in lines
        ]


@pytest.fixture
def quiet_brain(monkeypatch):
    monkeypatch.setattr(main, "brain_engine", NeutralBrain())


# --- /direct: the pasted script ---


def test_direct_rejects_too_many_lines(quiet_brain):
    script = "\n".join(f"Line {i}." for i in range(main.MAX_SCRIPT_LINES + 1))
    response = client().post("/direct", json={"script": script, "direction": "warm"})
    assert response.status_code == 400
    assert str(main.MAX_SCRIPT_LINES) in response.json()["detail"]


def test_direct_accepts_a_script_at_the_limit(quiet_brain):
    script = "\n".join(f"Line {i}." for i in range(main.MAX_SCRIPT_LINES))
    response = client().post("/direct", json={"script": script, "direction": "warm"})
    assert response.status_code == 200
    assert len(response.json()["lines"]) == main.MAX_SCRIPT_LINES


def test_direct_rejects_a_monster_paste(quiet_brain):
    script = "x" * (main.MAX_SCRIPT_CHARS + 1)
    response = client().post("/direct", json={"script": script, "direction": ""})
    assert response.status_code == 400


def test_direct_rejects_one_overlong_line(quiet_brain):
    script = "Short one.\n" + "y" * (main.MAX_LINE_CHARS + 1)
    response = client().post("/direct", json={"script": script, "direction": ""})
    assert response.status_code == 400
    assert str(main.MAX_LINE_CHARS) in response.json()["detail"]


def test_direct_caps_the_direction(quiet_brain):
    over = "d" * (main.MAX_DIRECTION_CHARS + 1)
    response = client().post("/direct", json={"script": "Hi.", "direction": over})
    assert response.status_code == 400


# --- /perform rides the same guards ---


def test_perform_shares_the_script_guards():
    script = "x" * (main.MAX_SCRIPT_CHARS + 1)
    response = client().post("/perform", json={"script": script})
    assert response.status_code == 400


def test_perform_rejects_too_many_lines():
    script = "\n".join(f"Line {i}." for i in range(main.MAX_SCRIPT_LINES + 1))
    response = client().post("/perform", json={"script": script, "direction": "warm"})
    assert response.status_code == 400


# --- /read: the pre-directed lines ---


def test_read_rejects_too_many_lines():
    line = {"text": "Hi.", "settings": NEUTRAL, "tags": [], "voice": "", "delivery": ""}
    response = client().post(
        "/read", json={"lines": [line] * (main.MAX_SCRIPT_LINES + 1), "music": ""}
    )
    assert response.status_code == 400


def test_read_rejects_an_overlong_line():
    long_line = {"text": "y" * (main.MAX_LINE_CHARS + 1), "settings": NEUTRAL, "tags": []}
    response = client().post("/read", json={"lines": [long_line], "music": ""})
    assert response.status_code == 400


# --- single-line endpoints ---


def test_render_caps_the_text():
    response = client().post("/render", json={"text": "y" * (main.MAX_LINE_CHARS + 1)})
    assert response.status_code == 400


def test_speak_caps_the_text():
    response = client().post("/speak", json={"text": "y" * (main.MAX_LINE_CHARS + 1)})
    assert response.status_code == 400


def test_retake_caps_the_note():
    response = client().post(
        "/retake",
        json={"script": ["Hi."], "index": 0, "note": "n" * (main.MAX_DIRECTION_CHARS + 1)},
    )
    assert response.status_code == 400


# --- /chat: the writer's room ---


def test_chat_caps_the_conversation():
    over = [{"role": "user", "content": "c" * (main.MAX_CHAT_CHARS + 1)}]
    response = client().post("/chat", json={"messages": over})
    assert response.status_code == 400


# --- /import/fountain: a real screenplay is big, so its cap is bigger ---


def test_fountain_has_its_own_generous_cap():
    response = client().post(
        "/import/fountain", json={"text": "x" * (main.MAX_FOUNTAIN_CHARS + 1)}
    )
    assert response.status_code == 400


# --- /voice/clone: the upload ---


def test_clone_upload_past_the_cap_is_413(monkeypatch):
    monkeypatch.setattr(main, "MAX_CLONE_BYTES", 1000)
    response = client().post(
        "/voice/clone",
        data={"name": "me", "consent": "true"},
        files={"files": ("rec.webm", b"x" * 2000, "audio/webm")},
    )
    assert response.status_code == 413
