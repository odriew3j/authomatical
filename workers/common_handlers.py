"""
Shared conversation handlers for the product/article/wordpress bot flow.

Platform-agnostic: both Telegram and Bale deliver the same `Update` object
shape (Bale's Bot API is a compatible fork of the Telegram Bot API), so a
single implementation is wired to either client — see
workers/telegram_worker.py and workers/bale_worker.py.

Multi-tenant: every conversation is scoped to a "tenant" — one row per
(platform, chat_id) — resolved via database/repository.py. Each tenant
connects their OWN WordPress/WooCommerce site (through the ODview Sync
companion plugin) and every WP-facing call in this file goes through that
tenant's stored site_url + secret, never a global config. This is what
makes it safe for many different people to use the same bot deployment
without ever touching each other's site.
"""
import os
import logging
import re
import uuid
from typing import Optional

from telegram import Update
from telegram.error import NetworkError
from telegram.ext import ContextTypes

from services.product_builder import ProductBuilder
from clients.site_connector_client import SiteConnectorClient, SiteConnectorError

from database.db import init_db
from database.repository import (
    create_article_job,
    get_or_create_tenant,
    get_wp_connection,
    mark_article_job_failed,
    mark_article_job_queued,
    save_wp_connection,
)
from messaging.redis_broker import RedisBroker

logger = logging.getLogger(__name__)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Database initialization happens when a bot is registered rather than at
# module-import time. That avoids surprise local database files during test
# discovery while retaining the same startup behaviour for both bot workers.
article_broker = RedisBroker(stream="article_jobs")

builder = ProductBuilder()

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
# Connecting a site now takes just two pieces of info: the site URL and the
# per-site secret shown in wp-admin -> "اتصال به بازو" (see the ODview Sync
# plugin). No wp-admin password ever passes through the chat.
WORDPRESS_STEPS = [
    ("site_url", "🌐 آدرس سایت وردپرس رو وارد کن (مثلاً https://example.com):"),
    ("secret", "🔑 کلید امنیتی رو از داخل وردپرس بفرست (منوی «اتصال به بازو»):"),
]

PRODUCT_STEPS = [
    ("title", "📦 نام محصول:"),
    ("product_type", "🏷 این محصول از چه نوعیه؟ (مثلاً: عینک، ساعت، ادکلن، کیف، ...)\nاین به هوش مصنوعی کمک می‌کنه توضیحات واقعی و درست بنویسه، نه چرت‌وپرت کلی."),
    ("user_notes", "📝 اگر مشخصات یا نکته‌ی خاصی درباره‌ی این محصول هست بنویس (جنس، رنگ، ویژگی فنی و ...).\nاگر چیزی نداری، فقط بفرست: x"),
    ("price", "💰 قیمت محصول:"),
    ("sale_price", "💲 قیمت تخفیفی (اختیاری، اگر نداری بفرست -):"),
    ("stock_quantity", "📦 موجودی انبار (چند عدد از این محصول داری؟):"),
]

# Keys the user is explicitly allowed to skip by sending "x" (in addition
# to the existing "-" convention used for numeric fields).
SKIPPABLE_WITH_X = {"user_notes", "notes"}

ARTICLE_STEPS = [
    ("keywords", "📝 موضوع مقاله رو وارد کن:"),
    ("article_type", "🏷 این مقاله چه نوعیه؟ (مثلاً: راهنمای خرید، مقایسه، آموزشی، معرفی محصول و ...)\nاین به هوش مصنوعی کمک می‌کنه محتوای دقیق‌تر و کاربردی‌تر بنویسه، نه چرت‌وپرت کلی."),
    ("notes", "📝 اگر نکته یا زاویه‌ی خاصی می‌خوای مقاله روش تمرکز کنه بنویس.\nاگر چیزی نداری، فقط بفرست: x"),
]


