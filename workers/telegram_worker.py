import os
import logging
import requests
import mimetypes
import re
from requests.auth import HTTPBasicAuth


from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes
from services.product_builder import ProductBuilder
from modules.wordpress_product import WordPressProductModule

from config import Config
from clients.telegram_client import TelegramClient
from messaging.redis_broker import RedisBroker

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

article_broker = RedisBroker(stream="article_jobs")
product_broker = RedisBroker(stream="product_jobs")
wordpress_broker = RedisBroker(stream="wordpress_jobs")

builder = ProductBuilder()
wp_module = WordPressProductModule()

# --- Normalizer ---
PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
ENGLISH_DIGITS = "0123456789"

digit_map = {p: e for p, e in zip(PERSIAN_DIGITS, ENGLISH_DIGITS)}
digit_map.update({a: e for a, e in zip(ARABIC_DIGITS, ENGLISH_DIGITS)})

def normalize_digits(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return "".join(digit_map.get(ch, ch) for ch in text)

def normalize_price(value: str) -> int:
    value = normalize_digits(value)
    value = re.sub(r"[^\d]", "", value)
    return int(value) if value else 0

# --- Steps ---
WORDPRESS_STEPS = [
    ("site_url", "🌐 آدرس سایت وردپرس رو وارد کن:"),
    ("username", "👤 نام کاربری وردپرس:"),
    ("password", "🔑 رمز عبور وردپرس:"),
]

PRODUCT_STEPS = [
    ("title", "📦 نام محصول:"),
    ("price", "💰 قیمت محصول:"),
    ("sale_price", "💲 قیمت تخفیفی (اختیاری، اگر نداری بفرست -):"),
    ("stock_quantity", "📦 موجودی انبار (چند عدد از این محصول داری؟):"),
]

ARTICLE_STEPS = [
    ("keywords", "📝 موضوع مقاله رو وارد کن:"),
]

# --- Categories ---
CATEGORIES = [
    ("اکسسوری", "accessories"),
    ("دید در شب", "night-vision"),
    ("عدسی طبی", "medical-lens"),
    ("عینک آفتابی زنانه", "women-sunglasses"),
    ("عینک آفتابی مردانه", "men-sunglasses"),
    ("عینک آفتابی بچه", "kids-sunglasses"),
    ("عینک اسپرت", "sports-glasses"),
    ("عینک پلاریزه", "polarized-glasses"),
    ("عینک طبی", "medical-glasses"),
    ("عینک طبی زنانه", "women-medical-glasses"),
    ("عینک طبی مردانه", "men-prescription-glasses"),
    ("عینک های ساخت اروپا", "glasses-made-in-europe"),
    ("فستیوال 1 عدد عینک 99 تومان", "festival-1-glasses-99-toman"),
    ("فستیوال 2 عدد عینک 130 تومان", "festival-2-glasses-130-toman")
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

    # --- category selection mode ---
    if context.user_data.get("step") == "category_selection":
        try:
            choice = int(normalize_digits(text))
            if 1 <= choice <= len(CATEGORIES):
                category_slug = CATEGORIES[choice - 1][1]
                context.user_data["data"]["category"] = category_slug

                # Go to the step of uploading images
                context.user_data["step"] = "awaiting_images"
                context.user_data["data"]["images"] = []
                await update.message.reply_text(
                    "🖼 لطفاً تصاویر محصول رو بفرست.\n"
                    "می‌تونی چندتا عکس بفرستی. وقتی تموم شد، کلمه «پایان» رو بفرست."
                )
            else:
                await update.message.reply_text("⚠️ لطفاً یک عدد معتبر انتخاب کن.")
        except ValueError:
            await update.message.reply_text("⚠️ لطفاً فقط عدد بفرست.")
        return

    # --- photo upload mode ---
    if context.user_data.get("step") == "awaiting_images":
        if text == "پایان":
            data = context.user_data["data"]

            # Generate text and brand with AI
            ai_product = builder.generate_full_product(
                title=data["title"],
                category=data.get("category")
            )
            brand_name = ai_product.get("brand", "Generic")

            # Build the product
            product_data = {
                "title": data["title"],
                "description": ai_product["description"],
                "price": data.get("price", 0),
                "sale_price": data.get("sale_price") or None,
                "category": data.get("category"),
                "brand": brand_name,
                "tags": ai_product.get("hashtags", "").split(","),
                "images": data.get("images", []),
                "meta_title": ai_product["seo"]["title"],
                "meta_description": ai_product["seo"]["description"],
                "keywords": ai_product["seo"]["keywords"],
                "stock_quantity": data.get("stock_quantity", 0),
            }

            wp_product = wp_module.create_product(**product_data)
            # job_id = product_broker.publish(product_data)

            await update.message.reply_text(f"✅ محصول برای ساخت ارسال شد (wp_product={wp_product})")

            context.user_data.clear()
            await show_main_menu(update)
        else:
            await update.message.reply_text("⚠️ اگر آپلود تموم شده، کلمه «پایان» رو بفرست.")
        return

    # --- mode of starting the steps ---
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

    # Normalize the price
    if key == "price" and text != "-":
        context.user_data["data"][key] = normalize_price(text)
    elif key == "sale_price" and text != "-":
        context.user_data["data"][key] = normalize_price(text)
    elif key == "stock_quantity" and text != "-":
        context.user_data["data"][key] = normalize_price(text)
    else:
        context.user_data["data"][key] = text if text != "-" else ""

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
        context.user_data.clear()
        await show_main_menu(update)

    elif step == "product":
        # Show categories
        msg = "📂 دسته‌بندی محصول را انتخاب کن:\n\n"
        for i, (name, slug) in enumerate(CATEGORIES, start=1):
            msg += f"{i}. {name}\n"
        msg += "\n🔢 عدد مربوط به دسته رو بفرست."
        await update.message.reply_text(msg)
        context.user_data["step"] = "category_selection"
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
    media_url = None

    # Receive photos from Telegram
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

    # Direct upload to WordPress (Media Library)
    wp_user = Config.WORDPRESS_USER
    wp_pass = Config.WORDPRESS_PASSWORD
    wp_url = Config.WORDPRESS_URL

    if wp_user and wp_pass and wp_url:
        media_endpoint = f"{wp_url}/wp-json/wp/v2/media"
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "application/octet-stream"

        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f, mime_type)}
                resp = requests.post(media_endpoint, files=files, auth=HTTPBasicAuth(wp_user, wp_pass), headers=headers)

            if resp.status_code in (200, 201):
                media_data = resp.json()
                media_url = media_data.get("source_url")
                await update.message.reply_text(f"🖼 تصویر در وردپرس آپلود شد: {media_url}")
            else:
                await update.message.reply_text(f"⚠️ خطا در آپلود به وردپرس ({resp.status_code}): {resp.text}")
        except Exception as e:
            await update.message.reply_text(f"⚠️ خطای آپلود: {str(e)}")

    # Add image to context.user_data for product
    if context.user_data.get("step") == "awaiting_images" and media_url:
        data = context.user_data.setdefault("data", {})
        images = data.setdefault("images", [])
        if media_url not in images:
            images.append(media_url)
            await update.message.reply_text("📸 تصویر به گالری محصول اضافه شد. می‌تونی ادامه بدی یا «پایان» رو بفرستی.")

# -------- MAIN --------
if __name__ == "__main__":
    tg = TelegramClient()
    tg.add_handler(CommandHandler("start", start))
    tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    tg.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_file))
    tg.app.run_polling(poll_interval=5, timeout=30, drop_pending_updates=True)
