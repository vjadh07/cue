"""Stitching — joining the per-line clips into one continuous track.

Each line of a script is rendered (and cached) as its own clip; this joins
them, in order, with a short natural pause between lines, so the script plays
as one read instead of separate clips. Output is a single mp3 — the same file
the user can download.

Needs ffmpeg on the PATH (pydub shells out to it to decode mp3 and encode the
result)."""

import hashlib
import io
import math
from pathlib import Path

from pydub import AudioSegment

# The gap between lines. ~0.4s reads like a natural beat between spoken lines.
PAUSE_MS = 400


def stitch_key(
    clip_ids: list[str],
    pause_ms: int = PAUSE_MS,
    volumes: list[float] | None = None,
    music: str = "",
) -> str:
    """A stable cache id for one stitched track. The track is fully determined
    by which clips it joins, in what order, at what volumes, with what pause,
    under which music bed — so that's the key. Same shape as the per-clip cache
    ids (64-char sha256 hex).

    Per-line volume lives HERE and not in the clip cache: clips are rendered
    volume-free (volume is a playback concern), but a stitched track bakes the
    gain in, so it must key on it."""
    vol_str = ",".join(f"{v:.2f}" for v in volumes) if volumes else ""
    raw = f"stitch|{pause_ms}|{vol_str}|{music}|" + ",".join(clip_ids)
    return hashlib.sha256(raw.encode()).hexdigest()


def stitch(
    paths: list[Path], pause_ms: int = PAUSE_MS, volumes: list[float] | None = None
) -> bytes:
    """Concatenate audio files (wav or mp3, mixable) with silence between each,
    returning one mp3 as bytes. Each clip's volume (0-1, from its line's
    settings) is applied as gain — a whispered line stays quiet in the track."""
    if not paths:
        raise ValueError("nothing to stitch")

    clips = [AudioSegment.from_file(path) for path in paths]
    if volumes:
        # volume -> decibels: 0.5 ≈ -6dB, 1.0 = no change.
        clips = [
            clip.apply_gain(20 * math.log10(v)) if v < 1.0 else clip
            for clip, v in zip(clips, volumes)
        ]

    track = clips[0]
    if len(clips) > 1:
        pause = AudioSegment.silent(duration=pause_ms)
        for clip in clips[1:]:
            track += pause + clip

    out = io.BytesIO()
    track.export(out, format="mp3")
    return out.getvalue()