# -------- TENANT / SITE HELPERS --------
def get_platform(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Set once at startup via register_handlers(client, platform=...)."""
    return context.application.bot_data.get("platform", "unknown")


def get_tenant_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Resolve (and cache for this conversation) the DB tenant id for the
    person currently chatting. Cached in user_data so we don't hit the DB
    on every single message — user_data is already isolated per chat by
    python-telegram-bot, and platform is baked into the DB lookup key, so
    a telegram chat_id and a bale chat_id with the same number never
    resolve to the same tenant."""
    if "_tenant_id" not in context.user_data:
        platform = get_platform(context)
        chat = update.effective_chat
        display_name = getattr(update.effective_user, "first_name", None)
        context.user_data["_tenant_id"] = get_or_create_tenant(platform, chat.id, display_name)
    return context.user_data["_tenant_id"]


def get_site_client(tenant_id: int) -> Optional[SiteConnectorClient]:
    """Returns a SiteConnectorClient bound to this tenant's own connected
    site, or None if they haven't connected one yet."""
    conn = get_wp_connection(tenant_id)
    if not conn:
        return None
    return SiteConnectorClient(conn["site_url"], conn["secret"])


# -------- HELPERS --------
def init_chain(context, step_name, steps):
    context.user_data["step"] = step_name
    context.user_data["substep"] = 0
    context.user_data["data"] = {}
    context.user_data["steps"] = steps


def reset_flow(context):
    """Clear conversation state but keep the cached tenant id — no need to
    re-hit the DB just because the user went back to the main menu."""
    tenant_id = context.user_data.get("_tenant_id")
    context.user_data.clear()
    if tenant_id is not None:
        context.user_data["_tenant_id"] = tenant_id


def push_next_substep(context):
    context.user_data["substep"] += 1


async def ask_current_question(update, context):
    steps = context.user_data["steps"]
    sub = context.user_data["substep"]
    if sub < len(steps):
        await update.message.reply_text(steps[sub][1])


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tenant_id = get_tenant_id(update, context)
    connected = get_wp_connection(tenant_id) is not None
    status_line = "✅ سایتت وصل است." if connected else "⚠️ هنوز سایتی وصل نکرده‌ای."
    msg = (
        f"سلام! 👋 {status_line}\n\n"
        "یکی از گزینه‌ها رو انتخاب کن:\n\n"
        "1️⃣ وارد کردن / تغییر اطلاعات وردپرس\n"
        "2️⃣ ارسال محصول به سایت\n"
        "3️⃣ ارسال نوشته به سایت\n\n"
        "🔙 یا بنویس: back برای برگشت"
    )
    await update.message.reply_text(msg)


async def require_connection(update, context) -> Optional[dict]:
    """Shared guard for anything that needs a connected site. Returns the
    connection dict on success, or replies with an error and returns None."""
    tenant_id = get_tenant_id(update, context)
    conn = get_wp_connection(tenant_id)
    if not conn:
        await update.message.reply_text(
            "⚠️ اول باید سایتت رو وصل کنی. گزینه‌ی «1» رو از منو انتخاب کن."
        )
        reset_flow(context)
        await show_main_menu(update, context)
        return None
    return conn


# -------- START --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_flow(context)
    get_tenant_id(update, context)  # ensure the tenant row exists from first contact
    await show_main_menu(update, context)


# -------- HANDLE TEXT --------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    get_tenant_id(update, context)

    if text.lower() == "back":
        if "substep" in context.user_data and context.user_data["substep"] > 0:
            context.user_data["substep"] -= 1
            await ask_current_question(update, context)
        else:
            reset_flow(context)
            await show_main_menu(update, context)
        return

    # --- category selection mode ---
    if context.user_data.get("step") == "category_selection":
        categories = context.user_data.get("categories", [])
        try:
            choice = int(normalize_digits(text))
            if 1 <= choice <= len(categories):
                category_slug = categories[choice - 1]["slug"]
                context.user_data["data"]["category"] = category_slug

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
            conn = await require_connection(update, context)
            if not conn:
                return
            site = SiteConnectorClient(conn["site_url"], conn["secret"])

            data = context.user_data["data"]

            # Generate text and brand with AI (tenant-agnostic AI service).
            # NineRouter (local multi-backend gateway) can occasionally
            # fail after retries — e.g. it routed to a slow reasoning
            # model that got truncated before producing valid JSON. Catch
            # that here so the user gets a clear message and can just
            # send "پایان" again, instead of the update silently dying
            # with no reply (which is what happened before this guard —
            # PTB just logs "No error handlers are registered").
            try:
                await update.message.reply_text(
                    "🤖 در حال پردازش با هوش مصنوعی هستم...\n"
                    "⏳ این عملیات ممکن است حدود ۱ دقیقه زمان ببرد، لطفاً منتظر بمانید."
                )

                ai_product = builder.generate_full_product(
                    title=data["title"],
                    category=data.get("category"),
                    product_type=data.get("product_type", ""),
                    user_notes=data.get("user_notes", ""),
                )

            except Exception as e:
                logging.error(f"AI product generation failed: {e}")
                await update.message.reply_text(
                    "⚠️ سرویس هوش مصنوعی موقتاً پاسخ نداد. "
                    "لطفاً چند لحظه دیگر «پایان» رو دوباره بفرست."
                )
                return

            brand_name = ai_product.get("brand", "Generic")

            payload = {
                "title": data["title"],
                "description": ai_product["description"],
                "slug": ai_product.get("slug"),  # always English/ASCII + unique, see product_builder.py
                "price": data.get("price", 0),
                "sale_price": data.get("sale_price") or None,
                "category": data.get("category"),
                "brand": brand_name,
                "tags": [t.strip() for t in ai_product.get("hashtags", "").split(",") if t.strip()],
                "images": data.get("images", []),
                "meta_title": ai_product["seo"]["title"],
                "meta_description": ai_product["seo"]["description"],
                "keywords": ai_product["seo"]["keywords"],
                "stock_quantity": data.get("stock_quantity", 0),
            }

            try:
                result = site.create_product(payload)
                msg = f"✅ محصول روی سایتت ساخته شد."
                if result.get("url"):
                    msg += f"\n🔗 {result['url']}"
                await update.message.reply_text(msg)
            except SiteConnectorError as e:
                await update.message.reply_text(f"⚠️ ساخت محصول ناموفق بود: {e}")

            reset_flow(context)
            await show_main_menu(update, context)
        else:
            await update.message.reply_text("⚠️ اگر آپلود تموم شده، کلمه «پایان» رو بفرست.")
        return

    # --- mode of starting the steps ---
    if "step" not in context.user_data:
        if text == "1":
            init_chain(context, "wordpress", WORDPRESS_STEPS)
            await ask_current_question(update, context)
        elif text == "2":
            conn = await require_connection(update, context)
            if not conn:
                return
            site = SiteConnectorClient(conn["site_url"], conn["secret"])
            try:
                categories = site.get_categories()
            except SiteConnectorError as e:
                await update.message.reply_text(f"⚠️ دریافت دسته‌بندی‌ها از سایتت ناموفق بود: {e}")
                await show_main_menu(update, context)
                return
            if not categories:
                await update.message.reply_text("⚠️ سایتت هیچ دسته‌بندی محصولی نداره. اول یک دسته بساز.")
                await show_main_menu(update, context)
                return
            init_chain(context, "product", PRODUCT_STEPS)
            context.user_data["categories"] = categories
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

    if key in ("price", "sale_price", "stock_quantity") and text != "-":
        context.user_data["data"][key] = normalize_price(text)
    elif key in SKIPPABLE_WITH_X and text.strip().lower() in ("x", "-"):
        context.user_data["data"][key] = ""
    else:
        context.user_data["data"][key] = text if text != "-" else ""

    push_next_substep(context)

    if context.user_data["substep"] < len(steps):
        await ask_current_question(update, context)
        return

    data = context.user_data["data"]

    if step == "article":
        # Validate that this conversation still owns a connected site before
        # creating a request.  The durable job itself derives platform/chat
        # metadata from tenant_id, never from Redis fields.
        conn = await require_connection(update, context)
        if not conn:
            return

        tenant_id = get_tenant_id(update, context)
        job_data = {
            "keywords": data["keywords"],
            "article_type": data.get("article_type", ""),
            "notes": data.get("notes", ""),
            "chapters": 5,
            "max_words": 500,
            "tone": "informative",
            "audience": "general",
            "source": "bot",
        }

        # PostgreSQL is written first.  A Redis stream entry is merely an
        # execution notification containing this durable ID — it must never
        # be the sole source of history or tenant ownership.
        try:
            job_id = create_article_job(tenant_id, **job_data)
        except Exception:
            logger.exception("Could not persist article job for tenant=%s", tenant_id)
            await update.message.reply_text(
                "⚠️ ثبت درخواست مقاله در دیتابیس ناموفق بود. لطفاً کمی بعد دوباره امتحان کن."
            )
            reset_flow(context)
            await show_main_menu(update, context)
            return

        try:
            queue_message_id = article_broker.publish({"job_id": str(job_id)})
        except RuntimeError as exc:
            # The durable record remains available for diagnostics even when
            # Redis is down.  Mark it terminal before returning to the user;
            # it was never enqueued, so no worker can publish it later.
            try:
                mark_article_job_failed(job_id, f"Redis queue publish failed: {exc}")
            except Exception:
                logger.exception("Could not record Redis queue failure for article job=%s", job_id)
            logger.error("Failed to publish durable article job=%s: %s", job_id, exc)
            await update.message.reply_text(
                "⚠️ صف پردازش پیام (Redis) در دسترس نیست. لطفاً بعداً دوباره امتحان کن."
            )
            reset_flow(context)
            await show_main_menu(update, context)
            return

        # If this metadata update is briefly unavailable, the XADD already
        # succeeded and the durable PENDING job remains safe to process.  Do
        # not incorrectly turn it into FAILED after it has been queued.
        try:
            mark_article_job_queued(job_id, queue_message_id)
        except Exception:
            logger.exception("Could not record Redis message ID for article job=%s", job_id)

        await update.message.reply_text(
            "🤖 مقاله وارد مرحله پردازش با هوش مصنوعی شد.\n"
            "⏳ این عملیات ممکن است حدود ۱ دقیقه زمان ببرد، لطفاً منتظر بمانید.\n"
            f"🔎 شناسه پیگیری: {job_id}"
        )

        reset_flow(context)
        await show_main_menu(update, context)

    elif step == "product":
        categories = context.user_data.get("categories", [])
        msg = "📂 دسته‌بندی محصول را انتخاب کن:\n\n"
        for i, cat in enumerate(categories, start=1):
            msg += f"{i}. {cat['name']}\n"
        msg += "\n🔢 عدد مربوط به دسته رو بفرست."
        await update.message.reply_text(msg)
        context.user_data["step"] = "category_selection"
        return

    elif step == "wordpress":
        site_url = data["site_url"].strip()
        secret = data["secret"].strip()

        await update.message.reply_text("🔎 در حال بررسی اتصال به سایتت...")
        tenant_id = get_tenant_id(update, context)
        site = SiteConnectorClient(site_url, secret)
        try:
            info = site.ping()
        except SiteConnectorError as e:
            await update.message.reply_text(
                f"❌ اتصال ناموفق بود: {e}\n\n"
                "آدرس سایت و کلید امنیتی رو دوباره چک کن و گزینه‌ی «1» رو دوباره امتحان کن."
            )
            reset_flow(context)
            await show_main_menu(update, context)
            return

        if not info.get("wc_active", True):
            await update.message.reply_text(
                "⚠️ اتصال برقرار شد ولی ووکامرس روی این سایت فعال نیست. "
                "برای ساخت محصول باید ووکامرس رو فعال کنی."
            )

        save_wp_connection(tenant_id, site_url, secret, verified=True)
        site_name = info.get("site_name") or site_url
        await update.message.reply_text(f"✅ سایتت («{site_name}») با موفقیت وصل شد.")
        reset_flow(context)
        await show_main_menu(update, context)


# -------- HANDLE FILE/PHOTO --------
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("step") != "awaiting_images":
        return  # ignore stray images outside the product-image step

    conn = await require_connection(update, context)
    if not conn:
        return

    file_path = None

    # Bale's file_id looks like "2141709305:-2821908970244137214:1:d71a...",
    # which contains colons — invalid in a Windows filename/path (this was
    # crashing download_to_drive() with "OSError: [Errno 22] Invalid
    # argument" on Windows). We never need the file_id as a filename, so
    # just generate a safe random one instead.
    if update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}.jpg")
        await file.download_to_drive(file_path)

    elif update.message.document:
        doc = update.message.document
        if not doc.mime_type or not doc.mime_type.startswith("image/"):
            await update.message.reply_text("⚠️ فقط فایل تصویری مجاز است.")
            return
        file = await doc.get_file()
        ext = os.path.splitext(doc.file_name or "")[-1]
        ext = ext if re.fullmatch(r"\.[A-Za-z0-9]{1,10}", ext or "") else ".jpg"
        file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")
        await file.download_to_drive(file_path)

    if not file_path:
        return

    site = SiteConnectorClient(conn["site_url"], conn["secret"])
    try:
        result = site.upload_media(file_path)
    except SiteConnectorError as e:
        await update.message.reply_text(f"⚠️ آپلود تصویر روی سایتت ناموفق بود: {e}")
        return
    finally:
        try:
            os.remove(file_path)
        except OSError:
            pass

    media_url = result.get("url")
    if media_url:
        data = context.user_data.setdefault("data", {})
        images = data.setdefault("images", [])
        if media_url not in images:
            images.append(media_url)
            await update.message.reply_text("📸 تصویر به گالری محصول اضافه شد. می‌تونی ادامه بدی یا «پایان» رو بفرستی.")


