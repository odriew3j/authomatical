import os

if os.environ.get("RAILWAY_ENVIRONMENT") is None:
    from dotenv import load_dotenv
    load_dotenv()



class Config:
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    NINEROUTER_API_KEY = os.getenv("NINEROUTER_API_KEY")
    WORDPRESS_URL = os.getenv("WORDPRESS_URL")
    WORDPRESS_USER = os.getenv("WORDPRESS_USER")
    WORDPRESS_PASSWORD = os.getenv("WORDPRESS_PASSWORD")
    WC_CONSUMER_KEY = os.getenv("WC_CONSUMER_KEY")
    WC_CONSUMER_SECRET = os.getenv("WC_CONSUMER_SECRET")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    BALE_BOT_TOKEN = os.getenv("BALE_BOT_TOKEN")
    REDIS_URL = os.getenv("REDIS_URL")
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
    TIMEOUT = int(os.getenv("TIMEOUT", 30))

    # Multi-tenant storage: one DB row per (platform, chat_id) user, holding
    # their own connected WordPress/WooCommerce site — see database/.
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///authomatical.db")
    # Encrypts stored site secrets at rest. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    SECRET_KEY = os.getenv("SECRET_KEY")

    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
    TIMEOUT = int(os.getenv("TIMEOUT", 30))