"""The local clone registry — where a user's voice lives when Cue clones it.

A clone is a short recording of the user's own voice plus a name. It is
stored on THIS machine only (backend/clones/): the sample is what the local
voice engine conditions on every time it speaks as them. Nothing here ever
leaves the computer — that's the whole point.

Whatever the browser recorded (webm/opus, m4a, wav...) is normalized to wav
on the way in, so the engine can always read it back."""

import hashlib
import io
import json
from pathlib import Path

from pydub import AudioSegment, effects
from pydub.silence import detect_leading_silence

CLONES_DIR = Path(__file__).parent / "clones"

# The reference the voice engine conditions on clones better when it's clean:
# one channel, a standard rate, no dead air at the ends, and a consistent
# level. Browser recordings are none of these by default.
TARGET_RATE = 24000
SILENCE_DBFS = -40  # quieter than this at the ends counts as trimmable silence


def _preprocess(segment: AudioSegment) -> AudioSegment:
    """Clean a raw recording into a good voice-clone reference."""
    segment = segment.set_channels(1).set_frame_rate(TARGET_RATE)
    lead = detect_leading_silence(segment, silence_threshold=SILENCE_DBFS)
    trail = detect_leading_silence(segment.reverse(), silence_threshold=SILENCE_DBFS)
    # Only trim if real speech is left — never trim a sample down to nothing.
    if lead + trail < len(segment):
        segment = segment[lead : len(segment) - trail]
    # Peak-normalize to a consistent level so the encoder hears it clearly.
    return effects.normalize(segment, headroom=1.0)


def _index_path(clones_dir: Path) -> Path:
    return clones_dir / "index.json"


def _read_index(clones_dir: Path) -> list[dict]:
    path = _index_path(clones_dir)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def add_clone(name: str, audio_bytes: bytes, clones_dir: Path | None = None) -> dict:
    """Register a voice: decode + normalize the sample to wav, store it, and
    index it. Raises ValueError when the bytes aren't decodable audio."""
    directory = Path(clones_dir or CLONES_DIR)
    directory.mkdir(parents=True, exist_ok=True)

    try:
        segment = AudioSegment.from_file(io.BytesIO(audio_bytes))
    except Exception as err:
        raise ValueError("could not decode the audio sample") from err

    segment = _preprocess(segment)
    clone_id = hashlib.sha256(name.encode() + audio_bytes).hexdigest()[:16]
    out = io.BytesIO()
    segment.export(out, format="wav")
    (directory / f"{clone_id}.wav").write_bytes(out.getvalue())

    index = [entry for entry in _read_index(directory) if entry["id"] != clone_id]
    index.append({"id": clone_id, "name": name})
    _index_path(directory).write_text(json.dumps(index, indent=2))
    return {"id": clone_id, "name": name}


def list_clones(clones_dir: Path | None = None) -> list[dict]:
    """The registered voices, oldest first — what the voice pickers list."""
    return _read_index(Path(clones_dir or CLONES_DIR))


def clone_path(clone_id: str, clones_dir: Path | None = None) -> Path | None:
    """The stored sample for one clone, or None if it doesn't exist."""
    path = Path(clones_dir or CLONES_DIR) / f"{clone_id}.wav"
    return path if path.exists() else None
