web: gunicorn services.web_app:app --bind 0.0.0.0:${PORT:-8080}
migrate: python -m alembic upgrade head
worker-article: python -m workers.article_worker
worker-telegram: python -m workers.telegram_worker
worker-bale: python -m workers.bale_worker
