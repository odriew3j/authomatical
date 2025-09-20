import logging
from messaging.redis_broker import RedisBroker
from services.article_builder import ArticleBuilder
from services.image_service import ImageService
from modules.wordpress_post import WordPressPostModule

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

# Worker setup
broker = RedisBroker(stream="article_jobs")
article_builder = ArticleBuilder()
image_service = ImageService()
wp_module = WordPressPostModule()

GROUP = "article_jobs_group"
CONSUMER = "article_worker_1"

logging.info("Article Worker started. Waiting for jobs...")

def store_temp_article(msg_id, article_data):
    """Store article temporarily in Redis for recovery"""
    broker.redis.hset(f"article_temp:{msg_id}", mapping={k: str(v) for k,v in article_data.items()})

def delete_temp_article(msg_id):
    broker.redis.delete(f"article_temp:{msg_id}")

while True:
    messages = broker.consume(GROUP, CONSUMER, block=5000, count=1)
    if not messages:
        continue

    for stream_name, msgs in messages:
        for msg_id, fields in msgs:
            # Convert bytes to str
            fields = {k.decode(): v.decode() for k, v in fields.items()}
            logging.info(f"Received job {msg_id}: {fields}")

            try:
                # Extract parameters with defaults
                keywords = fields.get("keywords", "No Keywords")
                chapters = int(fields.get("chapters", 5))
                tone = fields.get("tone", "informative")
                audience = fields.get("audience", "general")
                max_tokens = int(fields.get("max_words", 500)) * chapters

                # 1. Build article JSON
                article = article_builder.build_structure(
                    keywords=keywords,
                    num_chapters=chapters,
                    tone=tone,
                    audience=audience,
                    max_tokens=max_tokens
                )
                logging.info(f"Raw OpenRouter response: {article}")

                if not article:
                    raise ValueError("Failed to parse article JSON")

                # 2. Store temporarily in Redis
                store_temp_article(msg_id, article)

                # # 3. Generate image (optional)
                # image_data = None
                # try:
                #     image_data = image_service.generate(article.get("title",""), article.get("imagePrompt",""))
                # except Exception as e:
                #     logging.warning(f"[Image generation failed] {e}")


                # Combine all article parts into one HTML string
                content_html = article.get("introduction","") + "\n"

                for chapter in article.get("chapters", []):
                    content_html += f"{chapter.get('title','')} \n {chapter.get('content','')} \n"

                content_html += "\n" + article.get("conclusions","")
                
                # 4. Create post on WordPress
                post_id = wp_module.create_post(article.get("title","Untitled"), content_html, status="publish")

                # # 5. Upload image if available
                # if image_data:
                #     wp_module.upload_media(post_id, image_data, filename="featured.jpg")

                # 6. Log success and clean temp storage
                logging.info(f"Processed article for keywords: {keywords}, post_id={post_id}")
                delete_temp_article(msg_id)

                # 7. Acknowledge job
                broker.ack(GROUP, msg_id)

            except Exception as e:
                logging.error(f"Failed to process job {msg_id}: {e}")
                broker.ack(GROUP, msg_id)  # Ack even on failure to avoid blocking queue
