"""Tests for BrainEngine (fallback across brains) and KeywordBrain (the
deterministic final fallback). Fake brains exercise the orchestration without
calling a real LLM.
"""

import json

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
        self.directions = []  # the direction string passed on each call

    def interpret(self, line, direction, script=None, index=0):
        self.calls += 1
        self.seen.append((script, index))
        self.directions.append(direction)
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


def test_interpret_script_folds_per_line_hints_into_the_direction():
    """A screenplay parenthetical ((quietly)) rides only its own line's
    direction; lines without hints get the plain global direction."""
    a = FakeBrain("groq")
    BrainEngine([a]).interpret_script(["A", "B"], "warm", hints=[None, "quietly"])
    directions = sorted(a.directions)
    assert directions == sorted(["warm", "warm. This line: quietly"])


def test_interpret_script_hint_alone_still_directs():
    a = FakeBrain("groq")
    BrainEngine([a]).interpret_script(["A"], "", hints=["beat, then softer"])
    assert a.directions == ["This line: beat, then softer"]


# --- batch mode: long scripts go to the brain in chunks, not line by line ---
# Per-line-with-full-script costs O(n^2) tokens and trips Groq's free tier
# around 40-60 lines. Past BATCH_THRESHOLD the engine asks for BATCH_SIZE
# plans per call; short scripts keep the per-line path (best quality).


class FakeBatchBrain(FakeBrain):
    def __init__(self, name, fail=False, fail_batch=False):
        super().__init__(name, fail)
        self.fail_batch = fail_batch
        self.batch_calls = []  # (batch, start, direction, hints) per call

    def interpret_batch(self, batch, direction, script=None, start=0, hints=None):
        self.batch_calls.append((list(batch), start, direction, hints))
        if self.fail_batch:
            raise RuntimeError(f"{self.name} batch down")
        return [
            {"settings": S, "tags": [], "notes": f"plan {start + i}", "delivery": None}
            for i in range(len(batch))
        ]


LONG = [f"Line {i}." for i in range(100)]


def test_short_scripts_keep_the_per_line_path():
    a = FakeBatchBrain("groq")
    results = BrainEngine([a]).interpret_script(["A", "B", "C"], "warm")
    assert len(results) == 3
    assert a.batch_calls == []
    assert a.calls == 3


def test_long_scripts_go_to_the_brain_in_batches():
    a = FakeBatchBrain("groq")
    results = BrainEngine([a]).interpret_script(LONG, "build slowly")
    assert len(results) == 100
    assert a.calls == 0  # not one single-line call
    assert len(a.batch_calls) == 10
    assert all(len(batch) == 10 for batch, *_ in a.batch_calls)
    # Order is preserved end to end, whatever order the chunks ran in.
    assert [r["notes"] for r in results] == [f"plan {i}" for i in range(100)]
    assert all(r["brain"] == "groq" for r in results)


def test_batch_mode_handles_a_partial_last_chunk():
    a = FakeBatchBrain("groq")
    results = BrainEngine([a]).interpret_script(LONG[:45], "warm")
    assert len(results) == 45
    assert [len(batch) for batch, *_ in a.batch_calls] == [10, 10, 10, 10, 5]


def test_batch_mode_passes_start_and_hints_through():
    a = FakeBatchBrain("groq")
    hints = [None] * 45
    hints[40] = "quietly"
    BrainEngine([a]).interpret_script(LONG[:45], "warm", hints=hints)
    starts = sorted(start for _, start, *_ in a.batch_calls)
    assert starts == [0, 10, 20, 30, 40]
    # Every batch call sees the hints list; the prompt folds in its own.
    assert all(h == hints for *_, h in a.batch_calls)


def test_batch_failure_falls_to_the_next_batch_brain():
    a = FakeBatchBrain("groq", fail_batch=True)
    b = FakeBatchBrain("ollama")
    results = BrainEngine([a, b]).interpret_script(LONG[:45], "warm")
    assert all(r["brain"] == "ollama" for r in results)
    assert len(b.batch_calls) == 5


def test_batch_failure_everywhere_falls_back_per_line():
    # No brain can batch (or all batch calls fail): every line still gets a
    # plan through the per-line path, so a long script never dies.
    a = FakeBatchBrain("groq", fail_batch=True)
    results = BrainEngine([a]).interpret_script(LONG[:45], "warm")
    assert len(results) == 45
    assert a.calls == 45  # per-line fallback did the work
    assert all(r["brain"] == "groq" for r in results)


