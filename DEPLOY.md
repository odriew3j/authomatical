# راه‌اندازی و استقرار Authomatical

این نسخه برای ربات چندکاربره‌ی بله/تلگرام طراحی شده است. هر کاربر سایت وردپرس خودش را با افزونه‌ی **ODview Sync** وصل می‌کند؛ نام‌کاربری و گذرواژه‌ی وردپرس در ربات ذخیره نمی‌شود. اطلاعات اتصال هر سایت با `SECRET_KEY` در دیتابیس رمزنگاری می‌شود.

## پیش‌نیازها

- Docker Engine و Docker Compose v2 برای روش پیشنهادی
- یک کلید OpenRouter (`OPENROUTER_API_KEY`) برای تولید متن
- توکن بله، تلگرام، یا هر دو
- یک سایت WordPress؛ برای ساخت محصول باید WooCommerce هم فعال باشد

> **نکتهٔ امنیتی:** فایل `.env` حاوی توکن‌ها و کلید رمزنگاری است. آن را commit یا ارسال نکنید. اگر `SECRET_KEY` را بعد از ثبت سایت‌ها عوض کنید، کلیدهای اتصال قبلی دیگر قابل رمزگشایی نیستند.

---

## ۱. آماده‌سازی تنظیمات

در ریشهٔ پروژه:

```bash
cp .env.example .env
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

خروجی دستور دوم را به‌عنوان مقدار `SECRET_KEY` در `.env` بگذارید. سپس دست‌کم این مقادیر را تکمیل کنید:

```dotenv
OPENROUTER_API_KEY=کلید-واقعی-OpenRouter
SECRET_KEY=کلید-واقعی-Fernet
POSTGRES_PASSWORD=یک-رمز-طولانی-و-URL-safe
TELEGRAM_BOT_TOKEN=توکن-تلگرام-درصورت-استفاده
BALE_BOT_TOKEN=توکن-بله-درصورت-استفاده
```

برای `POSTGRES_PASSWORD` از حروف و اعداد استفاده کنید، یا اگر از کاراکترهایی مانند `@` و `:` استفاده می‌کنید آن‌ها را URL-encode کنید؛ Docker Compose این مقدار را در URL اتصال PostgreSQL قرار می‌دهد.

متغیرهای قدیمی `WORDPRESS_URL`، `WORDPRESS_USER` و `WORDPRESS_PASSWORD` برای جریان فعلی ربات لازم نیستند.

---

## ۲. نصب افزونهٔ WordPress

1. پوشهٔ `wp-content/plugins/odview-sync` را zip کنید یا از فایل `odview-sync-plugin.zip` آماده استفاده کنید:

   ```bash
   (cd wp-content/plugins && zip -r ../../odview-sync-plugin.zip odview-sync)
   ```

2. در WordPress به **Plugins → Add New → Upload Plugin** بروید، فایل zip را نصب و افزونه را فعال کنید.
3. از منوی **«اتصال به بازو»** آدرس سایت و کلید امنیتی را بردارید.
4. در ربات `/start` را بفرستید، گزینهٔ `1` را انتخاب کنید، سپس آدرس و کلید را وارد کنید.

کلید افزونه را فقط در چت ربات خودتان وارد کنید. با گزینهٔ «ساخت کلید جدید» در WordPress، اتصال قبلی ربات عمداً نامعتبر می‌شود و باید دوباره وصل شود.

---

## ۳. اجرای پیشنهادی با Docker Compose

### فقط تلگرام

```bash
docker compose --profile telegram up -d --build
docker compose ps
docker compose --profile telegram logs -f migrate telegram-worker article-worker
```

### فقط بله

```bash
docker compose --profile bale up -d --build
docker compose ps
docker compose --profile bale logs -f migrate bale-worker article-worker
```

### هر دو ربات

```bash
docker compose --profile telegram --profile bale up -d --build
docker compose --profile telegram --profile bale logs -f
```

Compose به‌ترتیب PostgreSQL و Redis را بالا می‌آورد، سپس `alembic upgrade head` را اجرا می‌کند، و فقط پس از موفقیت migration، workerها را شروع می‌کند. `article-worker` باید همراه هر رباتی که فعال می‌کنید در حال اجرا باشد؛ مقاله‌ها در Redis صف می‌شوند و این worker آن‌ها را منتشر می‌کند.

> داشبورد Flask موجود در `services/web_app.py` یک جریان قدیمی و بدون احراز هویت tenant است؛ endpointهای آن نمی‌توانند مشخص کنند job متعلق به کدام سایت متصل است. برای انتشار production از مسیر ربات استفاده کنید و dashboard را تا زمانی که authentication/tenant selection به آن اضافه نشده، مبنای انتشار قرار ندهید.

دستورهای مفید:

```bash
# مشاهدهٔ وضعیت سرویس‌ها
docker compose ps

# مشاهدهٔ فقط خطاهای worker مقاله
docker compose logs -f article-worker

# توقف بدون پاک‌کردن داده‌ها
docker compose down

