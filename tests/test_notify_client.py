from unittest.mock import MagicMock, patch

import requests

from clients.notify_client import send_platform_message
from config import Config


def _response(*, ok=True, status=200, body=None, text=""):
    response = MagicMock()
    response.ok = ok
    response.status_code = status
    response.text = text
    response.json.return_value = {"ok": True} if body is None else body
    return response


def test_sends_telegram_message_without_constructing_a_bot_application(monkeypatch):
    monkeypatch.setattr(Config, "TELEGRAM_BOT_TOKEN", "telegram-test-token")
    monkeypatch.setattr(Config, "TIMEOUT", 17)
    response = _response()

    with patch("clients.notify_client.requests.post", return_value=response) as post:
        assert send_platform_message("telegram", 12345, "کار تمام شد") is True

    post.assert_called_once_with(
        "https://api.telegram.org/bottelegram-test-token/sendMessage",
        json={"chat_id": 12345, "text": "کار تمام شد"},
        timeout=17,
    )


def test_sends_bale_message(monkeypatch):
    monkeypatch.setattr(Config, "BALE_BOT_TOKEN", "bale-test-token")

    with patch("clients.notify_client.requests.post", return_value=_response()) as post:
        assert send_platform_message("bale", "9988", "موفق") is True

    assert post.call_args.args[0] == "https://tapi.bale.ai/botbale-test-token/sendMessage"
    assert post.call_args.kwargs["json"] == {"chat_id": "9988", "text": "موفق"}


def test_missing_token_unknown_platform_and_http_error_are_non_fatal(monkeypatch):
    monkeypatch.setattr(Config, "TELEGRAM_BOT_TOKEN", None)
    with patch("clients.notify_client.requests.post") as post:
        assert send_platform_message("telegram", 1, "x") is False
        assert send_platform_message("unknown", 1, "x") is False
    post.assert_not_called()

    monkeypatch.setattr(Config, "TELEGRAM_BOT_TOKEN", "token")
    with patch(
        "clients.notify_client.requests.post",
        return_value=_response(ok=False, status=500, text="server error"),
    ):
        assert send_platform_message("telegram", 1, "x") is False


def test_network_failure_or_api_rejection_returns_false(monkeypatch):
    monkeypatch.setattr(Config, "TELEGRAM_BOT_TOKEN", "token")

    with patch("clients.notify_client.requests.post", side_effect=requests.Timeout("slow")):
        assert send_platform_message("telegram", 1, "x") is False

    with patch(
        "clients.notify_client.requests.post",
        return_value=_response(body={"ok": False, "description": "blocked"}),
    ):
        assert send_platform_message("telegram", 1, "x") is False
