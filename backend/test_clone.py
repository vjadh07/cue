"""Tests for /voice/clone — creating a voice from the user's own recording,
entirely on this machine. The rules that matter:

- explicit consent is required (own voice only — Cue never clones without it)
- no API key, no cloud: the sample is stored locally and the new voice speaks
  through Cue's local engine
- the new voice shows up in /voices like any other, marked as local
"""

from fastapi.testclient import TestClient

import clones
import main
from test_listen import tone_wav


def client():
    return TestClient(main.app)


def post_clone(consent="true", name="My voice", audio=None):
    return client().post(
        "/voice/clone",
        data={"name": name, "consent": consent},
        files=[("files", ("take1.wav", audio if audio is not None else tone_wav(220), "audio/wav"))],
    )


def test_clone_is_stored_locally_and_returned_as_a_local_voice(tmp_path, monkeypatch):
    monkeypatch.setattr(clones, "CLONES_DIR", tmp_path)

    response = post_clone()

    assert response.status_code == 200
    voice_id = response.json()["voice_id"]
    assert voice_id.startswith("local:")
    assert response.json()["engine"] == "cue-local"
    assert clones.clone_path(voice_id[len("local:") :], clones_dir=tmp_path) is not None


def test_clone_requires_consent(tmp_path, monkeypatch):
    monkeypatch.setattr(clones, "CLONES_DIR", tmp_path)

    response = post_clone(consent="false")

    assert response.status_code == 400
    assert "consent" in response.json()["detail"].lower()
    assert clones.list_clones(clones_dir=tmp_path) == []


def test_clone_requires_a_name(tmp_path, monkeypatch):
    monkeypatch.setattr(clones, "CLONES_DIR", tmp_path)
    assert post_clone(name="   ").status_code == 400


def test_undecodable_audio_is_a_clear_400(tmp_path, monkeypatch):
    monkeypatch.setattr(clones, "CLONES_DIR", tmp_path)
    assert post_clone(audio=b"not audio").status_code == 400


def test_delete_endpoint_removes_a_clone(tmp_path, monkeypatch):
    monkeypatch.setattr(clones, "CLONES_DIR", tmp_path)
    entry = clones.add_clone("My voice", tone_wav(220), clones_dir=tmp_path)

    response = client().delete(f"/voice/clone/local:{entry['id']}")

    assert response.status_code == 200
    assert clones.list_clones(clones_dir=tmp_path) == []


def test_delete_endpoint_accepts_the_bare_id_too(tmp_path, monkeypatch):
    monkeypatch.setattr(clones, "CLONES_DIR", tmp_path)
    entry = clones.add_clone("My voice", tone_wav(220), clones_dir=tmp_path)

    response = client().delete(f"/voice/clone/{entry['id']}")

    assert response.status_code == 200
    assert clones.list_clones(clones_dir=tmp_path) == []


def test_delete_endpoint_404s_on_unknown_clone(tmp_path, monkeypatch):
    monkeypatch.setattr(clones, "CLONES_DIR", tmp_path)
    assert client().delete("/voice/clone/feedfeedfeedfeed").status_code == 404


def test_delete_endpoint_rejects_a_malformed_id(tmp_path, monkeypatch):
    monkeypatch.setattr(clones, "CLONES_DIR", tmp_path)
    # Never let a path-ish id reach the filesystem.
    assert client().delete("/voice/clone/..%2f..%2fmain").status_code in (404, 422)


def test_voices_lists_local_clones_first(tmp_path, monkeypatch):
    monkeypatch.setattr(clones, "CLONES_DIR", tmp_path)
    entry = clones.add_clone("My voice", tone_wav(220), clones_dir=tmp_path)

    # ElevenLabs unreachable -> curated fallback; the local clone still leads.
    def boom(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr("main.httpx.get", boom)

    response = client().get("/voices")

    assert response.status_code == 200
    first = response.json()["voices"][0]
    assert first["id"] == f"local:{entry['id']}"
    assert "My voice" in first["name"]
