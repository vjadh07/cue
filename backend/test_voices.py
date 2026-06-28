"""Tests for usable_voices — picking which ElevenLabs voices the dropdown should
offer. On the free tier the API can only use your own/premade voices; shared
'professional' library voices return 402, so they must be left out."""

from voices import usable_voices


def test_keeps_premade_and_owned_drops_library():
    raw = [
        {"voice_id": "a", "name": "George", "category": "premade", "labels": {"description": "warm"}},
        {"voice_id": "b", "name": "Hope", "category": "professional", "labels": {"description": "bubbly"}},
        {"voice_id": "c", "name": "MyClone", "category": "cloned", "labels": {}},
    ]
    assert [v["id"] for v in usable_voices(raw)] == ["a", "c"]  # library voice dropped


def test_maps_id_name_description():
    raw = [{"voice_id": "a", "name": "George", "category": "premade", "labels": {"description": "warm storyteller"}}]
    assert usable_voices(raw) == [{"id": "a", "name": "George", "description": "warm storyteller"}]


def test_falls_back_to_use_case_then_empty_for_description():
    raw = [
        {"voice_id": "a", "name": "A", "category": "premade", "labels": {"use_case": "narration"}},
        {"voice_id": "b", "name": "B", "category": "premade", "labels": {}},
    ]
    out = usable_voices(raw)
    assert out[0]["description"] == "narration"
    assert out[1]["description"] == ""


def test_missing_name_falls_back_to_id():
    assert usable_voices([{"voice_id": "x", "category": "premade"}]) == [
        {"id": "x", "name": "x", "description": ""}
    ]