def test_per_line_fallback_in_batch_mode_uses_a_window_not_the_whole_script():
    # The whole point of batch mode is escaping O(n^2); the fallback must not
    # sneak it back in by passing all 45 lines on every single-line call.
    a = FakeBatchBrain("groq", fail_batch=True)
    BrainEngine([a]).interpret_script(LONG[:45], "warm")
    assert all(script is not None and len(script) <= 11 for script, _ in a.seen)


# --- _build_batch_messages: the batched director prompt ---


def test_build_batch_messages_shows_a_window_not_the_whole_script():
    from brains import _build_batch_messages

    user = _build_batch_messages(LONG, "build slowly", start=50, count=10)[-1]["content"]
    assert "Line 50." in user  # the batch itself (0-based line 50)
    assert "Line 46." in user and "Line 64." in user  # the window around it
    assert "Line 0." not in user and "Line 99." not in user  # not the whole script
    assert "lines 51-60" in user  # 1-based, what to perform
    assert "100 lines" in user  # arc position: how big the whole script is
    assert "build slowly" in user
    assert '"plans"' in user  # the reply contract


def test_build_batch_messages_lists_each_line_once():
    # Token budget: the free tier meters tokens per minute, so the batch
    # prompt must not carry the performed lines twice (once in the excerpt,
    # once in a perform list). Marked lines in one excerpt, that's it.
    from brains import _build_batch_messages

    user = _build_batch_messages(LONG, "warm", start=50, count=10)[-1]["content"]
    assert user.count("Line 50.") == 1


def test_build_batch_messages_skips_the_few_shot_anchors():
    # Same budget: the two few-shot exchanges cost hundreds of tokens per
    # call. The system brief alone carries the format in batch mode.
    from brains import _build_batch_messages

    messages = _build_batch_messages(LONG, "warm", start=0, count=10)
    assert len(messages) == 2  # system + user, no anchors
    assert messages[0]["role"] == "system"


def test_build_batch_messages_folds_hints_into_their_own_lines():
    from brains import _build_batch_messages

    hints = [None] * 20
    hints[12] = "through gritted teeth"
    user = _build_batch_messages(LONG[:20], "warm", start=10, count=10, hints=hints)[-1]["content"]
    assert "through gritted teeth" in user


# --- _parse_batch_json: the batched reply, cleaned plan by plan ---


def test_parse_batch_json_cleans_every_plan():
    from brains import _parse_batch_json

    content = json.dumps(
        {
            "plans": [
                {"delivery": "[sighs] One.", "tags": ["sighs"], "stability": 0.8, "notes": "weary"},
                {"delivery": "TWO!", "tags": ["banana"], "stability": 9.0, "notes": "x" * 200},
            ]
        }
    )
    plans = _parse_batch_json(content, ["One.", "Two!"])
    assert plans[0]["delivery"] == "[sighs] One."
    assert plans[0]["settings"]["stability"] == 0.8
    assert plans[1]["tags"] == []  # off-whitelist tag dropped
    assert plans[1]["settings"]["stability"] == 1.0  # clamped
    assert len(plans[1]["notes"]) == 80


def test_parse_batch_json_rejects_a_cheating_delivery_per_plan():
    from brains import _parse_batch_json

    content = json.dumps(
        {
            "plans": [
                {"delivery": "Totally different words."},
                {"delivery": "Two, exactly."},
            ]
        }
    )
    plans = _parse_batch_json(content, ["One.", "Two, exactly."])
    assert plans[0]["delivery"] is None  # words changed -> dropped
    assert plans[1]["delivery"] == "Two, exactly."


def test_parse_batch_json_wrong_count_raises():
    from brains import _parse_batch_json

    content = json.dumps({"plans": [{"notes": "only one"}]})
    try:
        _parse_batch_json(content, ["One.", "Two."])
        assert False, "expected a count mismatch to raise"
    except ValueError:
        pass


# --- GroqBrain 429 handling: wait out the rate window, don't drop the brain ---
# The free tier meters tokens per minute. A long script's batches can exhaust
# the window mid-run; giving up instantly demotes half the script to the
# keyword brain and the arc goes flat. A 429 with Retry-After means "worth
# waiting": sleep it out (bounded) and try again before falling back.


