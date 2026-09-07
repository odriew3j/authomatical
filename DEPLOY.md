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
# username عمومی bot بدون @؛ برای دکمه/QR یک‌کلیکی لازم است
TELEGRAM_BOT_USERNAME=your_telegram_bot
BALE_BOT_USERNAME=your_bale_bot
# capability اتصال فقط ۱ تا ۱۵ دقیقه معتبر می‌ماند (پیش‌فرض: ۶۰۰)
CONNECT_TOKEN_TTL_SECONDS=600
CONNECT_VERIFICATION_TIMEOUT_SECONDS=15
# request امضاشده فقط تا ۵ دقیقه قابل‌قبول است (برای جلوگیری از replay)
CONNECT_REGISTRATION_PROOF_MAX_AGE_SECONDS=300
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
3. آدرس عمومی سرویس `connect` را یک‌بار **در کد پلاگین** (ثابت `ODVIEW_SYNC_BACKEND_URL` در `odview-sync.php`) تنظیم کنید — این مقدار برای همهٔ مشتری‌ها یکی است و کاربر نهایی هرگز آن را نمی‌بیند یا وارد نمی‌کند. برای تست local/staging، بدون تغییر کد یا build جدا، همین یک خط را به `wp-config.php` همان سایت اضافه کنید: `define('ODVIEW_SYNC_BACKEND_URL', 'https://your-tunnel-url');` (باید پیش از بارگذاری پلاگین‌ها اجرا شود، یعنی قبل از خط `require_once ABSPATH . 'wp-settings.php'`).
4. از منوی **«اتصال به بازو»** روی **«اتصال با تلگرام»** یا **«اتصال با بله»** بزنید. افزونه به‌صورت server-to-server سایت و کلید خودش را نزد backend تأیید می‌کند، سپس یک لینک و QR کوتاه‌عمر می‌سازد.
5. لینک را باز کنید یا QR را اسکن کنید. دستور `/start connect_<token>` خودکار به همان worker می‌رسد، worker دوباره سایت را تست می‌کند و اتصال را فقط برای همان platform/chat ذخیره می‌کند. هیچ secretای را کپی یا داخل چت نمی‌فرستید.

هر دکمه یک token تصادفی ۲۵۶بیتی، تک‌بارمصرف و کوتاه‌عمر (پیش‌فرض ۱۰ دقیقه) برای **همان پلتفرم** می‌سازد؛ body ثبت هم با secret افزونه و زمان صدور HMAC می‌شود تا replay قدیمی پذیرفته نشود. QR به‌صورت محلی در backend SVG می‌شود و به سرویس QR خارجی فرستاده نمی‌شود. اگر token منقضی/استفاده/برای پلتفرم دیگر باشد یا تأیید سایت شکست بخورد، اتصال قبلی تنانت تغییر نمی‌کند؛ از WordPress دوباره لینک بسازید. برای سایت‌هایی که backend عمومی به آن‌ها دسترسی ندارد، بخش بازشدنی «اتصال دستی / بازیابی» در افزونه مسیر قدیمی را نگه می‌دارد.

کلید افزونه را فقط در مسیر دستی و فقط داخل چت ربات خودتان وارد کنید. با گزینهٔ «ساخت کلید جدید» در WordPress، اتصال قبلی ربات عمداً نامعتبر می‌شود و باید دوباره وصل شود.

---

## ۳. اجرای پیشنهادی با Docker Compose

### فقط تلگرام

```bash
docker compose --profile telegram --profile connect up -d --build
docker compose ps
docker compose --profile telegram --profile connect logs -f migrate telegram-worker article-worker connect
```

### فقط بله

```bash
docker compose --profile bale --profile connect up -d --build
docker compose ps
docker compose --profile bale --profile connect logs -f migrate bale-worker article-worker connect
```

### هر دو ربات

```bash
docker compose --profile telegram --profile bale --profile connect up -d --build
docker compose --profile telegram --profile bale --profile connect logs -f
```

