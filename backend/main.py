"""Cue backend.

Receives a line plus an optional plain-English direction, interprets the
direction into voice settings (Step 2), then generates real audio for the line
(Step 3) and serves it back. Renders are cached on disk and keyed by their
inputs, so an identical line is reused instead of re-generated.
"""

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from cache import AudioCache
from direction import interpret
from providers import PiperProvider

app = FastAPI()

# Allow the frontend (a different address) to call this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# The voice engine and the on-disk audio cache. (audio_cache/ is git-ignored.)
provider = PiperProvider()
cache = AudioCache(Path(__file__).parent / "audio_cache")

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

    # 1. Turn the direction into settings (Step 2 logic, unchanged).
    result = interpret(request.direction)
    speed = result["settings"]["speed"]

    # 2. Look this render up in the cache. A hit means no synthesis at all.
    audio_id = cache.key(provider.name, speed, text)
    if cache.has(audio_id, provider.ext):
        cached = True
    else:
        cache.write(audio_id, provider.ext, provider.synthesize(text, speed))
        cached = False

    return {
        "audio_id": audio_id,
        "ext": provider.ext,
        "engine": provider.name,
        "cached": cached,
        "settings": result["settings"],
        "matched": result["matched"],
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
