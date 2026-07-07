"""Tests for the local voice engine's pure parts: which voices it accepts,
how Cue's direction maps onto its expression knobs, and how a delivery is
prepared for an engine that would read [tags] out loud. The model itself is
exercised in the live smoke test, not here — these stay fast and offline."""

from providers import ChatterboxProvider, ElevenLabsProvider, PiperProvider, expression_controls, strip_tags


def test_only_the_local_engine_speaks_clones():
    assert ChatterboxProvider().supports("local:abc") is True
    assert ChatterboxProvider().supports("JBFqnCBsd6RMkjVDRZzb") is False
    assert ElevenLabsProvider().supports("local:abc") is False
    assert ElevenLabsProvider().supports("JBFqnCBsd6RMkjVDRZzb") is True
    assert PiperProvider().supports("local:abc") is False
    assert PiperProvider().supports("") is True


def test_tags_are_stripped_but_the_performance_punctuation_stays():
    assert strip_tags("[furious] STOP [yelling] IT!") == "STOP IT!"
    assert strip_tags("[whispers] It's… fine.") == "It's… fine."
    assert strip_tags("no tags here") == "no tags here"


def test_direction_maps_onto_expression_knobs():
    # A raw, unhinged read: low stability, high style -> wild + loose.
    wild = expression_controls({"stability": 0.1, "style": 0.9, "speed": 1.0, "volume": 1.0})
    # A flat, steady read: high stability, low style -> calm + steady.
    calm = expression_controls({"stability": 0.9, "style": 0.1, "speed": 1.0, "volume": 1.0})

    assert wild["exaggeration"] > calm["exaggeration"]
    assert wild["cfg_weight"] < calm["cfg_weight"]
    # Both knobs stay in the identity-safe band: high exaggeration makes the
    # clone sound generically expressive instead of like the actual person, so
    # protecting likeness caps the range far below the model's max.
    for knobs in (wild, calm):
        assert 0.3 <= knobs["exaggeration"] <= 0.75
        assert 0.3 <= knobs["cfg_weight"] <= 0.6


def test_even_the_most_dramatic_direction_protects_likeness():
    loudest = expression_controls({"stability": 0.0, "style": 1.0, "speed": 1.0, "volume": 1.0})
    # Never past ~0.75 — beyond that the voice stops sounding like the user.
    assert loudest["exaggeration"] <= 0.75


def test_unknown_clone_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr("clones.CLONES_DIR", tmp_path)
    try:
        ChatterboxProvider().synthesize("hi", {"stability": 0.5, "style": 0.5, "speed": 1, "volume": 1}, [], voice="local:feedfeedfeedfeed")
        assert False, "expected RuntimeError for an unregistered clone"
    except RuntimeError:
        pass
