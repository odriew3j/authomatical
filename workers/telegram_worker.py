"""
Telegram entrypoint. All business logic lives in workers/common_handlers.py
so it can be shared with the Bale entrypoint (workers/bale_worker.py).
"""
from clients.telegram_client import TelegramClient
from workers.common_handlers import register_handlers


if __name__ == "__main__":
    tg = TelegramClient()

    register_handlers(
        tg,
        platform="telegram"
    )

    tg.app.run_polling(
        poll_interval=5,
        timeout=30,
        drop_pending_updates=True,
    )