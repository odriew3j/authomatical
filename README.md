# Authomatical — ربات ساخت محصول و مقاله برای WordPress

Authomatical یک ربات چندکاربره برای **بله** و **تلگرام** است که محصول‌های WooCommerce و مقاله‌های WordPress را با کمک AI می‌سازد و منتشر می‌کند.

هر کاربر سایت خودش را از طریق افزونهٔ همراه **ODview Sync** متصل می‌کند. اطلاعات اتصال هر سایت در PostgreSQL به‌صورت رمزنگاری‌شده ذخیره می‌شود؛ هیچ سایت یا secretای بین کاربران مشترک نیست.

## قابلیت‌های اصلی

- اتصال امن سایت WordPress از داخل گفتگو، بدون ارسال رمز عبور wp-admin
- ساخت محصول با مراحل «نوع محصول» و «توضیحات اختیاری» برای تولید محتوای فارسی دقیق‌تر
- slug انگلیسی و یکتا برای محصول، با اعتبارسنجی هم در Python و هم در افزونهٔ WordPress
- صف Redis برای مقاله‌ها و worker چندمستاجره که مقاله را فقط روی سایت همان کاربر منتشر می‌کند
- پیام موفقیت یا خطا به همان چت بله/تلگرام پس از پایان کار
- PostgreSQL + Alembic برای migrationهای قابل‌ردیابی؛ SQLite همچنان برای توسعهٔ سبک پشتیبانی می‌شود
- Docker Compose برای PostgreSQL، Redis، migration و workerها

## شروع سریع

```bash
cp .env.example .env
# مقدارهای OPENROUTER_API_KEY، SECRET_KEY، POSTGRES_PASSWORD و توکن bot را در .env وارد کنید.
docker compose --profile telegram up -d --build
# یا: docker compose --profile bale up -d --build
```

سپس افزونهٔ `wp-content/plugins/odview-sync` را روی سایت WordPress نصب/فعال کنید، در ربات `/start` بزنید و گزینهٔ `1` را برای اتصال سایت انتخاب کنید.

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
services/       AI builders و داشبورد قدیمی (برای انتشار production استفاده نشود)
wp-content/     افزونهٔ WordPress ODview Sync
tests/          تست‌های unit و integration سبک
```

## امنیت

- `.env` و کلیدهای API را commit نکنید.
- `SECRET_KEY` را پس از ذخیره‌شدن اتصال سایت‌ها تغییر ندهید؛ در غیر این صورت secretهای قبلی قابل خواندن نخواهند بود.
- secret نمایش‌داده‌شده در صفحهٔ «اتصال به بازو» WordPress معادل دسترسی انتشار از طریق ربات است؛ آن را خصوصی نگه دارید.

## مجوز

MIT License — برای جزئیات [LICENSE](LICENSE) را ببینید.
