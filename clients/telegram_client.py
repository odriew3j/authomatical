import asyncio
import logging
from telegram.ext import Application
from config import Config

class TelegramClient:
    def __init__(self):
        token = Config.TELEGRAM_BOT_TOKEN
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is missing in config!")
        self.app = Application.builder().token(token).build()

    def add_handler(self, handler):
        self.app.add_handler(handler)

    async def run(self):
        """Run polling inside a safe loop with error handling"""
        while True:
            try:
                logging.info("Starting Telegram polling...")
                await self.app.run_polling(poll_interval=5, timeout=30, drop_pending_updates=True)
            except Exception as e:
                logging.error(f"[TelegramClient] Polling failed: {e}", exc_info=True)
                logging.info("Retrying in 10 seconds...")
                await asyncio.sleep(10)
