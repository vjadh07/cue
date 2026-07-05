"""Tests for verify_delivery — the guardrail that lets the brain rewrite a line
as a PERFORMANCE (inline audio tags, expressive punctuation) while guaranteeing
the spoken words are exactly the user's words. If anything was added, removed,
or changed, the delivery is rejected and the caller falls back to plain text."""

from delivery import verify_delivery


def test_identical_text_passes():
    assert verify_delivery("We did it.", "We did it.") == "We did it."


def test_inline_tags_punctuation_and_caps_pass():
    original = "We did it. We actually did it."
    delivery = "We did it [sighs]… we ACTUALLY did it."
    assert verify_delivery(original, delivery) == delivery


def test_leading_tag_and_multiword_tag_pass():
    assert verify_delivery("Run.", "[terrified] RUN!") == "[terrified] RUN!"
    assert (
        verify_delivery("I told you.", "[voice breaking] I told you…")
        == "[voice breaking] I told you…"
    )


def test_added_word_is_rejected():
    assert verify_delivery("We did it.", "We really did it.") is None


def test_removed_word_is_rejected():
    assert verify_delivery("We actually did it.", "We did it.") is None


def test_reordered_words_are_rejected():
    assert verify_delivery("it was you", "you was it") is None


def test_changed_spelling_is_rejected():
    assert verify_delivery("Don't stop.", "Dont stop.") is None


def test_unknown_tag_is_rejected():
    # An off-whitelist tag would be read out loud by the voice — reject.
    assert verify_delivery("We did it.", "[explodes] We did it.") is None


def test_empty_or_blank_delivery_is_rejected():
    assert verify_delivery("We did it.", "") is None
    assert verify_delivery("We did it.", "[sighs] …") is None  # tags but no words


def test_apostrophes_survive():
    assert verify_delivery("don't you dare", "Don't… you DARE") == "Don't… you DARE"
