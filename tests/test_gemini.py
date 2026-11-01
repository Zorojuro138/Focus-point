from __future__ import annotations

import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from focuspilot.ai.gemini import BrowserPage, GeminiClient, GeminiError, sanitize_page_url


def test_page_url_drops_query_fragment_and_credentials() -> None:
    assert (
        sanitize_page_url("https://person:secret@example.com/course/lesson?token=private#part")
        == "https://example.com/course/lesson"
    )


def test_page_url_rejects_non_web_and_invalid_input() -> None:
    assert sanitize_page_url("chrome://settings") == ""
    assert sanitize_page_url("not a url") == ""
    assert sanitize_page_url("https://example.com") == "https://example.com"


def test_classifier_sends_minimal_page_context_and_validates_response(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        response = {
            "candidates": [
                {"content": {"parts": [{"text": '{"label":"on_task","reason":"Matches DSA."}'}]}}
            ]
        }
        return BytesIO(json.dumps(response).encode())

    monkeypatch.setattr("focuspilot.ai.gemini.urlopen", fake_urlopen)
    result = GeminiClient("test-key").classify_page(
        goal="Study DSA",
        page=BrowserPage(
            title="Tree lesson", url="https://youtube.com/watch?v=secret&token=private"
        ),
    )

    body = json.loads(captured["request"].data)
    prompt = body["contents"][0]["parts"][0]["text"]
    assert captured["request"].get_header("X-goog-api-key") == "test-key"
    assert "https://youtube.com/watch" in prompt
    assert "secret" not in prompt and "private" not in prompt
    assert result.label == "on_task"
    assert result.reason == "Matches DSA."


def test_free_tier_limit_has_clear_fallback_message(monkeypatch) -> None:
    def rate_limited(*_args, **_kwargs):
        raise HTTPError("https://example.invalid", 429, "quota", {}, None)

    monkeypatch.setattr("focuspilot.ai.gemini.urlopen", rate_limited)
    with pytest.raises(GeminiError, match="free-tier limit"):
        GeminiClient("test-key").classify_page(
            goal="Study", page=BrowserPage(title="Lesson", url="https://example.com/lesson")
        )
