"""Captions — SRT and VTT subtitle files for a stitched read.

The stitcher knows the exact duration of every clip and every pause, so the
subtitles are pure timing math over data Cue already computes: no rendering,
no credits spent, accurate to the millisecond, identical whichever voice
engine performed the audio. A cue is {"start_ms", "end_ms", "speaker", "text"};
speaker None means the narrator (bare text, no name prefix)."""


def _stamp(ms: int, sep: str) -> str:
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{sep}{millis:03d}"


def _line(cue: dict) -> str:
    return f"{cue['speaker']}: {cue['text']}" if cue["speaker"] else cue["text"]


def srt(cues: list[dict]) -> str:
    """SubRip: numbered blocks, comma millisecond separator."""
    blocks = [
        f"{n}\n{_stamp(c['start_ms'], ',')} --> {_stamp(c['end_ms'], ',')}\n{_line(c)}"
        for n, c in enumerate(cues, 1)
    ]
    return "\n\n".join(blocks) + "\n" if blocks else ""


def vtt(cues: list[dict]) -> str:
    """WebVTT: the browser-native format (works in <track> tags), dot separator."""
    blocks = [
        f"{_stamp(c['start_ms'], '.')} --> {_stamp(c['end_ms'], '.')}\n{_line(c)}" for c in cues
    ]
    return "WEBVTT\n" + ("\n" + "\n\n".join(blocks) + "\n" if blocks else "")
