"""Voice list helpers — deciding which ElevenLabs voices the picker should offer.

On the free tier the API can only use your own / premade voices. Shared
'professional' library voices (the ones you add from Explore) return 402
"paid_plan_required", which would make the app silently fall back to the wrong
voice (Piper). So we leave those out of the dropdown rather than offer a voice
that can't actually be rendered.
"""

# Categories the free-tier API can render: ElevenLabs' premade voices and your
# own instant clones / designed voices. ('professional' = shared library or pro
# clones, which need a paid plan via the API.)
USABLE_CATEGORIES = {"premade", "cloned", "generated"}


def usable_voices(raw: list) -> list[dict]:
    """Filter the raw /v1/voices list to the ones the dropdown can actually use,
    trimmed to {id, name, description}."""
    result = []
    for v in raw:
        if v.get("category") not in USABLE_CATEGORIES:
            continue
        labels = v.get("labels") or {}
        description = labels.get("description") or labels.get("use_case") or ""
        result.append(
            {"id": v["voice_id"], "name": v.get("name", v["voice_id"]), "description": description}
        )
    return result
