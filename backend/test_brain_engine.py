"""Tests for BrainEngine (fallback across brains) and KeywordBrain (the
deterministic final fallback). Fake brains exercise the orchestration without
calling a real LLM.
"""

from brains import BrainEngine, KeywordBrain, _build_messages, _parse_director_json
from settings import DEFAULTS

S = {"stability": 0.4, "style": 0.6, "speed": 1.1, "volume": 0.9}


# --- _parse_director_json: the shared LLM-reply parser used by Ollama + Groq ---


def test_parse_director_json_builds_clean_result():
    content = (
        '{"tags": ["sarcastic", "sighs"], "stability": 0.3, "style": 0.7, '
        '"speed": 1.1, "volume": 0.9, "notes": "smug, dry"}'
    )
    result = _parse_director_json(content)
    assert result["settings"] == {"stability": 0.3, "style": 0.7, "speed": 1.1, "volume": 0.9}
    assert result["tags"] == ["sarcastic", "sighs"]
    assert result["notes"] == "smug, dry"


def test_parse_director_json_filters_unknown_tags_and_clamps():
    # "banana" isn't whitelisted; speed is out of range; stability is missing.
    content = '{"tags": ["sarcastic", "banana", "EXCITED"], "speed": 5.0, "notes": "x"}'
    result = _parse_director_json(content)
    assert result["tags"] == ["sarcastic", "excited"]  # banana dropped, case-normalized
    assert result["settings"]["speed"] == 1.2  # clamped to the supported max
    assert result["settings"]["stability"] == 0.5  # missing -> default


def test_parse_director_json_truncates_long_notes():
    content = '{"notes": "' + "x" * 200 + '"}'
    result = _parse_director_json(content)
    assert len(result["notes"]) == 80


def test_parse_director_json_keeps_a_valid_delivery():
    content = '{"delivery": "We did it [sighs]… we ACTUALLY did it.", "tags": ["sighs"]}'
    result = _parse_director_json(content, line="We did it. We actually did it.")
    assert result["delivery"] == "We did it [sighs]… we ACTUALLY did it."


def test_parse_director_json_rejects_a_cheating_delivery():
    # The model changed the words — the delivery must be dropped, not spoken.
    content = '{"delivery": "We totally did it!", "tags": []}'
    result = _parse_director_json(content, line="We did it.")
    assert result["delivery"] is None


def test_parse_director_json_without_line_has_no_delivery():
    result = _parse_director_json('{"delivery": "Hi.", "tags": []}')
    assert result["delivery"] is None


class FakeBrain:
    def __init__(self, name, fail=False):
        self.name = name
        self.fail = fail
        self.calls = 0
        self.seen = []  # (script, index) passed on each call

    def interpret(self, line, direction, script=None, index=0):
        self.calls += 1
        self.seen.append((script, index))
        if self.fail:
            raise RuntimeError(f"{self.name} down")
        return {"settings": S, "tags": ["sarcastic"], "notes": f"{self.name} read"}


def test_uses_first_brain_when_it_works():
    a, b = FakeBrain("groq"), FakeBrain("ollama")
    result = BrainEngine([a, b]).interpret("hi", "warm")
    assert result["brain"] == "groq"
    assert result["settings"] == S
    assert result["tags"] == ["sarcastic"]
    assert a.calls == 1
    assert b.calls == 0


def test_falls_back_when_first_brain_fails():
    a, b = FakeBrain("groq", fail=True), FakeBrain("ollama")
    result = BrainEngine([a, b]).interpret("hi", "warm")
    assert result["brain"] == "ollama"
    assert a.calls == 1
    assert b.calls == 1


def test_all_brains_failing_returns_neutral():
    result = BrainEngine([FakeBrain("groq", fail=True), FakeBrain("ollama", fail=True)]).interpret(
        "hi", "warm"
    )
    assert result["settings"] == DEFAULTS
    assert result["tags"] == []
    assert result["brain"] == "none"


def test_keyword_brain_maps_slow_to_speed():
    result = KeywordBrain().interpret("hi", "slow")
    assert result["settings"]["speed"] == 0.7
    assert "slow" in result["notes"]


