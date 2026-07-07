"""Voice providers — the swappable 'engines' that turn text into audio.

Every provider exposes the same shape: a name, a content type, a file
extension, and a synthesize(text, speed) -> bytes method. That sameness is what
lets the Engine try one and fall back to another.

- ElevenLabsProvider: the default, studio-quality cloud voice (needs an API key).
- PiperProvider: the free, local, offline fallback.
"""

import io
import os
import re
import wave
from pathlib import Path

import httpx
from piper import PiperVoice, SynthesisConfig

import clones

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

    def supports(self, voice: str) -> bool:
        # Local clones never leave the machine — the cloud never sees them.
        return not voice.startswith("local:")

    def synthesize(
        self,
        text: str,
        settings: dict,
        tags: list,
        voice: str = "",
        delivery: str = "",
        api_key: str = "",
    ) -> bytes:
        # A visitor's own key (bring-your-own-key) wins over the host's .env
        # key, so their reads spend their credits. Never stored, never logged.
        key = api_key or self.api_key
        # No key at all means this engine can't run — the Engine falls back.
        if not key:
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
                "xi-api-key": key,
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


# A [tag] would be read out loud by the local engines; the delivery's
# expressive punctuation and CAPS still carry the performance.
_TAG_IN_DELIVERY_RE = re.compile(r"\[[^\]]+\]\s*")


def strip_tags(delivery: str) -> str:
    return re.sub(r"\s+", " ", _TAG_IN_DELIVERY_RE.sub("", delivery)).strip()


def expression_controls(settings: dict) -> dict:
    """Map Cue's per-line direction onto the local engine's knobs.

    The brain speaks in stability (low = raw, unhinged) and style (high =
    stylized, dramatic). Chatterbox speaks in exaggeration (emotion intensity,
    ~0.3 flat .. ~1.3 wild) and cfg_weight (adherence/pace, higher = steadier).
    """
    return {
        "exaggeration": round(0.3 + settings["style"] * 0.9, 3),
        "cfg_weight": round(0.25 + settings["stability"] * 0.45, 3),
    }


class ChatterboxProvider:
    """Cue's own local voice engine: zero-shot voice cloning with emotion
    control, running entirely on this machine (MIT-licensed Chatterbox
    weights). Speaks only `local:` voices — the clones in the registry. The
    user's voice sample and every generated clip never leave the computer."""

    name = "chatterbox"
    content_type = "audio/wav"
    ext = "wav"

    def __init__(self) -> None:
        # The model is heavy (~2GB of weights), so it loads lazily on the
        # first clone render and is reused after that.
        self._model = None

    def supports(self, voice: str) -> bool:
        return voice.startswith("local:")

    def _get_model(self):
        if self._model is None:
            import torch
            from chatterbox.tts import ChatterboxTTS

            device = "mps" if torch.backends.mps.is_available() else "cpu"
            try:
                self._model = ChatterboxTTS.from_pretrained(device=device)
            except Exception:
                if device == "cpu":
                    raise
                self._model = ChatterboxTTS.from_pretrained(device="cpu")
        return self._model

    def synthesize(
        self,
        text: str,
        settings: dict,
        tags: list,
        voice: str = "",
        delivery: str = "",
        api_key: str = "",
    ) -> bytes:
        if not voice.startswith("local:"):
            raise RuntimeError("chatterbox speaks only local clone voices")
        sample = clones.clone_path(voice[len("local:") :])
        if sample is None:
            raise RuntimeError("unknown clone voice")

        # The delivery's punctuation and CAPS carry the emotion; inline [tags]
        # would be read aloud, so they're stripped.
        spoken = strip_tags(delivery) if delivery else text
        controls = expression_controls(settings)

        import torchaudio

        model = self._get_model()
        wav = model.generate(
            spoken,
            audio_prompt_path=str(sample),
            exaggeration=controls["exaggeration"],
            cfg_weight=controls["cfg_weight"],
        )
        out = io.BytesIO()
        torchaudio.save(out, wav, model.sr, format="wav")
        return out.getvalue()


class PiperProvider:
    """Local neural TTS. Free, offline, no quota."""

    name = "piper"
    content_type = "audio/wav"
    ext = "wav"

    def __init__(self) -> None:
        # The model is ~60MB, so load it once and reuse it, not per request.
        self._voice: PiperVoice | None = None

    def supports(self, voice: str) -> bool:
        # Piper can't speak a clone: falling back to its generic voice would
        # put someone else's voice on the user's words. Fail loudly instead.
        return not voice.startswith("local:")

    def _get_voice(self) -> PiperVoice:
        if self._voice is None:
            self._voice = PiperVoice.load(str(PIPER_MODEL))
        return self._voice

    def synthesize(
        self,
        text: str,
        settings: dict,
        tags: list,
        voice: str = "",
        delivery: str = "",
        api_key: str = "",
    ) -> bytes:
        """Render text to WAV bytes. Piper has only its one local model, so it
        ignores the chosen `voice`, the expressive controls (stability/style),
        the audio tags, the delivery (it would read the [tags] out loud), and
        the api_key (it's local — nobody's credits) — it can only honor speed,
        speaking the clean text."""
        # Piper's length_scale stretches time, so it's the inverse of speed:
        # faster speech = shorter = smaller length_scale.
        config = SynthesisConfig(length_scale=1.0 / settings["speed"])

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            self._get_voice().synthesize_wav(text, wav_file, syn_config=config)
        return buffer.getvalue()