Compose به‌ترتیب PostgreSQL و Redis را بالا می‌آورد، سپس `alembic upgrade head` را اجرا می‌کند، و فقط پس از موفقیت migration، workerها را شروع می‌کند. `article-worker` باید همراه هر رباتی که فعال می‌کنید در حال اجرا باشد؛ هر درخواست مقاله ابتدا با یک `article_jobs.id` پایدار در PostgreSQL ثبت می‌شود و Redis فقط همان `job_id` را برای اجرا حمل می‌کند. worker درخواست، tenant، اتصال WordPress، تلاش‌ها و نتیجه را از PostgreSQL می‌خواند/ثبت می‌کند و هرگز بر اساس `platform` یا `chat_id` داخل Redis سایت مقصد را انتخاب نمی‌کند.

### ارتقای schema پایدار (مقاله و اتصال یک‌کلیکی)

قبل از deploy این نسخه از PostgreSQL backup بگیرید و migration را **قبل از restart کردن workerها** اجرا کنید. در Compose، سرویس `migrate` این کار را در اجرای معمول `up` انجام می‌دهد؛ برای اجرای صریح نیز می‌توانید بزنید:

```bash
# Docker Compose
# profile لازم نیست؛ فقط schema را تا آخرین revision ارتقا می‌دهد.
docker compose run --rm migrate

# اجرای محلی با virtualenv فعال
python -m alembic upgrade head
python -m alembic current
```

revision جدید سه جدول پایدار می‌سازد:

- `article_jobs`: درخواست، tenant مالک، وضعیت `PENDING` / `PROCESSING` / `SUCCESS` / `FAILED`، زمان‌ها، خطا و شناسهٔ post وردپرس
- `article_attempts`: هر اجرای worker با شمارهٔ تلاش، زمان شروع/پایان و خطا
- `article_results`: خروجی ساخت‌یافتهٔ AI شامل عنوان، slug، فصل‌ها، image prompt و HTML، که **پیش از** انتشار WordPress ثبت می‌شود
- `pending_connections`: capabilityهای موقت اتصال یک‌کلیکی؛ token خام در آن ذخیره نمی‌شود، فقط digest، پلتفرم مقصد و secret رمزنگاری‌شده نگه‌داری می‌شوند. digest tombstone تا یک روز بعد از expiry باقی می‌ماند تا token مصرف‌شده revive نشود، سپس cleanup می‌شود.

migration سخت‌سازی pairing، recordهای بازِ revision قدیمی را عمداً revoke می‌کند، زیرا آن‌ها platform-bound نبودند. این‌ها فقط لینک‌های موقت‌اند و هیچ tenant connection یا history مقاله‌ای حذف/تغییر نمی‌کند؛ کاربر فقط یک لینک تازه می‌سازد.

پس از migration، bot/web/CLI جدید فقط payload زیر را در Stream می‌نویسد:

```text
job_id=<article_jobs.id>
```

شناسهٔ Redis مانند `1710000000000-0` صرفاً شناسهٔ حمل‌ونقل است و در ستون audit (`queue_message_id`) نگه داشته می‌شود؛ شناسهٔ اصلی مقاله نیست. کلیدهای موقت Redis نیز با شکل `article_temp:<database job id>` ساخته و پس از یک روز (قابل تنظیم با `ARTICLE_TEMP_TTL_SECONDS`) منقضی می‌شوند. حذف Redis هرگز تاریخچهٔ پایدار مقاله را حذف نمی‌کند. هنگام شروع `article-worker`، jobهای پایدارِ هنوز `PENDING` دوباره با همان `job_id` در صف قرار می‌گیرند؛ این فقط شکاف crash بین ثبت DB و `XADD` یا از‌دست‌رفتن Redis را جبران می‌کند و jobهای `PROCESSING`/`FAILED` را خودکار retry نمی‌کند.

#### پیام‌های قدیمی Redis

دو entry قدیمی Stream که `job_id` پایدار ندارند عمداً برای بررسی نگه داشته می‌شوند. worker جدید آن‌ها را **publish، ACK یا XDEL نمی‌کند** و از فیلدهای قدیمی `platform`/`chat_id` برای حدس‌زدن tenant استفاده نمی‌کند. تا وقتی سیاست backfill دستی و قابل ممیزی تصویب نشده است، آن‌ها را با دستورهای delete/requeue داشبورد هم حذف نکنید. برای مشاهدهٔ بدون تغییر داده:

```bash
docker compose exec redis redis-cli XRANGE article_jobs - +
docker compose exec redis redis-cli XPENDING article_jobs article_jobs_group
```

