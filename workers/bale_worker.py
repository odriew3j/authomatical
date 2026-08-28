"""
Bale entrypoint. All business logic lives in workers/common_handlers.py
so it's shared with the Telegram entrypoint (workers/telegram_worker.py).

Note on polling vs webhook: getUpdates on Bale keeps only the last 2000
messages for 24h, same as here. Long-polling (as used below) works fine
for low/medium volume; for production it's worth switching to setWebhook
per Bale's docs once you have a stable HTTPS endpoint.
"""
from clients.bale_client import BaleClient
from workers.common_handlers import register_handlers


if __name__ == "__main__":
    bale = BaleClient()

    register_handlers(
        bale,
        platform="bale"
    )

    bale.app.run_polling(
        poll_interval=5,
        timeout=30,
        drop_pending_updates=True,
    )