async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    """Report application errors without turning a transport blip into spam.

    python-telegram-bot also invokes application error handlers for polling
    transport failures, where ``update`` is ``None``. The polling loop already
    retries those failures; logging a second full traceback (and attempting a
    reply over the same broken network) only creates noisy duplicate logs.
    """
    error = context.error
    if update is None or isinstance(error, NetworkError):
        logger.warning("Bot API transport error; polling will retry: %s", error)
        return

    logger.error("Unhandled error while processing update: %s", error, exc_info=error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ یه خطای غیرمنتظره پیش اومد. لطفاً دوباره امتحان کن یا با «back» برگرد."
            )
    except Exception:
        # A failure while delivering the fallback should not trigger another
        # error-handler cycle.
        logger.warning("Could not deliver the user-facing error message")


def register_handlers(client, platform: str):
    """Wire the shared handlers onto any client exposing add_handler() and
    .app (both TelegramClient and BaleClient implement this). `platform`
    ('telegram' | 'bale') is stashed in bot_data so every handler call can
    tell which platform it's running on for tenant resolution."""
    from telegram.ext import CommandHandler, MessageHandler, filters

    init_db()
    client.app.bot_data["platform"] = platform
    client.add_handler(CommandHandler("start", start))
    client.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    client.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_file))
    client.app.add_error_handler(on_error)