# هشدار: توقف و حذف کامل دیتابیس/Redis محلی
docker compose down -v
```

---

## ۴. اجرای محلی بدون Docker (برای توسعه)

در سه یا چهار ترمینال جداگانه اجرا کنید:

```bash
# یک بار: محیط و وابستگی‌ها
python3 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                   # اگر قبلاً نساخته‌اید

# در .env یک SECRET_KEY واقعی، OPENROUTER_API_KEY و توکن ربات بگذارید.
# برای توسعهٔ ساده با SQLite:
# DATABASE_URL=sqlite:///authomatical.db
# REDIS_URL=redis://localhost:6379/0

# یک بار بعد از هر تغییر migration
python -m alembic upgrade head
```

migration اولیه با دیتابیس SQLite قدیمی‌ای که قبلاً با `init_db()` ساخته شده نیز سازگار است؛ جدول‌های موجود را دوباره نمی‌سازد و فقط revision Alembic را ثبت می‌کند. بنابراین برای ارتقا لازم نیست فایل دیتابیس یا اتصال‌های سایت را پاک کنید.

سپس Redis را اجرا کنید (اگر به‌صورت سرویس سیستم نصب نشده است):

```bash
redis-server
```

و در ترمینال‌های دیگر، با محیط virtualenv فعال:

```bash
# برای پردازش مقاله‌ها؛ این مورد لازم است
python -m workers.article_worker

# یکی یا هر دو مورد، مطابق توکنی که در .env دارید
python -m workers.telegram_worker
python -m workers.bale_worker
```

`workers/product_worker.py` عمداً deprecated است؛ ساخت محصول به‌صورت مستقیم و tenant-scoped در گفت‌وگوی ربات انجام می‌شود، بنابراین آن را اجرا نکنید.

---

## ۵. استفاده در ربات

1. `/start` → گزینهٔ `1`: اتصال سایت از طریق افزونه
2. گزینهٔ `2`: ساخت محصول. ابتدا نام محصول، **نوع واقعی محصول** و توضیحات اختیاری را می‌دهید. در مرحلهٔ توضیحات `x` بفرستید تا رد شود. سپس قیمت/موجودی، دسته‌بندی و تصویرها را وارد کنید و با `پایان` انتشار را شروع کنید.
3. گزینهٔ `3`: موضوع مقاله را بدهید. job در صف قرار می‌گیرد و نتیجه (یا دلیل خطا) به همان چت بله/تلگرام ارسال می‌شود.

برای محصول، AI یک slug انگلیسی می‌سازد و Python و افزونهٔ WordPress هر دو آن را دوباره اعتبارسنجی می‌کنند؛ در نتیجه URL محصول فارسی نمی‌شود و یک suffix یکتا دارد.

---

## ۶. تست‌ها

همهٔ تست‌ها بدون Redis واقعی، OpenRouter، Telegram/Bale یا WordPress واقعی اجرا می‌شوند:

```bash
source .venv/bin/activate
python -m pytest -q
```

برای اجرای گروه‌های مهم به‌تنهایی:

```bash
python -m pytest tests/test_product_builder.py -q
python -m pytest tests/test_article_worker.py -q
python -m pytest tests/test_migrations.py -q
```

تست migration یک SQLite موقت می‌سازد، `alembic upgrade head` را اجرا می‌کند و وجود جدول‌های tenant و اتصال WordPress را تأیید می‌کند. هیچ داده‌ای از دیتابیس واقعی شما پاک یا تغییر داده نمی‌شود.

---

## رفع خطاهای رایج

| پیام / نشانه | راه‌حل |
| --- | --- |
| `SECRET_KEY is missing` | یک Fernet key بسازید و در `.env` قرار دهید؛ پس از ثبت سایت‌ها آن را عوض نکنید. |
| `Redis is unavailable` | وضعیت `redis` یا `redis-server` و مقدار `REDIS_URL` را بررسی کنید. job در این حالت منتشر نشده و می‌توانید دوباره ارسال کنید. |
| خطای 403 یا «کلید امنیتی نامعتبر» | آدرس و secret افزونه را در گزینهٔ 1 دوباره وارد کنید. اگر secret در WordPress regenerate شده، اتصال قبلی معتبر نیست. |
| خطای 404 افزونه | افزونهٔ ODview Sync را نصب/فعال کنید و URL ریشهٔ سایت را وارد کنید، نه `/wp-admin`. |
| worker دائماً restart می‌شود | `docker compose logs <service>` را ببینید؛ معمولاً توکن bot، `OPENROUTER_API_KEY` یا `SECRET_KEY` ناقص است. |
| migration اجرا نشد | `docker compose logs migrate` یا محلی `python -m alembic upgrade head` را اجرا کنید. |

## پشتیبان‌گیری

قبل از ارتقای production از PostgreSQL backup بگیرید. در Compose محلی می‌توانید از این دستور استفاده کنید:

```bash
docker compose exec -T postgres pg_dump -U authomatical authomatical > authomatical-backup.sql
```

فایل backup و `.env` را در محل امن و خارج از Git نگه دارید.
