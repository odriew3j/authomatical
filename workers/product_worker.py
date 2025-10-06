import logging
from messaging.redis_broker import RedisBroker
from clients.openrouter_client import OpenRouterClient
from modules.wordpress_product import WordPressProductModule
from services.product_builder import ProductBuilder

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

broker = RedisBroker(stream="product_jobs")
ai_service = OpenRouterClient()
wp_product = WordPressProductModule()
product_builder = ProductBuilder()

GROUP = "product_jobs_group"
CONSUMER = "product_worker_1"

logging.info("Product Worker started. Waiting for jobs...")

while True:
    messages = broker.consume(GROUP, CONSUMER, block=5000, count=1)
    if not messages:
        continue

    for stream_name, msgs in messages:
        for msg_id, fields in msgs:
        # Convert bytes to str safely
            fields = { (k.decode() if isinstance(k, bytes) else k):
                    (v.decode() if isinstance(v, bytes) else v)
                    for k, v in fields.items() }
            logging.info(f"Received job {msg_id}: {fields}")
    
            try:
                #1. Manual fields
                title = fields["title"]
                price = float(fields.get("price", 0))
                sale_price = float(fields.get("sale_price", 0)) if fields.get("sale_price") else None
                category = fields.get("category", "Uncategorized")
                brand = fields.get("brand")
                tags = fields.get("tags", "").split(",") if fields.get("tags") else []
                images = fields.get("images", "").split(",") if fields.get("images") else []

                #2. Description generation and SEO with AI
                description = product_builder.generate_description(
                    title, fields.get("keywords", ""), fields.get("tone", "informative"), fields.get("audience", "general")
                )
                seo_meta = product_builder.generate_seo(title, fields.get("keywords", ""))
                
                #3. Product Creation in WordPress
                product_id = wp_product.create_product(
                    title=title,
                    description=description,
                    price=price,
                    sale_price=sale_price,
                    category=category,
                    brand=brand,
                    tags=tags,
                    images=images,
                    meta_title=seo_meta["title"],
                    meta_description=seo_meta["description"],
                    keywords=seo_meta["keywords"]
                )

                logging.info(f"Created product: {title}, id={product_id}")
                broker.ack(GROUP, msg_id)

            except Exception as e:
                logging.error(f"Failed to process product job {msg_id}: {e}")
                broker.ack(GROUP, msg_id)
