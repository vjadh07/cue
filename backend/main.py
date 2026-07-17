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
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Load backend/.env (the ElevenLabs key) before creating the providers.
load_dotenv(Path(__file__).parent / ".env")

import clones
from brains import BrainEngine, GroqBrain, KeywordBrain, OllamaBrain
from cache import AudioCache
from captions import srt, vtt
from delivery import verify_delivery
from engine import Engine
from fountain import characters, parse_fountain, to_cue_script
from listen import profile
from music import INTRO_MS, MUSIC_DIR, list_music, underlay
from providers import ChatterboxProvider, DEFAULT_VOICE_ID, ElevenLabsProvider, PiperProvider
from script import parse_script, speakers
from settings import clean, clean_tags
from stitch import stitch, stitch_key, timeline
from voices import usable_voices

app = FastAPI()


def cors_origins() -> list[str]:
    """Origins allowed to call this backend from a browser. Comma-separated
    CUE_CORS_ORIGINS in the environment, defaulting to the local frontend so
    dev needs no config. In production set it to your real frontend domain —
    never "*", so only your own site can call the backend with a visitor's key.
    """
    raw = os.environ.get("CUE_CORS_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


# Allow the frontend (a different address) to call this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Voice: ElevenLabs first for its voices, Cue's local clone engine for
# `local:` voices (each declares what it supports), Piper as the offline /
# out-of-quota fallback. The cache wraps all of them.
cache = AudioCache(Path(__file__).parent / "audio_cache")
voice_engine = Engine([ElevenLabsProvider(), ChatterboxProvider(), PiperProvider()], cache)

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
    # A single line plus the settings/tags/delivery it already got from /direct.
    # The client supplies these, so they're re-cleaned (and the delivery
    # re-verified word-for-word) before they reach the voice.
    text: str
    settings: dict = {}
    tags: list[str] = []
    voice: str = ""  # an ElevenLabs voice_id; empty = the default voice
    delivery: str = ""  # the performed rewrite; must speak exactly `text`'s words
    speaker: str = ""  # the character name; only used to label captions


class FountainRequest(BaseModel):
    # A raw .fountain screenplay (pasted or uploaded). include_action = also
    # read the action lines and scene headings, in the narrator's voice.
    text: str
    include_action: bool = False


class AnalyzeRequest(BaseModel):
    # A clip that was already rendered (its cache id + extension), plus the
    # line's text so speech rate can be computed. Analysis is local DSP only.
    audio_id: str
    ext: str
    text: str = ""


class RetakeRequest(BaseModel):
    # One line of the directed script, a director's note against the last
    # take, and the whole script for arc context. Returns a fresh
    # interpretation for that line only — the retake.
    script: list[str]
    index: int
    direction: str = ""
    note: str


class ReadRequest(BaseModel):
    # The whole directed script, ready to perform: each line with the settings,
    # tags, and voice it should be rendered with. Order = playback order.
    lines: list[RenderRequest]
    # A music bed id from GET /music (empty = no music). The bed plays alone
    # for a short intro, ducks under the speech, and swells back for the outro.
    music: str = ""


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    # The writer's-room conversation so far, oldest first. The brain sees the
    # whole thread, so "make it shorter" revises its own last draft.
    messages: list[ChatMessage]


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
def speak(request: SpeakRequest, x_elevenlabs_key: str = Header(default="")):
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    # 1. Interpret the direction into settings + audio tags (brain: Ollama →
    #    keyword fallback).
    brain = brain_engine.interpret(text, request.direction)

    # 2. Render it (voice: cache → ElevenLabs v3 with tags → Piper fallback).
    rendered = voice_engine.render(
        text, brain["settings"], brain["tags"], api_key=x_elevenlabs_key
    )

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
    hints = [line["hint"] for line in parsed]
    interpretations = brain_engine.interpret_script(texts, request.direction, hints=hints)
    return {
        "lines": [
            {
                "speaker": line["speaker"],
                "text": line["text"],
                "hint": line["hint"],
                "settings": result["settings"],
                "tags": result["tags"],
                "notes": result["notes"],
                "delivery": result["delivery"],
                "brain": result["brain"],
            }
            for line, result in zip(parsed, interpretations)
        ],
        "speakers": speakers(parsed),
    }


@app.post("/render")
def render(request: RenderRequest, x_elevenlabs_key: str = Header(default="")):
    """Render one line into audio using the settings/tags it already got from
    /direct. This is what Play calls — it does NOT re-interpret, just voices the
    line (cache → ElevenLabs v3 with tags → Piper fallback). A visitor's own
    ElevenLabs key (X-ElevenLabs-Key) spends their credits, not the host's."""
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    # The settings/tags/delivery came from the client, so re-clean them before
    # the voice — a tampered delivery must never be spoken.
    settings = clean(request.settings)
    tags = clean_tags(request.tags)
    delivery = verify_delivery(text, request.delivery) or ""
    try:
        return voice_engine.render(
            text, settings, tags, request.voice, delivery, api_key=x_elevenlabs_key
        )
    except RuntimeError:
        # Generic on purpose: error responses must never echo request details
        # (a visitor's API key rides this request).
        raise HTTPException(status_code=503, detail="no voice engine available")


@app.post("/chat")
def chat(request: ChatRequest):
    """The writer's room: chat with the brain to develop the material. Returns
    {message, script|null} — the script is the full current draft whenever the
    brain wrote or revised one. Only the LLM brains can write, so if none is
    reachable this is a plain error, not a silent fallback."""
    messages = [
        {"role": m.role, "content": m.content}
        for m in request.messages
        if m.role in ("user", "assistant") and m.content.strip()
    ]
    if not messages:
        raise HTTPException(status_code=400, detail="messages are required")
    try:
        return brain_engine.chat(messages)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="no brain available to write")


