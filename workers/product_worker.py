import logging
import re
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

def clean_description(desc: str) -> str:
    """Remove code fences like ```html, ```, ~~~ from AI output."""
    if not desc:
        return ""
    desc = re.sub(r"```(?:html)?", "", desc, flags=re.IGNORECASE)
    desc = desc.replace("```", "").replace("~~~", "")
    return desc.strip()

logging.info("Product Worker started. Waiting for jobs...")

while True:
    messages = broker.consume(GROUP, CONSUMER, block=5000, count=1)
    if not messages:
        continue

    for stream_name, msgs in messages:
        for msg_id, fields in msgs:
            fields = {
                (k.decode() if isinstance(k, bytes) else k):
                (v.decode() if isinstance(v, bytes) else v)
                for k, v in fields.items()
            }
            logging.info(f"Received job {msg_id}: {fields}")
    
            try:
                # 1. Manual fieldsre
                title = fields["title"]
                price = float(fields.get("price", 0))
                sale_price = float(fields.get("sale_price", 0)) if fields.get("sale_price") else None
                category = fields.get("category", "Uncategorized")
                brand = fields.get("brand")
                tags = fields.get("tags", "").split(",") if fields.get("tags") else []
                images = fields.get("images", "").split(",") if fields.get("images") else []
                stock_raw = fields.get("stock_quantity")
                try:
                    stock_quantity = int(stock_raw) if stock_raw not in (None, "", "None") else 0
                except ValueError:
                    stock_quantity = 0

                # 2. Generate all AI data
                ai_output = product_builder.generate_full_product(
                    title=title,
                    price=price,
                    sale_price=sale_price,
                    category=category,
                    brand=brand,
                    tags=tags
                )

                description = clean_description(ai_output.get("description", ""))
                seo_meta = ai_output.get("seo", {})
                hashtags = ai_output.get("hashtags", "")

                # convert hashtags to tags
                if hashtags:
                    tags.extend([h.strip().lstrip("#") for h in hashtags.split(",") if h.strip()])

                # 3. Product Creation in WordPress
                product_id = wp_product.create_product(
                    title=title,
                    description=description,
                    price=price,
                    sale_price=sale_price,
                    category=category,
                    brand=brand,
                    tags=tags,
                    images=images,
                    meta_title=seo_meta.get("title"),
                    meta_description=seo_meta.get("description"),
                    keywords=seo_meta.get("keywords"),
                    stock_quantity=stock_quantity,
                    upload_images=False
                )

                logging.info(f"✅ Created product: {title}, id={product_id}")
                broker.ack(GROUP, msg_id)

            except Exception as e:
                logging.error(f"❌ Failed to process product job {msg_id}: {e}")
                broker.ack(GROUP, msg_id)
