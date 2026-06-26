"""The Engine — orchestrates providers and the cache.

It owns the policy: serve from cache if possible (in provider preference
order), otherwise try each provider in order until one succeeds, caching the
result. This is what gives Cue graceful degradation — ElevenLabs first, Piper
when ElevenLabs is offline or out of quota — without the rest of the app caring
which engine actually ran.
"""


class Engine:
    def __init__(self, providers: list, cache) -> None:
        # Order matters: providers are tried in preference order.
        self.providers = providers
        self.cache = cache

    def render(self, text: str, settings: dict) -> dict:
        # 1. If any provider already has this exact render cached, reuse it.
        for provider in self.providers:
            key = self.cache.key(provider.name, settings, text)
            if self.cache.has(key, provider.ext):
                return {
                    "audio_id": key,
                    "ext": provider.ext,
                    "engine": provider.name,
                    "cached": True,
                }

        # 2. Cache miss: try each provider in order until one succeeds.
        for provider in self.providers:
            try:
                audio = provider.synthesize(text, settings)
            except Exception:
                continue  # this engine is down/out of quota — try the next
            key = self.cache.key(provider.name, settings, text)
            self.cache.write(key, provider.ext, audio)
            return {
                "audio_id": key,
                "ext": provider.ext,
                "engine": provider.name,
                "cached": False,
            }

        raise RuntimeError("all voice providers failed")
