"""Audio cache — a small disk store so identical renders are reused, not
re-generated. Reusing a render means no API call, which is what keeps Cue
inside the free ElevenLabs quota.

The cache is keyed by what actually affects the audio: the engine, the speed,
and the text. (Volume is applied at playback, so it is not part of the key.)

It is also budgeted: without a cap, every render ever made stays forever,
which on a public deploy is a slow-motion disk-full outage. Writes past the
budget evict the oldest files first; a cache hit refreshes a file's age, so
the clips a scene is actively using survive while long-forgotten ones pay.
"""

import hashlib
import os
from pathlib import Path

DEFAULT_MAX_MB = 500  # ~a few thousand line clips, or dozens of full tracks


class AudioCache:
    def __init__(self, cache_dir: Path, max_bytes: int | None = None) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if max_bytes is None:
            max_bytes = int(os.environ.get("CUE_CACHE_MAX_MB", DEFAULT_MAX_MB)) * 1024 * 1024
        self.max_bytes = max_bytes

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
        path = self.path(key, ext)
        if not path.exists():
            return False
        self._touch(path)  # a hit means "in use": refresh its age
        return True

    def read(self, key: str, ext: str) -> bytes:
        path = self.path(key, ext)
        self._touch(path)
        return path.read_bytes()

    def write(self, key: str, ext: str, data: bytes) -> None:
        path = self.path(key, ext)
        path.write_bytes(data)
        self._evict(keep=path)

    @staticmethod
    def _touch(path: Path) -> None:
        try:
            os.utime(path)
        except OSError:
            pass  # freshness is best-effort; never fail a read over it

    def _evict(self, keep: Path) -> None:
        """Delete oldest files until the cache fits the budget. The file just
        written is never evicted — the caller is about to serve it, so the
        cache runs over budget with one file rather than break that request."""
        files = []
        total = 0
        for path in self.cache_dir.iterdir():
            try:
                if path.is_file():
                    stat = path.stat()
                    files.append((stat.st_mtime, stat.st_size, path))
                    total += stat.st_size
            except OSError:
                continue  # vanished mid-scan; nothing to account for
        if total <= self.max_bytes:
            return
        for _, size, path in sorted(files):
            if path == keep:
                continue
            try:
                path.unlink()
            except OSError:
                continue
            total -= size
            if total <= self.max_bytes:
                return
