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
from script import split_lines
from settings import clean, clean_tags

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
    """Step 4b: restyle a whole script under one direction. Splits the pasted
    block into lines and interprets each one with the full script as context
    (so the direction can ramp across the arc). Brain only — no audio is rendered
    here, so this is fast and spends no ElevenLabs credits."""
    lines = split_lines(request.script)
    interpretations = brain_engine.interpret_script(lines, request.direction)
    return {
        "lines": [
            {
                "text": line,
                "settings": result["settings"],
                "tags": result["tags"],
                "notes": result["notes"],
                "brain": result["brain"],
            }
            for line, result in zip(lines, interpretations)
        ]
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
            mapped = []
            for v in response.json().get("voices", []):
                labels = v.get("labels") or {}
                description = labels.get("description") or labels.get("use_case") or ""
                mapped.append(
                    {"id": v["voice_id"], "name": v.get("name", v["voice_id"]), "description": description}
                )
            if mapped:
                return {"voices": mapped, "default": default}
        except Exception:
            pass  # fall through to the curated list
    return {"voices": FALLBACK_VOICES, "default": default}


@app.get("/audio/{filename}")
def get_audio(filename: str):
    if not SAFE_AUDIO_NAME.fullmatch(filename):
        raise HTTPException(status_code=404, detail="not found")
    audio_path = cache.cache_dir / filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="not found")
    media_type = "audio/wav" if filename.endswith(".wav") else "audio/mpeg"
    return FileResponse(audio_path, media_type=media_type)
