import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import Config
print("TOKEN:", Config.TELEGRAM_BOT_TOKEN)

class TelegramClient:
    def __init__(self):
        token = Config.TELEGRAM_BOT_TOKEN
        self.app = Application.builder().token(token).build()

    def add_handler(self, handler):
        self.app.add_handler(handler)

    def run(self):
        self.app.run_polling()