@app.post("/read")
def read(request: ReadRequest, x_elevenlabs_key: str = Header(default="")):
    """Step 5: perform the whole script as ONE continuous track. Renders every
    line (cache -> ElevenLabs/Piper) in its own voice, then stitches the clips
    together with a natural pause between lines. The stitched track is cached
    too, so replaying an unchanged read is free — and it's the same file the
    Download button serves."""
    if not request.lines:
        raise HTTPException(status_code=400, detail="lines are required")

    clips = []
    volumes = []
    cue_speakers = []
    cue_texts = []
    for line in request.lines:
        text = line.text.strip()
        if not text:
            continue
        settings = clean(line.settings)
        delivery = verify_delivery(text, line.delivery) or ""
        try:
            rendered = voice_engine.render(
                text, settings, clean_tags(line.tags), line.voice, delivery, api_key=x_elevenlabs_key
            )
        except RuntimeError:
            # Generic on purpose — see /render.
            raise HTTPException(status_code=503, detail="no voice engine available")
        clips.append(rendered)
        # Clips are rendered volume-free (volume is a playback concern), so the
        # line's volume is baked into the stitched track as gain instead.
        volumes.append(settings["volume"])
        cue_speakers.append(line.speaker.strip() or None)
        cue_texts.append(text)
    if not clips:
        raise HTTPException(status_code=400, detail="lines are required")

    # The music id must be one we actually offer — never a client-supplied path.
    music = request.music if any(t["id"] == request.music for t in list_music()) else ""

    key = stitch_key([c["audio_id"] for c in clips], volumes=volumes, music=music)
    paths = [cache.path(c["audio_id"], c["ext"]) for c in clips]
    cached = cache.has(key, "mp3")
    segments = None
    if not cached:
        track, segments = stitch(paths, volumes=volumes)
        if music:
            track = underlay(track, MUSIC_DIR / music)
        cache.write(key, "mp3", track)

    # Captions ride along for free: the stitcher's timeline says exactly when
    # each line plays (shifted by the intro when a music bed opens the track).
    if not cache.has(key, "srt"):
        if segments is None:
            segments = timeline(paths)  # backfill for a pre-captions track
        offset = INTRO_MS if music else 0
        cues = [
            {
                "start_ms": segment["start_ms"] + offset,
                "end_ms": segment["end_ms"] + offset,
                "speaker": speaker,
                "text": text,
            }
            for segment, speaker, text in zip(segments, cue_speakers, cue_texts)
        ]
        cache.write(key, "srt", srt(cues).encode())
        cache.write(key, "vtt", vtt(cues).encode())

    return {
        "audio_id": key,
        "ext": "mp3",
        "engine": "stitch",
        "cached": cached,
        "captions": True,
        # The per-line clips inside this track, in order — what the booth
        # analyzes to draw the measured energy arc of the whole read.
        "clips": [{"audio_id": c["audio_id"], "ext": c["ext"]} for c in clips],
    }


