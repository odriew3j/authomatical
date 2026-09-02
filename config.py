import os

if os.environ.get("RAILWAY_ENVIRONMENT") is None:
    from dotenv import load_dotenv
    load_dotenv()


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """Read a deploy-time integer without allowing unsafe token lifetimes."""

    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return min(max(value, minimum), maximum)


class Config:
    # NineRouter: local multi-backend AI gateway (localhost:20128). It can
    # route a request to any of several underlying models — some of those
    # (e.g. reasoning models like deepseek-r1) burn tokens on <think>
    # blocks before producing real content, and can get truncated. See
    # NINEROUTER_MODEL below and clients/ninerouter_client.py for how
    # that's handled.
    NINEROUTER_API_KEY = os.getenv("NINEROUTER_API_KEY")
    # Their 9Router instance has a combo ("code-9router-combo") that fans
    # requests out across several backends (a mix of Fallback/Round-Robin/
    # Fusion strategies, including reasoning models like deepseek-r1).
    # NineRouterClient already strips <think> blocks, retries on truncated/
    # unparsable output, and logs finish_reason — so the combo is fine to
    # use directly. Override with a pinned model (e.g. "bg/gpt-4o-mini")
    # via .env if the combo proves too slow/unreliable in practice.
    NINEROUTER_MODEL = os.getenv("NINEROUTER_MODEL", "code-9router-combo")

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")

    WORDPRESS_URL = os.getenv("WORDPRESS_URL")
    WORDPRESS_USER = os.getenv("WORDPRESS_USER")
    WORDPRESS_PASSWORD = os.getenv("WORDPRESS_PASSWORD")
    WC_CONSUMER_KEY = os.getenv("WC_CONSUMER_KEY")
    WC_CONSUMER_SECRET = os.getenv("WC_CONSUMER_SECRET")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    BALE_BOT_TOKEN = os.getenv("BALE_BOT_TOKEN")
    # @username of each bot (no leading @), used only to build the
    # /start connect_<token> deep links returned by the one-click connect
    # endpoint (services/blueprints/connect.py) — never used for auth.
    TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME")
    BALE_BOT_USERNAME = os.getenv("BALE_BOT_USERNAME")
    # A one-click pairing link is a bearer capability. Keep it deliberately
    # short-lived even when an environment value was accidentally set too high.
    CONNECT_TOKEN_TTL_SECONDS = _bounded_env_int(
        "CONNECT_TOKEN_TTL_SECONDS", default=600, minimum=60, maximum=900,
    )
    # Registration proves possession of the WordPress plugin secret by pinging
    # the site before saving anything. This public endpoint gets a bounded,
    # independent network budget rather than the longer AI/site-operation one.
    CONNECT_VERIFICATION_TIMEOUT_SECONDS = _bounded_env_int(
        "CONNECT_VERIFICATION_TIMEOUT_SECONDS", default=15, minimum=3, maximum=30,
    )
    # Signed registration requests are accepted only near their creation time.
    # This complements the digest tombstone retained after expiry/consumption
    # and prevents a captured body from reviving an old deep link.
    CONNECT_REGISTRATION_PROOF_MAX_AGE_SECONDS = _bounded_env_int(
        "CONNECT_REGISTRATION_PROOF_MAX_AGE_SECONDS", default=300, minimum=60, maximum=600,
    )
    REDIS_URL = os.getenv("REDIS_URL")
    # Redis only keeps short-lived diagnostic/intermediate article data. The
    # durable request/result/lifecycle records live in PostgreSQL.
    ARTICLE_TEMP_TTL_SECONDS = int(os.getenv("ARTICLE_TEMP_TTL_SECONDS", "86400"))
    # Reasoning-capable backends behind NineRouter can genuinely take
    # 30-90s; 30s was cutting real (non-stuck) generations off mid-flight.
    # Keep MAX_RETRIES modest since each retry can itself take a minute+.
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 2))
    TIMEOUT = int(os.getenv("TIMEOUT", 120))

    # Bot API transport settings are deliberately independent of the AI/site
    # timeout above. python-telegram-bot otherwise defaults to a very short
    # 5-second connect timeout, which makes transient container DNS/TLS delays
    # look like fatal worker errors.
    BOT_CONNECT_TIMEOUT = float(os.getenv("BOT_CONNECT_TIMEOUT", 30))
    BOT_READ_TIMEOUT = float(os.getenv("BOT_READ_TIMEOUT", 30))
    BOT_WRITE_TIMEOUT = float(os.getenv("BOT_WRITE_TIMEOUT", 30))
    BOT_POOL_TIMEOUT = float(os.getenv("BOT_POOL_TIMEOUT", 10))
    BOT_POLL_TIMEOUT = int(os.getenv("BOT_POLL_TIMEOUT", 30))
    BOT_POLL_READ_TIMEOUT = float(os.getenv("BOT_POLL_READ_TIMEOUT", 45))
    BOT_POLL_INTERVAL = float(os.getenv("BOT_POLL_INTERVAL", 1))

    # Multi-tenant storage: one DB row per (platform, chat_id) user, holding
    # their own connected WordPress/WooCommerce site — see database/.
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///authomatical.db")
    # Encrypts stored site secrets at rest. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    SECRET_KEY = os.getenv("SECRET_KEY")