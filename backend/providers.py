"""Voice providers — the swappable 'engines' that turn text into audio.

Every provider exposes the same shape: a name, a content type, a file
extension, and a synthesize(text, speed) -> bytes method. That sameness is what
lets the Engine try one and fall back to another.

- ElevenLabsProvider: the default, studio-quality cloud voice (needs an API key).
- PiperProvider: the free, local, offline fallback.
"""

import io
import os
import wave
from pathlib import Path

import httpx
from piper import PiperVoice, SynthesisConfig

# The downloaded Piper voice lives here (git-ignored — see .gitignore).
VOICES_DIR = Path(__file__).parent / "voices"
PIPER_MODEL = VOICES_DIR / "en_US-lessac-medium.onnx"

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech"
# George — "Warm, Captivating Storyteller". Overridable via env.
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
# v3 is the expressive model that understands inline audio tags ([sarcastic],
# [whispers], ...) — that's what lets the voice actually act.
DEFAULT_MODEL = "eleven_v3"


class ElevenLabsProvider:
    """Studio-quality cloud TTS. Uses the free-tier API key from the environment."""

    name = "elevenlabs"
    content_type = "audio/mpeg"
    ext = "mp3"

    def __init__(self) -> None:
        self.api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        self.voice_id = os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)
        self.model = os.environ.get("ELEVENLABS_MODEL", DEFAULT_MODEL)

    def synthesize(
        self, text: str, settings: dict, tags: list, voice: str = "", delivery: str = ""
    ) -> bytes:
        # No key means this engine can't run — the Engine will fall back to Piper.
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not set")

        # The caller can pick the voice (the actor); fall back to the default.
        voice_id = voice or self.voice_id

        # Best case: the brain wrote a full performance — the same words with
        # inline tags at the emotional beats and expressive punctuation. Speak
        # that. Otherwise fall back to prepending the tags, e.g.
        # ["sarcastic", "sighs"] + "We did it." -> "[sarcastic] [sighs] We did it."
        if delivery:
            directed = delivery
        elif tags:
            directed = " ".join(f"[{t}]" for t in tags) + " " + text
        else:
            directed = text

        # The expressive controls come straight from the brain (already clamped).
        response = httpx.post(
            f"{ELEVENLABS_URL}/{voice_id}",
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json={
                "text": directed,
                "model_id": self.model,
                "voice_settings": {
                    "stability": settings["stability"],
                    "style": settings["style"],
                    "similarity_boost": 0.75,
                    "speed": settings["speed"],
                },
            },
            timeout=30.0,
        )
        # Raises on quota-exceeded / bad key / network issues; the Engine then
        # falls back to Piper.
        response.raise_for_status()
        return response.content


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

    def synthesize(
        self, text: str, settings: dict, tags: list, voice: str = "", delivery: str = ""
    ) -> bytes:
        """Render text to WAV bytes. Piper has only its one local model, so it
        ignores the chosen `voice`, the expressive controls (stability/style),
        the audio tags, and the delivery (it would read the [tags] out loud) —
        it can only honor speed, speaking the clean text."""
        # Piper's length_scale stretches time, so it's the inverse of speed:
        # faster speech = shorter = smaller length_scale.
        config = SynthesisConfig(length_scale=1.0 / settings["speed"])

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            self._get_voice().synthesize_wav(text, wav_file, syn_config=config)
        return buffer.getvalue()