پیام‌های جدیدی که job آن‌ها به `SUCCESS` یا `FAILED` رسیده است بعد از ثبت وضعیت پایدار ACK می‌شوند؛ خطای رساندن پیام Telegram/Bale نتیجهٔ publish را retry نمی‌کند تا post تکراری ساخته نشود.

### سرویس عمومی اتصال یک‌کلیکی

سرویس profile `connect` عمداً فقط endpointهای زیر را دارد و باید در یک hostname عمومی HTTPS منتشر شود:

```text
POST /api/connect/register
POST /api/connect/status
GET  /api/connect/qr/<token>.svg?platform=telegram|bale
GET  /healthz
```

Container روی `8081` میزبان map می‌شود؛ برای production آن را مستقیماً با HTTP عمومی باز نکنید. یک reverse proxy/TLS terminator (nginx، Caddy، Cloudflare Tunnel و مانند آن) را روی دامنه‌ای مانند `https://connect.example.com` قرار دهید و همین URL ریشه را در افزونه ذخیره کنید. backend پیش از نگه‌داری token، HMAC درخواست و `GET /wp-json/odview/v1/ping` authenticated سایت را بررسی می‌کند؛ URL سایت باید HTTPS، عمومی و قابل resolve باشد و پاسخ DNS خصوصی/loopback رد می‌شود. برای defence-in-depth، egress سرویس را هم طوری محدود کنید که به subnetهای خصوصی/metadata دسترسی نداشته باشد. سپس worker در لحظهٔ بازشدن deep link همان ping بدون follow کردن redirect را دوباره انجام می‌دهد.

> **جداسازی مهم:** profile `web` داشبورد اپراتوری بدون authentication دارد. آن را با دامنه/پورت عمومی `connect` یکی نکنید و برای حل مسئله، همهٔ routeهای dashboard را anonymous نکنید. اگر به‌جای profile `connect` از همان Flask web app پشت proxy استفاده می‌کنید، فقط `/api/connect/*` را public allow کنید و root، `/articles/*`، `/products/*` و `/api/jobs/*` را private/authenticated نگه دارید.

### داشبورد وب (اختیاری)

اگر می‌خواهید بدون چت با ربات، برای هر تنانتِ متصل محصول/مقاله بسازید، داشبورد Flask را هم بالا بیاورید:

```bash
docker compose --profile web up -d --build
```

روی `http://localhost:8080` در دسترس است. فرم محصول و مقاله ابتدا لیست تنانت‌های متصل (سایت‌هایی که قبلاً از طریق ربات وصل شده‌اند) را نشان می‌دهند و شما یکی را انتخاب می‌کنید؛ ساخت محصول همزمان (synchronous) و مستقیم روی همان سایت انجام می‌شود، و مقاله مثل مسیر ربات در صف Redis قرار می‌گیرد.

> **هشدار امنیتی:** این داشبورد هیچ احراز هویتی ندارد. هرکسی که به این پورت دسترسی داشته باشد می‌تواند روی هر سایت متصلی محصول/مقاله بسازد. آن را پشت یک reverse proxy با auth (مثلاً Basic Auth در nginx) قرار دهید یا فقط در شبکهٔ داخلی/VPN در دسترس بگذارید — پورت `8080` را در فایروال عمومی باز نکنید.

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

### بازیابی Docker Desktop / DNS در Windows

اگر هر دو worker خطای `Temporary failure in name resolution`، `Name or service not known` یا `RemoteProtocolError` می‌دهند، مسئله از اتصال خارجی/DNS Docker Desktop است، نه Redis یا PostgreSQL. این ترتیب را در **PowerShell** اجرا کنید. هیچ‌کدام از این دستورها volume دیتابیس را حذف نمی‌کند:

```powershell
# اگر دستور قبلی وسط کار cancel شده، شبکه و containerهای همین پروژه را تمیز متوقف کن.
docker compose down --remove-orphans

# Docker Desktop را از system tray کاملاً Quit کن، سپس در PowerShell اجرا کن:
wsl --shutdown

# Docker Desktop را دوباره باز کن و صبر کن تا وضعیت Engine Running شود.
# سپس پروژه را دوباره بساز و اجرا کن:
docker compose --profile telegram --profile bale up -d --build --force-recreate
docker compose ps
```

