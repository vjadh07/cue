"""Voice providers — the swappable 'engines' that turn text into audio.

Every provider exposes the same shape: a name, a content type, a file
extension, and a synthesize(text, speed) -> bytes method. That sameness is what
lets the orchestrator (engine.py) try one engine and fall back to another.

Step 3 starts with the free, local Piper engine. ElevenLabs is added later as
the default, with Piper kept as the offline / quota-exhausted fallback.
"""

import io
import wave
from pathlib import Path

from piper import PiperVoice, SynthesisConfig

# The downloaded Piper voice lives here (git-ignored — see .gitignore).
VOICES_DIR = Path(__file__).parent / "voices"
PIPER_MODEL = VOICES_DIR / "en_US-lessac-medium.onnx"


class PiperProvider:
    """Local neural TTS. Free, offline, no quota."""

    name = "piper"
    content_type = "audio/wav"
    ext = "wav"

    def __init__(self) -> None:
        # The model is ~60MB, so load it once and reuse it, not per request.
        self._voice: PiperVoice | None = None

    def _get_voice(self) -> PiperVoice:
        if self._voice is None:
            self._voice = PiperVoice.load(str(PIPER_MODEL))
        return self._voice

    def synthesize(self, text: str, speed: float) -> bytes:
        """Render text to WAV bytes at the given speed (1.0 = normal)."""
        # Piper's length_scale stretches time, so it's the inverse of speed:
        # faster speech = shorter = smaller length_scale.
        config = SynthesisConfig(length_scale=1.0 / speed)

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            self._get_voice().synthesize_wav(text, wav_file, syn_config=config)
        return buffer.getvalue()
