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
