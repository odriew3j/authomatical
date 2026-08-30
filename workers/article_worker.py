# authomatical\workers\article_worker.py
import logging
from messaging.redis_broker import RedisBroker
from services.article_builder import ArticleBuilder
from services.image_service import ImageService
from modules.wordpress_article import WordPressArticleModule
from modules.wordpress_steps import WordPressSteps

from clients.bale_client import BaleClient
from clients.telegram_client import TelegramClient

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
                # words != tokens, and the HTML/JSON wrapper (chapter titles,
                # <p> tags, field names) costs tokens too — 1 word/token was
                # starving generations, causing finish_reason="length" and
                # truncated/unparsable JSON. ~1.5 tokens per requested word,
                # times chapters, with a 3000-token floor.
                requested_words = int(fields.get("max_words", 500))
                max_tokens = max(3000, int(requested_words * chapters * 1.5))

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
                send_success_message(fields)

                broker.ack(GROUP, msg_id)

                logging.info(
                    f"[{msg_id}] ✅ Completed successfully"
                )

        except Exception as e:
            logging.error(f"[{msg_id}] ❌ Failed at step {step.value}: {e}")
            broker.ack(GROUP, msg_id)  # Ack even on failure
            break


def run_forever():
    while True:
        messages = broker.consume(GROUP, CONSUMER, block=5000, count=1)
        if not messages:
            continue

        for stream_name, msgs in messages:
            for msg_id, fields in msgs:
                logging.info(f"Received job {msg_id}: {fields}")
                process_chain(msg_id, fields)


def send_success_message(fields):
    platform = fields.get("platform")
    chat_id = fields.get("chat_id")

    if not platform or not chat_id:
        logging.warning("Cannot send success message: missing platform/chat_id")
        return

    try:
        if platform == "bale":
            client = BaleClient()
        elif platform == "telegram":
            client = TelegramClient()
        else:
            logging.warning("Unknown platform: %s", platform)
            return

        client.send_message(
            chat_id=int(chat_id),
            text="✅ مقاله با موفقیت ساخته و روی سایتت منتشر شد."
        )

    except Exception as e:
        logging.error(
            "Failed to send article success message: %s",
            e,
            exc_info=True,
        )


if __name__ == "__main__":
    run_forever()