class FakeResponse:
    def __init__(self, status_code, content="", headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _plan_json():
    return '{"stability": 0.2, "style": 0.7, "speed": 1.0, "volume": 1.0, "notes": "hot"}'


def test_groq_waits_out_a_429_then_succeeds(monkeypatch):
    from brains import GroqBrain

    responses = [
        FakeResponse(429, headers={"retry-after": "1.5"}),
        FakeResponse(200, _plan_json()),
    ]
    sleeps = []
    monkeypatch.setattr("brains.httpx.post", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr("brains.time.sleep", lambda s: sleeps.append(s))
    brain = GroqBrain()
    brain.api_key = "k"

    result = brain.interpret("Stop.", "furious")

    assert result["settings"]["stability"] == 0.2
    assert sleeps == [1.5]  # honored the server's own retry hint


def test_groq_gives_up_after_one_bounded_wait(monkeypatch):
    # ONE wait per call, then a typed failure. More retries here compound
    # catastrophically: a failed batch falls back to 10 per-line calls, and
    # if each of those also sleeps out 429s, a long script hangs for many
    # minutes (live-observed). The window being empty is the chain's problem.
    from brains import GroqBrain, RateLimited

    calls = []
    monkeypatch.setattr(
        "brains.httpx.post",
        lambda *a, **k: calls.append(1) or FakeResponse(429, headers={"retry-after": "1"}),
    )
    monkeypatch.setattr("brains.time.sleep", lambda s: None)
    brain = GroqBrain()
    brain.api_key = "k"

    try:
        brain.interpret("Stop.", "furious")
        assert False, "expected the final 429 to raise RateLimited"
    except RateLimited:
        pass
    assert len(calls) == 2  # one try + one waited retry, then hand off


def test_groq_fails_fast_when_the_wait_is_hopeless(monkeypatch):
    # A retry-after in the hundreds of seconds is the DAILY token cap, not
    # the minute window (live-observed: 900-1026s). No user waits that out;
    # napping 30s first just delays the fallback. Hand off immediately.
    from brains import GroqBrain, RateLimited

    calls = []
    sleeps = []
    monkeypatch.setattr(
        "brains.httpx.post",
        lambda *a, **k: calls.append(1) or FakeResponse(429, headers={"retry-after": "993"}),
    )
    monkeypatch.setattr("brains.time.sleep", lambda s: sleeps.append(s))
    brain = GroqBrain()
    brain.api_key = "k"

    try:
        brain.interpret("Stop.", "furious")
        assert False, "expected RateLimited"
    except RateLimited:
        pass
    assert calls == [1]  # one attempt, no retry against a wall
    assert sleeps == []  # and no pointless nap


def test_groq_honors_a_precise_waitable_retry_after(monkeypatch):
    # Within the minute-window regime the server's own number is exact;
    # sleeping less just guarantees a second 429.
    from brains import GroqBrain

    responses = [
        FakeResponse(429, headers={"retry-after": "45"}),
        FakeResponse(200, _plan_json()),
    ]
    sleeps = []
    monkeypatch.setattr("brains.httpx.post", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr("brains.time.sleep", lambda s: sleeps.append(s))
    brain = GroqBrain()
    brain.api_key = "k"

    brain.interpret("Stop.", "furious")

    assert sleeps == [45.0]


def test_batch_fallback_skips_the_brain_that_rate_limited_it(monkeypatch):
    # When the batch died on an exhausted rate window, hammering the same
    # brain once per line is pure amplification: skip it for this chunk and
    # let the rest of the chain do the work.
    from brains import RateLimited

    class LimitedBrain(FakeBatchBrain):
        def interpret_batch(self, *a, **k):
            raise RateLimited("window empty")

    a = LimitedBrain("groq")
    b = FakeBrain("keyword")
    results = BrainEngine([a, b]).interpret_script(LONG[:45], "warm")

    assert len(results) == 45
    assert all(r["brain"] == "keyword" for r in results)
    assert a.calls == 0  # not one per-line call against the empty window


def test_groq_does_not_retry_other_errors(monkeypatch):
    from brains import GroqBrain

    calls = []
    monkeypatch.setattr(
        "brains.httpx.post", lambda *a, **k: calls.append(1) or FakeResponse(500)
    )
    brain = GroqBrain()
    brain.api_key = "k"

    try:
        brain.interpret("Stop.", "furious")
        assert False, "expected a server error to raise immediately"
    except Exception:
        pass
    assert len(calls) == 1  # a 500 is not a rate window; fail fast to Ollama


def test_groq_batch_rides_the_same_retry(monkeypatch):
    from brains import GroqBrain

    plans = '{"plans": [{"notes": "a"}, {"notes": "b"}]}'
    responses = [FakeResponse(429, headers={"retry-after": "0.5"}), FakeResponse(200, plans)]
    sleeps = []
    monkeypatch.setattr("brains.httpx.post", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr("brains.time.sleep", lambda s: sleeps.append(s))
    brain = GroqBrain()
    brain.api_key = "k"

    result = brain.interpret_batch(["One.", "Two."], "warm", script=["One.", "Two."], start=0)

    assert len(result) == 2
    assert sleeps == [0.5]


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
