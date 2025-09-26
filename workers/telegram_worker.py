import logging
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes

from clients.telegram_client import TelegramClient
from messaging.redis_broker import RedisBroker

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

broker = RedisBroker(stream="article_jobs")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! 👋 لطفاً موضوع مقاله رو وارد کن:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logging.info(f"User input: {text}")

    job_data = {
        "keywords": text,
        "chapters": "5",
        "max_words": "500",
        "tone": "informative",
        "audience": "general"
    }

    job_id = broker.publish(job_data)
    logging.info(f"Published job id: {job_id}")
    await update.message.reply_text("درخواستت ثبت شد، مقاله در حال تولید است...")

if __name__ == "__main__":
    tg = TelegramClient()
    tg.add_handler(CommandHandler("start", start))
    tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Only run_polling not asyncio.run
    tg.app.run_polling(poll_interval=5, timeout=30, drop_pending_updates=True)
