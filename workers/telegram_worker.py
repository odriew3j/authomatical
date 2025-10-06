import logging
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes

from clients.telegram_client import TelegramClient
from messaging.redis_broker import RedisBroker

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

article_broker = RedisBroker(stream="article_jobs")
product_broker = RedisBroker(stream="product_jobs")
wordpress_broker = RedisBroker(stream="wordpress_jobs")


# -------- STEP CHAINS --------
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
    ("images", "🖼️ لینک تصاویر (با , جدا کن):"),
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


# -------- HANDLE --------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # Back handling
    if text.lower() == "back":
        if "substep" in context.user_data and context.user_data["substep"] > 0:
            context.user_data["substep"] -= 1
            await ask_current_question(update, context)
        else:
            context.user_data.clear()
            await show_main_menu(update)
        return

    # if step not selected:
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

    # is confrim chain
    step = context.user_data["step"]
    sub = context.user_data["substep"]
    steps = context.user_data["steps"]

    key = steps[sub][0]
    if text != "-" or step == "article":  # "-" = for optional
        context.user_data["data"][key] = text

    push_next_substep(context)

    # if step
    if context.user_data["substep"] < len(steps):
        await ask_current_question(update, context)
        return

    # -------- charg data --------
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
        job_data = data.copy()
        job_id = product_broker.publish(job_data)
        await update.message.reply_text(f"✅ محصول ثبت شد. job_id={job_id}")

    elif step == "wordpress":
        job_data = data.copy()
        job_id = wordpress_broker.publish(job_data)
        await update.message.reply_text(f"✅ اطلاعات وردپرس ذخیره شد. job_id={job_id}")

    # restart → general menu
    context.user_data.clear()
    await show_main_menu(update)


# -------- MAIN --------
if __name__ == "__main__":
    tg = TelegramClient()
    tg.add_handler(CommandHandler("start", start))
    tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    tg.app.run_polling(poll_interval=5, timeout=30, drop_pending_updates=True)
