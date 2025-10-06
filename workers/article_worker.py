# authomatical\workers\article_worker.py
import logging
from messaging.redis_broker import RedisBroker
from services.article_builder import ArticleBuilder
from services.image_service import ImageService
from modules.wordpress_article import WordPressArticleModule
from modules.wordpress_steps import WordPressSteps

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

# Worker setup
broker = RedisBroker(stream="article_jobs")
article_builder = ArticleBuilder()
image_service = ImageService()
wp_module = WordPressArticleModule()

GROUP = "article_jobs_group"
CONSUMER = "article_worker_1"

logging.info("Article Worker started. Waiting for jobs...")


def store_temp_article(msg_id, article_data):
    broker.redis.hset(f"article_temp:{msg_id}", mapping={k: str(v) for k, v in article_data.items()})


def delete_temp_article(msg_id):
    broker.redis.delete(f"article_temp:{msg_id}")


def process_chain(msg_id, fields):
    """Pipeline execution for article processing"""
    context = {"fields": fields}

    for step in [
        WordPressSteps.BUILD_ARTICLE,
        WordPressSteps.STORE_TEMP,
        # WordPressSteps.GENERATE_IMAGE,   # optional
        WordPressSteps.COMBINE_HTML,
        WordPressSteps.CREATE_POST,
        # WordPressSteps.UPLOAD_MEDIA,    # optional
        WordPressSteps.CLEANUP,
        WordPressSteps.ACKNOWLEDGE,
    ]:
        try:
            logging.info(f"[{msg_id}] Running step: {step.value}")

            if step == WordPressSteps.BUILD_ARTICLE:
                keywords = fields.get("keywords", "No Keywords")
                chapters = int(fields.get("chapters", 5))
                tone = fields.get("tone", "informative")
                audience = fields.get("audience", "general")
                max_tokens = int(fields.get("max_words", 500)) * chapters

                article = article_builder.build_structure(
                    keywords=keywords,
                    num_chapters=chapters,
                    tone=tone,
                    audience=audience,
                    max_tokens=max_tokens
                )
                context["article"] = article

            elif step == WordPressSteps.STORE_TEMP:
                store_temp_article(msg_id, context["article"])

            elif step == WordPressSteps.GENERATE_IMAGE:
                try:
                    article = context["article"]
                    image_data = image_service.generate(article.get("title", ""), article.get("imagePrompt", ""))
                    context["image_data"] = image_data
                except Exception as e:
                    logging.warning(f"[{msg_id}] Image generation failed: {e}")

            elif step == WordPressSteps.COMBINE_HTML:
                article = context["article"]

                content_html = article.get("introduction", "") + "\n"

                for chapter in article.get("chapters", []):
                    title = chapter.get("title") or chapter.get("chapterTitle") or ""
                    content = chapter.get("content", "")
                    content_html += f"{title}\n{content}\n"

                content_html += "\n" + article.get("conclusions", "")
                context["content_html"] = content_html


            elif step == WordPressSteps.CREATE_POST:
                article = context["article"]
                post_id = wp_module.create_post(article.get("title", "Untitled"), context["content_html"], status="publish")
                context["post_id"] = post_id

            elif step == WordPressSteps.UPLOAD_MEDIA:
                if "image_data" in context:
                    wp_module.upload_media(context["post_id"], context["image_data"], filename="featured.jpg")

            elif step == WordPressSteps.CLEANUP:
                delete_temp_article(msg_id)

            elif step == WordPressSteps.ACKNOWLEDGE:
                broker.ack(GROUP, msg_id)
                logging.info(f"[{msg_id}] ✅ Completed successfully")

        except Exception as e:
            logging.error(f"[{msg_id}] ❌ Failed at step {step.value}: {e}")
            broker.ack(GROUP, msg_id)  # Ack even on failure
            break


while True:
    messages = broker.consume(GROUP, CONSUMER, block=5000, count=1)
    if not messages:
        continue

    for stream_name, msgs in messages:
        for msg_id, fields in msgs:
            logging.info(f"Received job {msg_id}: {fields}")
            process_chain(msg_id, fields)