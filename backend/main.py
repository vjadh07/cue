"""Cue backend.

Receives a line plus an optional plain-English direction, interprets the
direction into voice settings (Step 2), then generates real audio for the line
(Step 3) and serves it back. Renders are cached on disk and keyed by their
inputs, so an identical line is reused instead of re-generated.
"""

import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Load backend/.env (the ElevenLabs key) before creating the providers.
load_dotenv(Path(__file__).parent / ".env")

from brains import BrainEngine, KeywordBrain, OllamaBrain
from cache import AudioCache
from engine import Engine
from providers import ElevenLabsProvider, PiperProvider

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

# Brain: local Ollama interprets the direction, with the keyword matcher as the
# deterministic final fallback. (The Groq cloud default gets added in front later.)
brain_engine = BrainEngine([OllamaBrain(), KeywordBrain()])

# Only ever serve files whose names look like our own hashes, never arbitrary
# paths — this stops requests like /audio/../../secret.
SAFE_AUDIO_NAME = re.compile(r"[a-f0-9]{64}\.(wav|mp3)")


class SpeakRequest(BaseModel):
    text: str
    direction: str = ""


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


@app.get("/audio/{filename}")
def get_audio(filename: str):
    if not SAFE_AUDIO_NAME.fullmatch(filename):
        raise HTTPException(status_code=404, detail="not found")
    audio_path = cache.cache_dir / filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="not found")
    media_type = "audio/wav" if filename.endswith(".wav") else "audio/mpeg"
    return FileResponse(audio_path, media_type=media_type)
