import os
import logging
import requests
import mimetypes

from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes

from config import Config
from clients.telegram_client import TelegramClient
from messaging.redis_broker import RedisBroker

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

article_broker = RedisBroker(stream="article_jobs")
product_broker = RedisBroker(stream="product_jobs")
wordpress_broker = RedisBroker(stream="wordpress_jobs")

WORDPRESS_STEPS = [
    ("site_url", "🌐 آدرس سایت وردپرس رو وارد کن:"),
    ("username", "👤 نام کاربری وردپرس:"),
    ("password", "🔑 رمز عبور وردپرس:"),
]

PRODUCT_STEPS = [
    ("title", "📦 نام محصول:"),
    ("price", "💰 قیمت محصول:"),
    ("sale_price", "💲 قیمت تخفیفی (اختیاری، اگر نداری بفرست -):"),
    ("category", "📂 دسته‌بندی محصول:"),
    ("brand", "🏷️ برند محصول (اختیاری):"),
    ("tags", "🔖 تگ‌ها (با , جدا کن):"),
]

ARTICLE_STEPS = [
    ("keywords", "📝 موضوع مقاله رو وارد کن:"),
]

# -------- HELPERS --------
def init_chain(context, step_name, steps):
    context.user_data.clear()
    context.user_data["step"] = step_name
    context.user_data["substep"] = 0
    context.user_data["data"] = {}
    context.user_data["steps"] = steps

def push_next_substep(context):
    context.user_data["substep"] += 1

async def ask_current_question(update, context):
    steps = context.user_data["steps"]
    sub = context.user_data["substep"]
    if sub < len(steps):
        await update.message.reply_text(steps[sub][1])

async def show_main_menu(update: Update):
    msg = (
        "سلام! 👋 لطفاً یکی از گزینه‌ها رو انتخاب کن:\n\n"
        "1️⃣ وارد کردن اطلاعات وردپرس\n"
        "2️⃣ ارسال محصول به سایت\n"
        "3️⃣ ارسال نوشته به سایت\n\n"
        "🔙 یا بنویس: back برای برگشت"
    )
    await update.message.reply_text(msg)

# -------- START --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await show_main_menu(update)

# -------- HANDLE TEXT --------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text.lower() == "back":
        if "substep" in context.user_data and context.user_data["substep"] > 0:
            context.user_data["substep"] -= 1
            await ask_current_question(update, context)
        else:
            context.user_data.clear()
            await show_main_menu(update)
        return

    if "step" not in context.user_data:
        if text == "1":
            init_chain(context, "wordpress", WORDPRESS_STEPS)
            await ask_current_question(update, context)
        elif text == "2":
            init_chain(context, "product", PRODUCT_STEPS)
            await ask_current_question(update, context)
        elif text == "3":
            init_chain(context, "article", ARTICLE_STEPS)
            await ask_current_question(update, context)
        else:
            await update.message.reply_text("لطفاً فقط 1 یا 2 یا 3 رو انتخاب کن.")
        return

    step = context.user_data["step"]
    sub = context.user_data["substep"]
    steps = context.user_data["steps"]

    key = steps[sub][0]
    if step == "article":
        context.user_data["data"][key] = text
    elif text == "-":
        context.user_data["data"][key] = ""
    else:
        context.user_data["data"][key] = text

    push_next_substep(context)

    if context.user_data["substep"] < len(steps):
        await ask_current_question(update, context)
        return

    data = context.user_data["data"]

    if step == "article":
        job_data = {
            "keywords": data["keywords"],
            "chapters": "5",
            "max_words": "500",
            "tone": "informative",
            "audience": "general"
        }
        job_id = article_broker.publish(job_data)
        await update.message.reply_text(f"✅ مقاله ثبت شد. job_id={job_id}")

    elif step == "product":
        await update.message.reply_text("✅ اطلاعات محصول ثبت شد. حالا عکس محصول رو بفرست 📷")
        return

    elif step == "wordpress":
        job_data = data.copy()
        job_id = wordpress_broker.publish(job_data)
        await update.message.reply_text(f"✅ اطلاعات وردپرس ذخیره شد. job_id={job_id}")

    context.user_data.clear()
    await show_main_menu(update)

# -------- HANDLE FILE/PHOTO --------
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_path = None

    if update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_path = os.path.join(UPLOAD_DIR, f"{file.file_id}.jpg")
        await file.download_to_drive(file_path)

    elif update.message.document:
        doc = update.message.document
        if not doc.mime_type.startswith("image/"):
            await update.message.reply_text("⚠️ فقط فایل تصویری مجاز است.")
            return
        file = await doc.get_file()
        ext = os.path.splitext(doc.file_name)[-1]
        file_path = os.path.join(UPLOAD_DIR, f"{doc.file_id}{ext}")
        await file.download_to_drive(file_path)

    if not file_path:
        return

    await update.message.reply_text(f"🖼 تصویر ذخیره شد: {os.path.basename(file_path)}")

    # wp_user = context.user_data.get("username")
    # wp_pass = context.user_data.get("password")
    # wp_url = context.user_data.get("site_url")
    wp_user = Config.WORDPRESS_USER
    wp_pass = Config.WORDPRESS_PASSWORD
    wp_url = Config.WORDPRESS_URL

    media_url = None
    if wp_user and wp_pass and wp_url:
        media_endpoint = f"{wp_url}/wp-json/wp/v2/media"
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "application/octet-stream"

        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f, mime_type)}
                resp = requests.post(media_endpoint, files=files, auth=(wp_user, wp_pass))

            if resp.status_code in (200, 201):
                media_data = resp.json()
                media_url = media_data.get("source_url")
                await update.message.reply_text(f"🖼 تصویر در وردپرس آپلود شد: {media_url}")
            else:
                await update.message.reply_text(f"⚠️ خطا در آپلود به وردپرس ({resp.status_code}): {resp.text}")
        except Exception as e:
            await update.message.reply_text(f"⚠️ خطای آپلود: {str(e)}")

    # send product
    if "step" in context.user_data and context.user_data["step"] == "product":
        data = context.user_data.get("data", {})
        if media_url:
            data["images"] = media_url
        job_id = product_broker.publish(data)
        await update.message.reply_text(f"✅ محصول نهایی ساخته شد. job_id={job_id}")
        context.user_data.clear()
        await show_main_menu(update)


# -------- MAIN --------
if __name__ == "__main__":
    tg = TelegramClient()
    tg.add_handler(CommandHandler("start", start))
    tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    tg.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_file))
    tg.app.run_polling(poll_interval=5, timeout=30, drop_pending_updates=True)
