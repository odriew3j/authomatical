"""Shared, resilient HTTP transport configuration for Telegram and Bale."""
from telegram.request import HTTPXRequest

from config import Config


def build_bot_requests() -> tuple[HTTPXRequest, HTTPXRequest]:
    """Create separate request clients for messages and long polling.

    A dedicated getUpdates client prevents one long-poll connection from
    starving normal replies.  The defaults are intentionally longer than
    python-telegram-bot's 5-second HTTPX defaults, which are too aggressive
    for transient DNS/TLS delays in containers.
    """
    api_request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=Config.BOT_CONNECT_TIMEOUT,
        read_timeout=Config.BOT_READ_TIMEOUT,
        write_timeout=Config.BOT_WRITE_TIMEOUT,
        pool_timeout=Config.BOT_POOL_TIMEOUT,
        http_version="1.1",
    )
    updates_request = HTTPXRequest(
        connection_pool_size=2,
        connect_timeout=Config.BOT_CONNECT_TIMEOUT,
        read_timeout=Config.BOT_POLL_READ_TIMEOUT,
        write_timeout=Config.BOT_WRITE_TIMEOUT,
        pool_timeout=Config.BOT_POOL_TIMEOUT,
        http_version="1.1",
    )
    return api_request, updates_request