@app.post("/voice/clone")
async def voice_clone(
    name: str = Form(...),
    consent: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """Create a voice from the user's own recording — entirely on this
    machine. The sample is stored in the local clone registry and the voice
    speaks through Cue's local engine; no API key, no cloud, nothing leaves
    the computer. Explicit consent is required: your own voice only."""
    if consent.lower() != "true":
        raise HTTPException(
            status_code=400,
            detail="consent is required: the recording must be your own voice",
        )
    if not name.strip():
        raise HTTPException(status_code=400, detail="a name for the voice is required")
    if not files:
        raise HTTPException(status_code=400, detail="a recording is required")

    audio = await files[0].read()
    try:
        entry = clones.add_clone(name.strip(), audio)
    except ValueError:
        raise HTTPException(status_code=400, detail="couldn't read that audio; try a different recording")
    return {"voice_id": f"local:{entry['id']}", "engine": "cue-local"}


# A clone id is 16 hex chars; accept it bare or with the "local:" voice prefix.
SAFE_CLONE_ID = re.compile(r"(?:local:)?([a-f0-9]{16})$")


@app.delete("/voice/clone/{clone_id}")
def delete_voice_clone(clone_id: str):
    """Forget a locally-cloned voice: delete its sample and registry entry from
    this machine. The id must look like our own (16 hex, optionally 'local:'
    prefixed) so nothing path-ish ever reaches the filesystem."""
    match = SAFE_CLONE_ID.fullmatch(clone_id)
    if not match:
        raise HTTPException(status_code=404, detail="not found")
    if not clones.delete_clone(match.group(1)):
        raise HTTPException(status_code=404, detail="not found")
    return {"deleted": f"local:{match.group(1)}"}


@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    """The booth's ears: measure a rendered take — loudness, pitch,
    brightness, energy, speech rate — with local DSP over the cached clip.
    No credits, no network; the numbers are how Cue checks whether a
    direction actually landed in the audio."""
    filename = f"{request.audio_id}.{request.ext}"
    if not SAFE_AUDIO_NAME.fullmatch(filename):
        raise HTTPException(status_code=404, detail="not found")
    if not cache.has(request.audio_id, request.ext):
        raise HTTPException(status_code=404, detail="not found")

    measured = profile(cache.read(request.audio_id, request.ext))
    words = len(re.findall(r"[A-Za-z0-9']+", request.text))
    seconds = measured["duration_ms"] / 1000
    measured["words_per_sec"] = round(words / seconds, 2) if words and seconds > 0.2 else None
    return measured


@app.post("/retake")
def retake(request: RetakeRequest):
    """One line, one director's note, a new performance. The note is folded
    into that line's direction only (same convention as screenplay
    parentheticals), with the whole script still passed for arc context.
    Returns the fresh interpretation; the client renders it as the next take."""
    note = request.note.strip()
    if not note:
        raise HTTPException(status_code=400, detail="a note is required")
    if not 0 <= request.index < len(request.script):
        raise HTTPException(status_code=400, detail="index out of range")

    line = request.script[request.index]
    direction = f"{request.direction}. This line: {note}" if request.direction else f"This line: {note}"
    return brain_engine.interpret(line, direction, script=request.script, index=request.index)


@app.post("/import/fountain")
def import_fountain(request: FountainRequest):
    """Import a real screenplay: parse the Fountain format (what Highland,
    WriterDuet, and Final Draft export as plain text) into Cue's native script,
    merging character extensions (DEV (V.O.) is DEV), carrying parentheticals
    as per-line direction hints, and dropping everything nobody speaks."""
    parsed = parse_fountain(request.text)
    script_text = to_cue_script(parsed, include_action=request.include_action)
    if not script_text.strip():
        raise HTTPException(status_code=400, detail="no performable lines found")
    return {
        "script": script_text,
        "title": parsed["title"],
        "characters": characters(parsed),
        "dialogue_lines": sum(1 for e in parsed["elements"] if e["type"] == "dialogue"),
        "action_lines": sum(1 for e in parsed["elements"] if e["type"] in ("action", "scene")),
    }


@app.get("/music")
def music():
    """The music beds on offer for the full read — whatever audio lives in
    backend/music/ (two synthesized beds ship by default; drop in your own)."""
    return {"tracks": list_music()}


@app.get("/voices")
def voices(x_elevenlabs_key: str = Header(default="")):
    """The voices the picker offers — the ones in your ElevenLabs account
    (premade + any you've saved or created). With a visitor's own key
    (X-ElevenLabs-Key) it lists THEIR account's voices instead, and a bad
    pasted key gets a clear 401 so the studio can verify it on the spot.
    Without an explicit key it falls back to a small curated list whenever
    ElevenLabs can't be reached, so the dropdown is never empty."""
    default = os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)
    # The user's own local clones lead the list — they never depend on any
    # cloud being reachable.
    local = [
        {
            "id": f"local:{c['id']}",
            "name": f"{c['name']} · your voice",
            "description": "cloned locally; never leaves this machine",
        }
        for c in clones.list_clones()
    ]
    key = x_elevenlabs_key or os.environ.get("ELEVENLABS_API_KEY", "")
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
                return {"voices": local + mapped, "default": default}
        except Exception:
            # A key the visitor explicitly supplied deserves a real answer,
            # not a silent fallback — this is how the studio validates it.
            if x_elevenlabs_key:
                raise HTTPException(status_code=401, detail="ElevenLabs rejected this key")
    return {"voices": local + FALLBACK_VOICES, "default": default}


SAFE_CAPTION_NAME = re.compile(r"[a-f0-9]{64}\.(srt|vtt)")


@app.get("/captions/{filename}")
def get_captions(filename: str, download: bool = False):
    """The subtitle files written next to a stitched track — same id as the
    audio, .srt or .vtt extension. Same hash-only naming rule as /audio."""
    if not SAFE_CAPTION_NAME.fullmatch(filename):
        raise HTTPException(status_code=404, detail="not found")
    caption_path = cache.cache_dir / filename
    if not caption_path.exists():
        raise HTTPException(status_code=404, detail="not found")
    ext = filename.rsplit(".", 1)[1]
    media_type = "text/vtt" if ext == "vtt" else "application/x-subrip"
    if download:
        return FileResponse(caption_path, media_type=media_type, filename=f"cue-read.{ext}")
    return FileResponse(caption_path, media_type=media_type)


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
