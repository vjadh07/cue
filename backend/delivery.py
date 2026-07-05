"""The delivery guardrail.

The brain is allowed to rewrite a line as a performance — inline audio tags at
the emotional beats, ellipses for hesitation, CAPS for emphasis — but it is
NEVER allowed to change the user's words. verify_delivery enforces that: it
strips the tags and all punctuation/casing from both versions and demands the
word sequences match exactly. Anything else (added words, dropped words,
respellings, off-whitelist tags that the voice would read out loud) rejects
the delivery, and the caller falls back to the plain line."""

import re

from settings import TAG_WHITELIST

_TAG_RE = re.compile(r"\[([^\[\]]+)\]")
_WORD_RE = re.compile(r"[a-z0-9']+")


def _words(text: str) -> list[str]:
    """The bare spoken words: lowercased, punctuation and casing gone."""
    return [w.strip("'") for w in _WORD_RE.findall(text.lower()) if w.strip("'")]


def verify_delivery(original: str, delivery: str) -> str | None:
    """Return the delivery if it speaks EXACTLY the original's words (tags and
    expressive punctuation aside), else None."""
    if not delivery or not delivery.strip():
        return None

    # Every bracketed tag must be on the whitelist — v3 reads unknown ones aloud.
    tags = _TAG_RE.findall(delivery)
    if any(tag.strip().lower() not in TAG_WHITELIST for tag in tags):
        return None

    spoken = _words(_TAG_RE.sub(" ", delivery))
    if not spoken or spoken != _words(original):
        return None
    return delivery
