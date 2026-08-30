from unittest.mock import MagicMock, patch

import pytest
import requests

from config import Config
from clients.ninerouter_client import NineRouterClient
from clients.openrouter_client import OpenRouterClient


@pytest.fixture(autouse=True)
def _nine_router_config():
    Config.NINEROUTER_API_KEY = "test-key"
    Config.MAX_RETRIES = 2
    Config.TIMEOUT = 5
    yield


def test_success_returns_data():
    def fake_post(url, json, headers, timeout, verify):
        resp = MagicMock()
        resp.ok = True
        resp.status_code = 200
        resp.json.return_value = {
            "model": "bg/gpt-4o-mini",
            "choices": [{"finish_reason": "stop", "message": {"content": '{"ok": true}'}}],
        }
        return resp

    client = NineRouterClient()
    with patch("requests.post", side_effect=fake_post):
        data = client.chat([{"role": "user", "content": "hi"}])
    assert data["choices"][0]["message"]["content"] == '{"ok": true}'


def test_401_invalid_api_key_raises_with_status_in_message():
    """Reproduces the exact failure caused by a malformed .env value
    (an old OPENROUTER key's 'sk-or-v1-' prefix glued onto the real
    local 9Router key)."""
    def fake_post_401(url, json, headers, timeout, verify):
        resp = MagicMock()
        resp.ok = False
        resp.status_code = 401
        resp.text = '{"error":{"message":"Invalid API key","type":"authentication_error"}}'
        return resp

    client = NineRouterClient()
    with patch("requests.post", side_effect=fake_post_401):
        with pytest.raises(RuntimeError, match="401"):
            client.chat([{"role": "user", "content": "hi"}])


def test_reasoning_only_response_is_retried_then_raises():
    """finish_reason=length with content=null (a reasoning model that
    burned its whole budget on <think> and never got to content) must
    not be treated as success."""
    def fake_post(url, json, headers, timeout, verify):
        resp = MagicMock()
        resp.ok = True
        resp.status_code = 200
        resp.json.return_value = {
            "model": "cf/@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",
            "choices": [{"finish_reason": "length", "message": {"content": None, "reasoning": "..."}}],
        }
        return resp

    client = NineRouterClient()
    with patch("requests.post", side_effect=fake_post):
        with pytest.raises(RuntimeError, match="200"):
            client.chat([{"role": "user", "content": "hi"}])


def test_truncated_unparsable_json_body_is_retried_then_raises():
    """A response body cut off mid-string (finish_reason=length, but the
    HTTP body itself is malformed JSON) — the real failure mode from the
    user's log."""
    def fake_post(url, json, headers, timeout, verify):
        resp = MagicMock()
        resp.ok = True
        resp.status_code = 200
        resp.text = '{"choices":[{"message":{"content":"{\\"description\\": \\"<p>Perfect for eve'
        resp.json.side_effect = ValueError("Expecting value")
        return resp

    client = NineRouterClient()
    with patch("requests.post", side_effect=fake_post):
        with pytest.raises(RuntimeError):
            client.chat([{"role": "user", "content": "hi"}])


def test_timeout_is_retried_up_to_max_retries():
    call_count = {"n": 0}

    def fake_post(url, json, headers, timeout, verify):
        call_count["n"] += 1
        raise requests.Timeout("Read timed out.")

    client = NineRouterClient()
    with patch("requests.post", side_effect=fake_post):
        with pytest.raises(RuntimeError, match="Could not connect"):
            client.chat([{"role": "user", "content": "hi"}])

    assert call_count["n"] == Config.MAX_RETRIES


def test_default_model_follows_config():
    Config.NINEROUTER_MODEL = "code-9router-combo"
    client = NineRouterClient()
    assert client.model == "code-9router-combo"
