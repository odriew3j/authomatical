from unittest.mock import MagicMock, call, patch

from clients.bot_requests import build_bot_requests
from clients.bale_client import BALE_API_BASE_URL, BALE_API_FILE_BASE_URL, BaleClient
from clients.telegram_client import TelegramClient
from config import Config


def test_build_bot_requests_uses_longer_separate_message_and_polling_timeouts(monkeypatch):
    monkeypatch.setattr(Config, "BOT_CONNECT_TIMEOUT", 31.0)
    monkeypatch.setattr(Config, "BOT_READ_TIMEOUT", 32.0)
    monkeypatch.setattr(Config, "BOT_WRITE_TIMEOUT", 33.0)
    monkeypatch.setattr(Config, "BOT_POOL_TIMEOUT", 34.0)
    monkeypatch.setattr(Config, "BOT_POLL_READ_TIMEOUT", 45.0)
    api_request, updates_request = MagicMock(), MagicMock()

    with patch(
        "clients.bot_requests.HTTPXRequest",
        side_effect=[api_request, updates_request],
    ) as request_class:
        assert build_bot_requests() == (api_request, updates_request)

    assert request_class.call_args_list == [
        call(
            connection_pool_size=8,
            connect_timeout=31.0,
            read_timeout=32.0,
            write_timeout=33.0,
            pool_timeout=34.0,
            http_version="1.1",
        ),
        call(
            connection_pool_size=2,
            connect_timeout=31.0,
            read_timeout=45.0,
            write_timeout=33.0,
            pool_timeout=34.0,
            http_version="1.1",
        ),
    ]


class _Builder:
    def __init__(self, app):
        self.app = app
        self.calls = []

    def _chain(self, name, *args):
        self.calls.append((name, args))
        return self

    def token(self, *args):
        return self._chain("token", *args)

    def base_url(self, *args):
        return self._chain("base_url", *args)

    def base_file_url(self, *args):
        return self._chain("base_file_url", *args)

    def request(self, *args):
        return self._chain("request", *args)

    def get_updates_request(self, *args):
        return self._chain("get_updates_request", *args)

    def build(self):
        self.calls.append(("build", ()))
        return self.app


class _ApplicationFactory:
    def __init__(self, builder):
        self.builder_instance = builder

    def builder(self):
        return self.builder_instance


def test_telegram_client_attaches_both_request_clients(monkeypatch):
    app = MagicMock()
    builder = _Builder(app)
    api_request, updates_request = MagicMock(), MagicMock()
    monkeypatch.setattr(Config, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr("clients.telegram_client.Application", _ApplicationFactory(builder))
    monkeypatch.setattr(
        "clients.telegram_client.build_bot_requests",
        lambda: (api_request, updates_request),
    )

    client = TelegramClient()

    assert client.app is app
    assert builder.calls == [
        ("token", ("test-token",)),
        ("request", (api_request,)),
        ("get_updates_request", (updates_request,)),
        ("build", ()),
    ]


def test_bale_client_keeps_bale_urls_and_attaches_both_request_clients(monkeypatch):
    app = MagicMock()
    builder = _Builder(app)
    api_request, updates_request = MagicMock(), MagicMock()
    monkeypatch.setattr(Config, "BALE_BOT_TOKEN", "test-token")
    monkeypatch.setattr("clients.bale_client.Application", _ApplicationFactory(builder))
    monkeypatch.setattr(
        "clients.bale_client.build_bot_requests",
        lambda: (api_request, updates_request),
    )

    client = BaleClient()

    assert client.app is app
    assert builder.calls == [
        ("token", ("test-token",)),
        ("base_url", (BALE_API_BASE_URL,)),
        ("base_file_url", (BALE_API_FILE_BASE_URL,)),
        ("request", (api_request,)),
        ("get_updates_request", (updates_request,)),
        ("build", ()),
    ]
