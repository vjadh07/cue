"""The music bed — Step 6's "sounds produced, not raw".

underlay() puts a music bed under a stitched read with sidechain-style
ducking. Because Cue stitches the voice track itself, the timeline is known
exactly — no speech detection needed: the music plays alone for a short
intro, ducks while the voice speaks, then swells back and fades out.

Beds live in backend/music/ — drop any mp3/wav there and it shows up in the
picker. A default ambient bed is checked in so it works out of the box."""

import io
from pathlib import Path

from pydub import AudioSegment
from pydub.effects import normalize

MUSIC_DIR = Path(__file__).parent / "music"

INTRO_MS = 1500  # music alone before the first line
OUTRO_MS = 2500  # music alone after the last line, fading out
BED_DB = -8  # the bed's level relative to its normalized loudness
DUCK_DB = 12  # how far the bed dips under speech (positive number of dB)
FADE_MS = 350  # duck/swell transition time

AUDIO_EXTS = {".mp3", ".wav"}


def list_music(folder: Path = MUSIC_DIR) -> list[dict]:
    """The beds on offer: every audio file in the folder, prettified."""
    if not folder.is_dir():
        return []
    return [
        {"id": p.name, "name": p.stem.replace("-", " ").replace("_", " ")}
        for p in sorted(folder.iterdir())
        if p.suffix.lower() in AUDIO_EXTS
    ]


def underlay(voice_bytes: bytes, music_path: Path) -> bytes:
    """Mix a music bed under a rendered read, ducked while the voice speaks.
    Takes the stitched track's bytes, returns the produced mp3's bytes."""
    voice = AudioSegment.from_file(io.BytesIO(voice_bytes))
    bed = normalize(AudioSegment.from_file(music_path)) + BED_DB

    total_ms = INTRO_MS + len(voice) + OUTRO_MS

    # Loop the bed to cover the whole read.
    while len(bed) < total_ms:
        bed += bed
    bed = bed[:total_ms]

    # Shape the bed: full for the intro, RAMP down to ducked as the voice
    # enters, hold under the speech, ramp back up and fade out for the outro —
    # a proper sidechain curve, not a cut.
    intro = bed[:INTRO_MS].fade_in(min(FADE_MS, INTRO_MS))
    under = bed[INTRO_MS : INTRO_MS + len(voice)].fade(
        to_gain=-DUCK_DB, start=0, duration=min(FADE_MS, len(voice))
    )
    outro = bed[INTRO_MS + len(voice) :]
    if len(outro) > FADE_MS:
        outro = outro.fade(from_gain=-DUCK_DB, start=0, duration=FADE_MS)
    shaped = intro + under + outro.fade_out(min(len(outro), OUTRO_MS // 2))

    # Lay the voice on top, starting after the intro, and tidy the loudness.
    mixed = shaped.overlay(voice, position=INTRO_MS)
    produced = normalize(mixed, headroom=1.0)

    out = io.BytesIO()
    produced.export(out, format="mp3")
    return out.getvalue()
