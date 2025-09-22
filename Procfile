web: gunicorn services.web_app:app --bind 0.0.0.0:8080
worker-article: python -m workers.article_worker
worker-product: python -m workers.product_worker
worker-telegram: python -m workers.telegram_worker