`migrate` باید پس از migration با وضعیت `Exited (0)` دیده شود؛ این طبیعی است. `postgres` و `redis` باید `healthy` و workerها باید `running` باشند.

ابتدا DNS خود Windows را چک کنید:

```powershell
Resolve-DnsName api.telegram.org
Resolve-DnsName tapi.bale.ai
Test-NetConnection api.telegram.org -Port 443
Test-NetConnection tapi.bale.ai -Port 443
```

اگر Windows درست resolve می‌کند ولی containerها نه، از داخل container بررسی کنید:

```powershell
docker compose exec telegram-worker python -c "import socket; print(socket.gethostbyname('api.telegram.org'))"
docker compose exec bale-worker python -c "import socket; print(socket.gethostbyname('tapi.bale.ai'))"
```

اگر هنوز خطا دارید، یک override اختیاری برای DNS Docker فعال کنید:

```powershell
Copy-Item docker-compose.dns.example.yml docker-compose.override.yml
# در صورت نیاز، DNSهای مورد تأیید شبکهٔ خود را در .env با DOCKER_DNS_PRIMARY و DOCKER_DNS_SECONDARY تعیین کنید.
docker compose --profile telegram --profile bale up -d --force-recreate
```

فایل `docker-compose.override.yml` محلی است و وارد Git نمی‌شود. اگر شبکهٔ سازمانی/VPN دارید، به‌جای DNS عمومی از DNS مورد تأیید همان شبکه استفاده کنید. می‌توانید همین تنظیم را در Docker Desktop از مسیر **Settings → Resources → Network / Docker Engine** نیز اعمال و سپس **Apply & Restart** کنید.

برای دیدن log بدون باز ماندن دائمی terminal:

```powershell
docker compose logs --tail=100 telegram-worker bale-worker article-worker
```

`docker compose logs -f` فقط log را stream می‌کند؛ `Ctrl+C` در آن معمولاً containerها را متوقف نمی‌کند. اما `Ctrl+C` هنگام `up --force-recreate` ممکن است عملیات recreate را نیمه‌کاره بگذارد؛ در آن حالت دوباره از دستور `down --remove-orphans` بالا شروع کنید.

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

migration اولیه با دیتابیس SQLite قدیمی‌ای که قبلاً با `init_db()` ساخته شده نیز سازگار است؛ جدول‌های tenant/اتصال موجود را دوباره نمی‌سازد و فقط revision Alembic را ثبت می‌کند. migration بعدی جدول‌های پایدار مقاله را اضافه می‌کند. بنابراین برای ارتقا لازم نیست فایل دیتابیس، اتصال‌های سایت یا Stream Redis را پاک کنید — فقط `python -m alembic upgrade head` را پیش از شروع worker اجرا کنید.

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

