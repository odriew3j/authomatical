import os

if os.environ.get("RAILWAY_ENVIRONMENT") is None:
    from dotenv import load_dotenv
    load_dotenv()



class Config:
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    WORDPRESS_URL = os.getenv("WORDPRESS_URL")
    WORDPRESS_USER = os.getenv("WORDPRESS_USER")
    WORDPRESS_PASSWORD = os.getenv("WORDPRESS_PASSWORD")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    REDIS_URL = os.getenv("REDIS_URL")
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
    TIMEOUT = int(os.getenv("TIMEOUT", 30))
