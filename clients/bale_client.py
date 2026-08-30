import logging

from telegram.ext import Application

from clients.bot_requests import build_bot_requests
from config import Config

logger = logging.getLogger(__name__)

# Bale's Bot API is a compatible fork of the Telegram Bot API, so the same
# python-telegram-bot library works against it — we only need to point the
# base URLs at tapi.bale.ai instead of api.telegram.org.
BALE_API_BASE_URL = "https://tapi.bale.ai/bot"
BALE_API_FILE_BASE_URL = "https://tapi.bale.ai/file/bot"


class BaleClient:
    def __init__(self):
        token = Config.BALE_BOT_TOKEN
        if not token:
            raise ValueError("BALE_BOT_TOKEN is missing in config!")

        api_request, updates_request = build_bot_requests()
        self.app = (
            Application.builder()
            .token(token)
            .base_url(BALE_API_BASE_URL)
            .base_file_url(BALE_API_FILE_BASE_URL)
            .request(api_request)
            .get_updates_request(updates_request)
            .build()
        )

    def add_handler(self, handler):
        self.app.add_handler(handler)
