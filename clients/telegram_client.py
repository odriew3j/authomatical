import logging

from telegram.ext import Application

from clients.bot_requests import build_bot_requests
from config import Config

logger = logging.getLogger(__name__)


class TelegramClient:
    def __init__(self):
        token = Config.TELEGRAM_BOT_TOKEN
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is missing in config!")

        api_request, updates_request = build_bot_requests()
        self.app = (
            Application.builder()
            .token(token)
            .request(api_request)
            .get_updates_request(updates_request)
            .build()
        )

    def add_handler(self, handler):
        self.app.add_handler(handler)