# اختیاری: داشبورد وب برای ساخت محصول/مقاله بدون چت با ربات
python -m services.web_app          # روی http://127.0.0.1:5000 با debug=True
```

`workers/product_worker.py` عمداً deprecated است؛ ساخت محصول به‌صورت مستقیم و tenant-scoped در گفت‌وگوی ربات (و در فرم وب) انجام می‌شود، بنابراین آن را اجرا نکنید.

---

## ۵. استفاده در ربات

1. `/start` → گزینهٔ `1`: اتصال سایت از طریق افزونه
2. گزینهٔ `2`: ساخت محصول. ابتدا نام محصول، **نوع واقعی محصول** و توضیحات اختیاری را می‌دهید. در مرحلهٔ توضیحات `x` بفرستید تا رد شود. سپس قیمت/موجودی، دسته‌بندی و تصویرها را وارد کنید و با `پایان` انتشار را شروع کنید.
3. گزینهٔ `3`: ساخت مقاله. ابتدا موضوع، سپس **نوع مقاله** (راهنمای خرید، مقایسه، آموزشی و ...) و در آخر نکات/زاویهٔ اختیاری را می‌دهید (با `x` قابل رد است). ابتدا یک job پایدار در PostgreSQL ثبت می‌شود و شناسهٔ پیگیری آن نمایش داده می‌شود؛ سپس فقط همان شناسه وارد صف Redis می‌شود. نتیجه (یا دلیل خطا) به همان چت بله/تلگرام ارسال می‌شود.

برای محصول و مقاله هر دو، AI یک slug انگلیسی می‌سازد و Python و افزونهٔ WordPress هر دو آن را دوباره اعتبارسنجی می‌کنند؛ در نتیجه URL هرگز فارسی نمی‌شود و همیشه یک suffix یکتا دارد.

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

تست migration یک SQLite موقت می‌سازد، `alembic upgrade head` و downgrade را اجرا می‌کند و وجود جدول‌های tenant، اتصال WordPress و سه جدول پایدار مقاله را تأیید می‌کند. هیچ داده‌ای از دیتابیس واقعی شما پاک یا تغییر داده نمی‌شود.

---

## رفع خطاهای رایج

| پیام / نشانه | راه‌حل |
| --- | --- |
| `SECRET_KEY is missing` | یک Fernet key بسازید و در `.env` قرار دهید؛ پس از ثبت سایت‌ها آن را عوض نکنید. |
| `Redis is unavailable` | وضعیت `redis` یا `redis-server` و مقدار `REDIS_URL` را بررسی کنید. درخواست جدید ابتدا در PostgreSQL ثبت و سپس با وضعیت `FAILED` (خطای صف) ذخیره می‌شود؛ پس از رفع Redis یک درخواست تازه ثبت کنید. برای جلوگیری از post تکراری، job شکست‌خورده را خام و کورکورانه requeue نکنید. |
| خطای 403 یا «کلید امنیتی نامعتبر» | آدرس و secret افزونه را در گزینهٔ 1 دوباره وارد کنید. اگر secret در WordPress regenerate شده، اتصال قبلی معتبر نیست. |
| خطای 404 افزونه | افزونهٔ ODview Sync را نصب/فعال کنید و URL ریشهٔ سایت را وارد کنید، نه `/wp-admin`. |
| ساخت لینک یک‌کلیکی ناموفق است | `connect` باید روی HTTPS عمومی باشد، `TELEGRAM_BOT_USERNAME` یا `BALE_BOT_USERNAME` متناظر در `.env` تنظیم شود و backend بتواند URL HTTPS عمومی WordPress را resolve و `/wp-json/odview/v1/ping` را با secret افزونه تأیید کند. سپس `docker compose run --rm migrate` را اجرا کنید. |
| QR یا لینک می‌گوید منقضی/برای ربات دیگر | هر دکمه token جداگانه و platform-bound می‌سازد. از همان دکمه برای همان bot یک لینک تازه بسازید؛ token را در گروه/جای عمومی منتشر نکنید. |
| worker دائماً restart می‌شود | `docker compose logs <service>` را ببینید؛ معمولاً توکن bot، `OPENROUTER_API_KEY` یا `SECRET_KEY` ناقص است. |
| `Name or service not known` یا `ConnectTimeout` در polling | اگر چند بار اول رخ دهد و بعد `200 OK` ببینید، اختلال موقت DNS/TLS بوده و worker خودکار retry می‌کند. اگر ادامه‌دار است، DNS/فایروال/VPN میزبان را بررسی کنید: `docker compose exec bale-worker getent hosts tapi.bale.ai` و برای تلگرام `docker compose exec telegram-worker getent hosts api.telegram.org`. زمان‌های `BOT_*` در `.env` قابل تنظیم‌اند. |
| URLهای Bot API همراه token در لاگ قدیمی دیده می‌شوند | token را فوراً از BotFather (تلگرام) یا پنل بله regenerate/revoke کنید، سپس `.env` را به‌روزرسانی و workerها را recreate کنید. نسخهٔ فعلی URLهای موفق httpx را log نمی‌کند و formatter آن tokenها را redact می‌کند. |
| migration اجرا نشد | `docker compose logs migrate` یا محلی `python -m alembic upgrade head` را اجرا کنید. |

## پشتیبان‌گیری

قبل از ارتقای production از PostgreSQL backup بگیرید. در Compose محلی می‌توانید از این دستور استفاده کنید:

```bash
docker compose exec -T postgres pg_dump -U authomatical authomatical > authomatical-backup.sql
```

فایل backup و `.env` را در محل امن و خارج از Git نگه دارید.