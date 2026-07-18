"""Audio cache — a small disk store so identical renders are reused, not
re-generated. Reusing a render means no API call, which is what keeps Cue
inside the free ElevenLabs quota.

The cache is keyed by what actually affects the audio: the engine, the speed,
and the text. (Volume is applied at playback, so it is not part of the key.)
"""

import hashlib
from pathlib import Path


class AudioCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def key(
        self,
        engine: str,
        settings: dict,
        text: str,
        tags: list,
        voice: str = "",
        delivery: str = "",
        take: int = 0,
    ) -> str:
        """A stable id for one exact render. Same inputs always give the same id.

        Keyed on everything that affects the audio: the engine, the voice, the
        expressive settings (stability/style/speed), the audio tags, the text,
        and the delivery (the performed rewrite actually spoken, when there is
        one). Volume is excluded — it's applied at playback, so it doesn't
        change the file.

        `take` is the performance loop's re-roll salt: TTS is stochastic, so
        take 1, 2, ... of identical inputs are genuinely different renders and
        must not collapse into one cache entry. Take 0 (the default) leaves
        the key exactly as before, so the existing cache stays warm.
        """
        s = settings
        tag_str = ",".join(tags)
        raw = (
            f"{engine}|{voice}|{s['stability']:.2f}|{s['style']:.2f}|{s['speed']:.2f}"
            f"|{tag_str}|{delivery}|{text}"
        )
        if take:
            raw += f"|t{take}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def path(self, key: str, ext: str) -> Path:
        return self.cache_dir / f"{key}.{ext}"

    def has(self, key: str, ext: str) -> bool:
        return self.path(key, ext).exists()

    def read(self, key: str, ext: str) -> bytes:
        return self.path(key, ext).read_bytes()

    def write(self, key: str, ext: str, data: bytes) -> None:
        self.path(key, ext).write_bytes(data)
