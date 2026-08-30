from unittest.mock import MagicMock

from config import Config
from workers import bale_worker, telegram_worker


def _assert_worker_run(monkeypatch, module, client_attribute, platform):
    app = MagicMock()
    client = MagicMock()
    client.app = app
    configure_logging = MagicMock()
    register = MagicMock()
    monkeypatch.setattr(module, client_attribute, lambda: client)
    monkeypatch.setattr(module, "configure_worker_logging", configure_logging)
    monkeypatch.setattr(module, "register_handlers", register)
    monkeypatch.setattr(Config, "BOT_POLL_INTERVAL", 2.5)
    monkeypatch.setattr(Config, "BOT_POLL_TIMEOUT", 42)

    module.run()

    configure_logging.assert_called_once_with()
    register.assert_called_once_with(client, platform=platform)
    app.run_polling.assert_called_once_with(
        poll_interval=2.5,
        timeout=42,
        bootstrap_retries=-1,
        drop_pending_updates=True,
    )


def test_bale_worker_configures_logging_and_resilient_polling(monkeypatch):
    _assert_worker_run(monkeypatch, bale_worker, "BaleClient", "bale")


def test_telegram_worker_configures_logging_and_resilient_polling(monkeypatch):
    _assert_worker_run(monkeypatch, telegram_worker, "TelegramClient", "telegram")
