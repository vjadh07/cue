"""Tests for per-IP rate limiting — what keeps a public deploy's brain quota
from being drained by one stranger. BYOK already protects the host's
ElevenLabs credits, but /direct, /perform, /retake, /chat and /speak all
spend the HOST's Groq budget, and the clone endpoint burns real compute.
The limiter answers 429 with a Retry-After, the same honest contract Groq
gives us. In-memory and per-process on purpose: Cue deploys as one process.
"""

import pytest
from fastapi.testclient import TestClient

import main
from limiter import RateLimiter


def client():
    return TestClient(main.app)


# --- the limiter itself: a sliding window per key ---


def test_allows_up_to_the_limit():
    limiter = RateLimiter(limit=3, window_seconds=60)
    assert [limiter.allow("ip", now=t)[0] for t in (0, 1, 2)] == [True, True, True]


def test_blocks_past_the_limit_and_says_how_long():
    limiter = RateLimiter(limit=2, window_seconds=60)
    limiter.allow("ip", now=0)
    limiter.allow("ip", now=10)
    allowed, retry_after = limiter.allow("ip", now=20)
    assert allowed is False
    assert retry_after == 40  # the oldest call (t=0) leaves the window at t=60


def test_the_window_slides():
    limiter = RateLimiter(limit=2, window_seconds=60)
    limiter.allow("ip", now=0)
    limiter.allow("ip", now=10)
    assert limiter.allow("ip", now=61)[0] is True  # t=0 has aged out


def test_keys_are_independent():
    limiter = RateLimiter(limit=1, window_seconds=60)
    assert limiter.allow("alice", now=0)[0] is True
    assert limiter.allow("bob", now=0)[0] is True
    assert limiter.allow("alice", now=1)[0] is False


def test_a_blocked_call_does_not_consume_budget():
    limiter = RateLimiter(limit=1, window_seconds=60)
    limiter.allow("ip", now=0)
    limiter.allow("ip", now=1)  # blocked
    assert limiter.allow("ip", now=61)[0] is True  # only t=0 counted


# --- the endpoints: brain bucket and clone bucket ---


@pytest.fixture
def strict(monkeypatch):
    """Rate limits ON with a tiny budget, isolated to this test."""
    monkeypatch.setattr(main, "RATE_LIMITS_ENABLED", True)
    monkeypatch.setattr(main, "brain_limiter", RateLimiter(limit=2, window_seconds=60))
    monkeypatch.setattr(main, "clone_limiter", RateLimiter(limit=1, window_seconds=60))


def test_the_brain_bucket_answers_429_past_the_budget(strict):
    c = client()
    for _ in range(2):
        c.post("/direct", json={"script": "", "direction": ""})  # any outcome counts
    response = c.post("/direct", json={"script": "Hi.", "direction": "warm"})
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0


def test_brain_endpoints_share_one_bucket(strict):
    c = client()
    c.post("/direct", json={"script": "", "direction": ""})
    c.post("/chat", json={"messages": []})
    assert c.post("/retake", json={"script": ["Hi."], "index": 0, "note": "x"}).status_code == 429


def test_the_clone_bucket_is_separate(strict):
    c = client()
    for _ in range(2):
        c.post("/direct", json={"script": "", "direction": ""})  # brain budget spent
    # The clone bucket still has room: this must NOT be a 429 (it fails
    # later on consent validation instead, which is the point).
    response = c.post(
        "/voice/clone",
        data={"name": "me", "consent": "false"},
        files={"files": ("r.webm", b"x", "audio/webm")},
    )
    assert response.status_code == 400


def test_different_visitors_have_different_budgets(strict):
    c = client()
    for _ in range(2):
        c.post("/direct", json={"script": "", "direction": ""})
    other = c.post(
        "/direct",
        json={"script": "Hi.", "direction": ""},
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert other.status_code != 429  # a proxy-forwarded visitor is their own key


def test_limits_are_off_in_the_test_suite_by_default():
    # conftest.py flips the kill switch so the hundreds of requests the rest
    # of this suite makes never trip a shared budget.
    assert main.RATE_LIMITS_ENABLED is False


def test_the_kill_switch_only_answers_to_off():
    assert main.rate_limits_enabled({"CUE_RATE_LIMITS": "off"}) is False
    assert main.rate_limits_enabled({"CUE_RATE_LIMITS": "on"}) is True
    assert main.rate_limits_enabled({}) is True  # protection is the default
