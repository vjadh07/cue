"""The Engine — orchestrates providers and the cache.

It owns the policy: serve from cache if possible (in provider preference
order), otherwise try each provider in order until one succeeds, caching the
result. A transient failure (rate limit, network blip) gets one retry before
the engine falls back, so a single hiccup doesn't swap the voice out from
under the user. This is what gives Cue graceful degradation — ElevenLabs
first, Piper when ElevenLabs is truly down or out of quota — without the rest
of the app caring which engine actually ran.
"""

import time

# One retry, after a short breath — enough for a rate-limit blip to pass.
RETRY_DELAY_SECONDS = 0.4


class Engine:
    def __init__(self, providers: list, cache) -> None:
        # Order matters: providers are tried in preference order.
        self.providers = providers
        self.cache = cache

    def render(
        self,
        text: str,
        settings: dict,
        tags: list,
        voice: str = "",
        delivery: str = "",
        api_key: str = "",
        take: int = 0,
    ) -> dict:
        # api_key is whose account pays (bring-your-own-key); it never enters
        # the cache key — the same render is the same audio for everyone.
        # `take` is the performance loop's re-roll salt: non-zero takes render
        # fresh instead of replaying take 0 from the cache.
        # Providers can declare which voices they speak (a local clone must
        # never reach a cloud engine; a cloud voice never reaches the clone
        # engine). No declaration means "any voice".
        def handles(provider) -> bool:
            return getattr(provider, "supports", lambda v: True)(voice)

        # 1. If any provider already has this exact render cached, reuse it.
        for provider in self.providers:
            if not handles(provider):
                continue
            key = self.cache.key(provider.name, settings, text, tags, voice, delivery, take)
            if self.cache.has(key, provider.ext):
                return {
                    "audio_id": key,
                    "ext": provider.ext,
                    "engine": provider.name,
                    "cached": True,
                }

        # 2. Cache miss: try each provider (with one retry) until one succeeds.
        for provider in self.providers:
            if not handles(provider):
                continue
            audio = None
            for attempt in range(2):
                try:
                    audio = provider.synthesize(text, settings, tags, voice, delivery, api_key)
                    break
                except Exception:
                    if attempt == 0:
                        time.sleep(RETRY_DELAY_SECONDS)  # let a blip pass, retry once
            if audio is None:
                continue  # truly down/out of quota — try the next provider
            key = self.cache.key(provider.name, settings, text, tags, voice, delivery, take)
            self.cache.write(key, provider.ext, audio)
            return {
                "audio_id": key,
                "ext": provider.ext,
                "engine": provider.name,
                "cached": False,
            }

        raise RuntimeError("all voice providers failed")
