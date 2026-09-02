# Authomatical — ربات ساخت محصول و مقاله برای WordPress

Authomatical یک ربات چندکاربره برای **بله** و **تلگرام** است که محصول‌های WooCommerce و مقاله‌های WordPress را با کمک AI می‌سازد و منتشر می‌کند.

هر کاربر سایت خودش را از طریق افزونهٔ همراه **ODview Sync** متصل می‌کند. اطلاعات اتصال هر سایت در PostgreSQL به‌صورت رمزنگاری‌شده ذخیره می‌شود؛ هیچ سایت یا secretای بین کاربران مشترک نیست.

## قابلیت‌های اصلی

- اتصال امن سایت WordPress با دکمه/QR یک‌کلیکی برای بله یا تلگرام، بدون ارسال رمز عبور wp-admin یا کپی‌کردن secret در چت (مسیر دستی فقط برای بازیابی باقی مانده است)
- ساخت محصول و مقاله هر دو با مراحل «نوع/موضوع» و «توضیحات اختیاری» برای تولید محتوای فارسی دقیق‌تر و بدون کلی‌گویی
- slug انگلیسی و یکتا برای محصول و مقاله، با اعتبارسنجی هم در Python و هم در افزونهٔ WordPress
- PostgreSQL به‌عنوان منبع پایدار درخواست، تلاش‌ها، نتیجه و وضعیت مقاله؛ Redis فقط صف اجرای `job_id` و فضای موقت است
- worker چندمستاجره که مقاله را فقط از مسیر job → tenant → اتصال WordPress همان کاربر منتشر می‌کند
- پیام موفقیت یا خطا به همان چت بله/تلگرام پس از پایان کار
- داشبورد وب اختیاری برای ساخت محصول/مقاله بدون چت با ربات (نیاز به انتخاب تنانت؛ بدون authentication خودش — پشت reverse proxy یا شبکهٔ داخلی اجرا شود)
- PostgreSQL + Alembic برای migrationهای قابل‌ردیابی؛ SQLite همچنان برای توسعهٔ سبک پشتیبانی می‌شود
- Docker Compose برای PostgreSQL، Redis، migration و workerها

## شروع سریع

```bash
cp .env.example .env
# مقدارهای OPENROUTER_API_KEY، SECRET_KEY، POSTGRES_PASSWORD، توکن و username هر bot را در .env وارد کنید.
docker compose --profile telegram --profile connect up -d --build
# یا: docker compose --profile bale --profile connect up -d --build
```

سرویس `connect` را در یک دامنهٔ **عمومی HTTPS** پشت reverse proxy منتشر کنید (خود پورت Docker به‌تنهایی HTTPS نیست). سپس افزونهٔ `wp-content/plugins/odview-sync` را روی سایت WordPress نصب/فعال کنید، در صفحهٔ «اتصال به بازو» URL همین سرویس را یک‌بار ذخیره کنید و دکمهٔ تلگرام یا بله را بزنید. لینک/QR فقط چند دقیقه معتبر است و ربات اتصال را خودکار بررسی می‌کند. داشبورد `web` را عمومی نکنید؛ برای آن مسیر authentication جداگانه یا شبکهٔ خصوصی لازم است.

راهنمای کامل Docker، اجرای محلی، نصب افزونه، migration، تست و رفع خطاها در **[DEPLOY.md](DEPLOY.md)** است.

## تست

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
```

تست‌ها به سرویس خارجی یا Redis/WordPress واقعی نیاز ندارند.

## ساختار مهم پروژه

```text
clients/        API clients (site connector, AI, notifications)
database/       مدل‌ها، رمزنگاری و repository
migrations/     Alembic migrations
messaging/      Redis Streams wrapper
workers/        bot workers و article worker
services/       AI builders و داشبورد وب اختیاری (نیازمند انتخاب تنانت؛ بدون auth خودش)
wp-content/     افزونهٔ WordPress ODview Sync
tests/          تست‌های unit و integration سبک
```

## امنیت

- `.env` و کلیدهای API را commit نکنید.
- `SECRET_KEY` را پس از ذخیره‌شدن اتصال سایت‌ها تغییر ندهید؛ در غیر این صورت secretهای قبلی قابل خواندن نخواهند بود.
- secret نمایش‌داده‌شده در بخش دستی صفحهٔ «اتصال به بازو» WordPress معادل دسترسی انتشار از طریق ربات است؛ آن را خصوصی نگه دارید.
- اتصال یک‌کلیکی یک capability تصادفی ۲۵۶بیتی، تک‌بارمصرف و کوتاه‌عمر است. body ثبت با HMAC و زمان صدور امضا می‌شود تا replay قدیمی پذیرفته نشود؛ secret در URL، QR یا پاسخ AJAX برگردانده نمی‌شود و در PostgreSQL فقط به‌صورت رمزنگاری‌شده نگه‌داری می‌شود؛ خود token نیز فقط به‌شکل digest ذخیره می‌شود.
- فقط سرویس `connect` را برای URL ثبت‌شده در افزونه عمومی کنید و آن را پشت HTTPS قرار دهید. endpoint قبل از ثبت، HMAC و پاسخ authenticated `/ping` افزونه را بررسی می‌کند؛ با این وجود secret و QR را مانند credential موقت خصوصی نگه دارید.

## مجوز

MIT License — برای جزئیات [LICENSE](LICENSE) را ببینید.