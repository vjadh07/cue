"""Tests for /voice/clone — creating a voice from the visitor's own recording,
through THEIR ElevenLabs account. The rules that matter:

- the visitor's own API key is REQUIRED (never the host's; cloning always
  happens in the visitor's account, which enforces its own plan and policy)
- explicit consent is required (own voice only — Cue never clones without it)
- ElevenLabs' refusal (wrong plan, bad key) surfaces as a clear error that
  never echoes the key
"""

import httpx
from fastapi.testclient import TestClient

import main


def client():
    return TestClient(main.app)


class RecordingPost:
    def __init__(self, status=200, body=None):
        self.status = status
        self.body = body or {"voice_id": "new-voice-123"}
        self.headers = None
        self.data = None
        self.files = None

    def __call__(self, url, headers=None, data=None, files=None, timeout=None):
        self.headers = headers
        self.data = data
        self.files = files
        request = httpx.Request("POST", url)
        response = httpx.Response(self.status, json=self.body, request=request)
        if self.status >= 400:
            raise httpx.HTTPStatusError(str(self.status), request=request, response=response)
        return response


def post_clone(key="visitor-key", consent="true", name="My voice"):
    headers = {"X-ElevenLabs-Key": key} if key else {}
    return client().post(
        "/voice/clone",
        headers=headers,
        data={"name": name, "consent": consent},
        files=[("files", ("take1.webm", b"fake-audio-bytes", "audio/webm"))],
    )


def test_clone_forwards_recording_to_the_visitors_account(monkeypatch):
    recorder = RecordingPost()
    monkeypatch.setattr("main.httpx.post", recorder)

    response = post_clone()

    assert response.status_code == 200
    assert response.json()["voice_id"] == "new-voice-123"
    assert recorder.headers["xi-api-key"] == "visitor-key"
    assert recorder.data["name"] == "My voice"
    assert recorder.files[0][1][0] == "take1.webm"
    assert recorder.files[0][1][1] == b"fake-audio-bytes"


def test_clone_requires_the_visitors_own_key(monkeypatch):
    recorder = RecordingPost()
    monkeypatch.setattr("main.httpx.post", recorder)

    response = post_clone(key="")

    assert response.status_code == 400
    assert recorder.headers is None  # nothing was forwarded


def test_clone_requires_consent(monkeypatch):
    recorder = RecordingPost()
    monkeypatch.setattr("main.httpx.post", recorder)

    response = post_clone(consent="false")

    assert response.status_code == 400
    assert recorder.headers is None
    assert "consent" in response.json()["detail"].lower()


def test_clone_requires_a_name(monkeypatch):
    monkeypatch.setattr("main.httpx.post", RecordingPost())
    assert post_clone(name="   ").status_code == 400


def test_elevenlabs_refusal_is_a_clear_error_without_the_key(monkeypatch):
    # 401 = wrong scope / plan gate on instant voice cloning (needs Starter).
    monkeypatch.setattr("main.httpx.post", RecordingPost(status=401))

    response = post_clone(key="super-secret-key")

    assert response.status_code == 402
    assert "plan" in response.json()["detail"].lower()
    assert "super-secret-key" not in response.text
