"""Cue backend.

Receives a line plus an optional plain-English direction, interprets the
direction into voice settings (Step 2), then generates real audio for the line
(Step 3) and serves it back. Renders are cached on disk and keyed by their
inputs, so an identical line is reused instead of re-generated.
"""

import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Load backend/.env (the ElevenLabs key) before creating the providers.
load_dotenv(Path(__file__).parent / ".env")

from brains import BrainEngine, GroqBrain, KeywordBrain, OllamaBrain
from cache import AudioCache
from engine import Engine
from providers import DEFAULT_VOICE_ID, ElevenLabsProvider, PiperProvider
from script import parse_script, speakers
from settings import clean, clean_tags
from stitch import stitch, stitch_key
from voices import usable_voices

app = FastAPI()

# Allow the frontend (a different address) to call this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Voice: ElevenLabs first, Piper as the offline / out-of-quota fallback. The
# cache wraps both so identical lines are never re-rendered.
cache = AudioCache(Path(__file__).parent / "audio_cache")
voice_engine = Engine([ElevenLabsProvider(), PiperProvider()], cache)

# Brain: Groq (fast cloud LLM) interprets the direction, falling back to local
# Ollama if it's unavailable, then to the deterministic keyword matcher.
brain_engine = BrainEngine([GroqBrain(), OllamaBrain(), KeywordBrain()])

# Only ever serve files whose names look like our own hashes, never arbitrary
# paths — this stops requests like /audio/../../secret.
SAFE_AUDIO_NAME = re.compile(r"[a-f0-9]{64}\.(wav|mp3)")


class SpeakRequest(BaseModel):
    text: str
    direction: str = ""


class DirectRequest(BaseModel):
    # The whole pasted script (line breaks separate lines) + one direction.
    script: str
    direction: str = ""


class RenderRequest(BaseModel):
    # A single line plus the settings/tags it already got from /direct. The
    # client supplies these, so they're re-cleaned before they reach the voice.
    text: str
    settings: dict = {}
    tags: list[str] = []
    voice: str = ""  # an ElevenLabs voice_id; empty = the default voice


class ReadRequest(BaseModel):
    # The whole directed script, ready to perform: each line with the settings,
    # tags, and voice it should be rendered with. Order = playback order.
    lines: list[RenderRequest]


# Shown in the voice dropdown when ElevenLabs can't be reached (no key, offline,
# out of quota) so the picker is never empty. A handful of stable premade voices.
FALLBACK_VOICES = [
    {"id": "JBFqnCBsd6RMkjVDRZzb", "name": "George", "description": "Warm storyteller (British)"},
    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah", "description": "Mature, reassuring, confident"},
    {"id": "IKne3meq5aSn9XLyUdCD", "name": "Charlie", "description": "Deep, energetic (Australian)"},
    {"id": "Xb7hH8MSUJpSbSDYk0k2", "name": "Alice", "description": "Clear educator (British)"},
    {"id": "SAz9YHcvj6GT2YYXdXww", "name": "River", "description": "Relaxed, neutral, informative"},
]


@app.get("/")
def root():
    return {"status": "ok", "message": "Cue backend is running"}


@app.post("/speak")
def speak(request: SpeakRequest):
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    # 1. Interpret the direction into settings + audio tags (brain: Ollama →
    #    keyword fallback).
    brain = brain_engine.interpret(text, request.direction)

    # 2. Render it (voice: cache → ElevenLabs v3 with tags → Piper fallback).
    rendered = voice_engine.render(text, brain["settings"], brain["tags"])

    return {
        **rendered,
        "settings": brain["settings"],
        "tags": brain["tags"],
        "notes": brain["notes"],
        "brain": brain["brain"],
    }


@app.post("/direct")
def direct(request: DirectRequest):
    """Restyle a whole script under one direction. Parses the pasted block into
    speaker-attributed lines (`NAME: text`, or no speaker for a plain read) and
    interprets each line's text with the full script as context, so the direction
    can ramp across the arc. Brain only — no audio is rendered here, so this is
    fast and spends no ElevenLabs credits."""
    parsed = parse_script(request.script)
    texts = [line["text"] for line in parsed]
    interpretations = brain_engine.interpret_script(texts, request.direction)
    return {
        "lines": [
            {
                "speaker": line["speaker"],
                "text": line["text"],
                "settings": result["settings"],
                "tags": result["tags"],
                "notes": result["notes"],
                "brain": result["brain"],
            }
            for line, result in zip(parsed, interpretations)
        ],
        "speakers": speakers(parsed),
    }


@app.post("/render")
def render(request: RenderRequest):
    """Render one line into audio using the settings/tags it already got from
    /direct. This is what Play calls — it does NOT re-interpret, just voices the
    line (cache → ElevenLabs v3 with tags → Piper fallback)."""
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    # The settings/tags came from the client, so re-clean them before the voice.
    settings = clean(request.settings)
    tags = clean_tags(request.tags)
    return voice_engine.render(text, settings, tags, request.voice)


@app.post("/read")
def read(request: ReadRequest):
    """Step 5: perform the whole script as ONE continuous track. Renders every
    line (cache -> ElevenLabs/Piper) in its own voice, then stitches the clips
    together with a natural pause between lines. The stitched track is cached
    too, so replaying an unchanged read is free — and it's the same file the
    Download button serves."""
    if not request.lines:
        raise HTTPException(status_code=400, detail="lines are required")

    clips = []
    volumes = []
    for line in request.lines:
        text = line.text.strip()
        if not text:
            continue
        settings = clean(line.settings)
        rendered = voice_engine.render(text, settings, clean_tags(line.tags), line.voice)
        clips.append(rendered)
        # Clips are rendered volume-free (volume is a playback concern), so the
        # line's volume is baked into the stitched track as gain instead.
        volumes.append(settings["volume"])
    if not clips:
        raise HTTPException(status_code=400, detail="lines are required")

    key = stitch_key([c["audio_id"] for c in clips], volumes=volumes)
    if not cache.has(key, "mp3"):
        paths = [cache.path(c["audio_id"], c["ext"]) for c in clips]
        cache.write(key, "mp3", stitch(paths, volumes=volumes))
        return {"audio_id": key, "ext": "mp3", "engine": "stitch", "cached": False}
    return {"audio_id": key, "ext": "mp3", "engine": "stitch", "cached": True}


@app.get("/voices")
def voices():
    """The voices the picker offers — the ones in your ElevenLabs account
    (premade + any you've saved or created). Falls back to a small curated list
    if ElevenLabs can't be reached, so the dropdown is never empty."""
    default = os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if key:
        try:
            response = httpx.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": key},
                timeout=10.0,
            )
            response.raise_for_status()
            # Only the voices the free-tier API can actually render (premade +
            # your own); library 'professional' voices 402 and would fall back
            # to the wrong voice.
            mapped = usable_voices(response.json().get("voices", []))
            if mapped:
                return {"voices": mapped, "default": default}
        except Exception:
            pass  # fall through to the curated list
    return {"voices": FALLBACK_VOICES, "default": default}


@app.get("/audio/{filename}")
def get_audio(filename: str, download: bool = False):
    if not SAFE_AUDIO_NAME.fullmatch(filename):
        raise HTTPException(status_code=404, detail="not found")
    audio_path = cache.cache_dir / filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="not found")
    media_type = "audio/wav" if filename.endswith(".wav") else "audio/mpeg"
    if download:
        # Content-Disposition: attachment — the browser saves it as a file
        # instead of playing it.
        return FileResponse(audio_path, media_type=media_type, filename="cue-read.mp3")
    return FileResponse(audio_path, media_type=media_type)
