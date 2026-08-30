"""Telegram polling entrypoint."""
from clients.telegram_client import TelegramClient
from config import Config
from utils.logging_utils import configure_worker_logging
from workers.common_handlers import register_handlers


def run():
    # Configure redacted logging before PTB/httpx starts making requests.
    configure_worker_logging()
    telegram = TelegramClient()
    register_handlers(telegram, platform="telegram")
    telegram.app.run_polling(
        poll_interval=Config.BOT_POLL_INTERVAL,
        timeout=Config.BOT_POLL_TIMEOUT,
        # Keep retrying through a transient Docker DNS/TLS outage rather than
        # terminating the worker during startup.
        bootstrap_retries=-1,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    run()