def test_keyword_brain_neutral_when_no_keywords():
    result = KeywordBrain().interpret("hi", "")
    assert result["settings"] == DEFAULTS
    assert result["notes"] == ""


# --- _build_messages: single-line vs whole-script context ---


def test_build_messages_single_line_has_no_script_block():
    user = _build_messages("Hello.", "warmly")[-1]["content"]
    assert "Hello." in user
    assert "warmly" in user
    assert "script" not in user.lower()  # no script context in single-line mode


def test_build_messages_with_script_includes_all_lines_and_marks_target():
    lines = ["One.", "Two.", "Three."]
    user = _build_messages("Two.", "build up", script=lines, index=1)[-1]["content"]
    assert "One." in user and "Two." in user and "Three." in user
    assert "build up" in user
    assert "line 2" in user  # target line marked 1-based


# --- interpret_script: one direction across many lines ---


def test_interpret_script_returns_one_result_per_line():
    a = FakeBrain("groq")
    results = BrainEngine([a]).interpret_script(["A", "B", "C"], "dramatic")
    assert len(results) == 3
    assert all(r["brain"] == "groq" for r in results)
    assert a.calls == 3


def test_interpret_script_passes_whole_script_and_index_each_call():
    a = FakeBrain("groq")
    lines = ["A", "B"]
    BrainEngine([a]).interpret_script(lines, "warm")
    # Lines are interpreted concurrently, so compare regardless of call order.
    assert sorted(a.seen, key=lambda s: s[1]) == [(lines, 0), (lines, 1)]


def test_interpret_script_falls_back_per_line():
    a, b = FakeBrain("groq", fail=True), FakeBrain("ollama")
    results = BrainEngine([a, b]).interpret_script(["A", "B"], "warm")
    assert all(r["brain"] == "ollama" for r in results)
    assert a.calls == 2 and b.calls == 2


# --- chat: the writer's room (only LLM brains can write) ---


class FakeWriterBrain(FakeBrain):
    def chat(self, messages):
        if self.fail:
            raise RuntimeError(f"{self.name} down")
        return {"message": f"drafted by {self.name}", "script": "ALICE: Hi."}


def test_chat_uses_first_writing_brain():
    a, b = FakeWriterBrain("groq"), FakeWriterBrain("ollama")
    result = BrainEngine([a, b]).chat([{"role": "user", "content": "a storm"}])
    assert result["message"] == "drafted by groq"
    assert result["script"] == "ALICE: Hi."


def test_chat_skips_brains_that_cannot_write():
    # KeywordBrain-style brains have no chat(); the engine must skip them.
    keyword = FakeBrain("keyword")
    writer = FakeWriterBrain("ollama")
    assert BrainEngine([keyword, writer]).chat([{"role": "user", "content": "hi"}])["script"]


def test_chat_falls_back_then_raises_when_no_writer_works():
    a, b = FakeWriterBrain("groq", fail=True), FakeWriterBrain("ollama")
    assert BrainEngine([a, b]).chat([{"role": "user", "content": "hi"}])["message"]
    try:
        BrainEngine([FakeWriterBrain("groq", fail=True), FakeBrain("keyword")]).chat(
            [{"role": "user", "content": "hi"}]
        )
        assert False, "expected an error when no brain can write"
    except RuntimeError:
        pass


# --- _parse_writer_json: the writer's structured reply ---


def test_parse_writer_json_extracts_message_and_script():
    from brains import _parse_writer_json

    raw = '{"message": "Here you go.", "script": "```\\nALICE: Hi.\\n\\nBOB: Hey.\\n```"}'
    result = _parse_writer_json(raw)
    assert result["message"] == "Here you go."
    assert result["script"] == "ALICE: Hi.\nBOB: Hey."  # cleaned like any generated script


def test_parse_writer_json_script_absent_or_empty_is_none():
    from brains import _parse_writer_json

    assert _parse_writer_json('{"message": "What tone?"}')["script"] is None
    assert _parse_writer_json('{"message": "hm", "script": ""}')["script"] is None
