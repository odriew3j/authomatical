"""Background worker that turns queued bot article jobs into WordPress posts.

Jobs include the originating platform/chat ID.  The worker resolves that
identity to the tenant's encrypted site connection at processing time, so an
article can only be published to the site that user connected in the bot.
"""
import html
import logging
from typing import Any

from clients.notify_client import send_platform_message
from clients.site_connector_client import SiteConnectorClient, SiteConnectorError
from database.db import init_db
from database.repository import get_or_create_tenant, get_wp_connection
from messaging.redis_broker import RedisBroker
from modules.wordpress_steps import WordPressSteps
from services.article_builder import ArticleBuilder
from services.image_service import ImageService
from utils.logging_utils import configure_worker_logging

logger = logging.getLogger(__name__)

# Client constructors are lazy, so module import does not require AI tokens or
# a reachable Redis server.  Tests can replace these module-level dependencies
# with fakes; production uses the real ones when work arrives.
broker = RedisBroker(stream="article_jobs")
article_builder = ArticleBuilder()
image_service = ImageService()

GROUP = "article_jobs_group"
CONSUMER = "article_worker_1"


def _positive_int(value: Any, default: int) -> int:
    """Read a positive job integer without letting a malformed stream field
    terminate the worker."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def store_temp_article(msg_id, article_data):
    """Keep an in-progress article briefly for diagnostics/recovery."""
    broker.redis.hset(
        f"article_temp:{msg_id}",
        mapping={key: str(value) for key, value in article_data.items()},
    )


def delete_temp_article(msg_id):
    broker.redis.delete(f"article_temp:{msg_id}")


def combine_article_html(article: dict) -> str:
    """Combine AI article fields into safe, structured WordPress HTML."""
    parts = []
    introduction = article.get("introduction", "")
    if introduction:
        parts.append(str(introduction))

    for chapter in article.get("chapters", []) or []:
        if not isinstance(chapter, dict):
            continue
        title = chapter.get("title") or chapter.get("chapterTitle") or ""
        content = chapter.get("content", "")
        if title:
            # Chapter titles are model output. Escape them before wrapping in
            # an allowed tag so an unexpected title cannot inject markup.
            parts.append(f"<h2>{html.escape(str(title))}</h2>")
        if content:
            parts.append(str(content))

    conclusions = article.get("conclusions", "")
    if conclusions:
        parts.append(str(conclusions))
    return "\n".join(parts)


def process_chain(msg_id, fields) -> bool:
    """Run the article pipeline once and acknowledge every terminal result.

    A failure is reported to the originating chat and then ACKed deliberately:
    blindly retrying can publish duplicate articles after an ambiguous network
    failure.  The user can submit again after correcting the site connection.
    """
    context: dict[str, Any] = {"fields": fields}
    platform = fields.get("platform")
    chat_id = fields.get("chat_id")

    for step in (
        WordPressSteps.BUILD_ARTICLE,
        WordPressSteps.STORE_TEMP,
        # WordPressSteps.GENERATE_IMAGE,  # optional; disabled by default
        WordPressSteps.COMBINE_HTML,
        WordPressSteps.CREATE_POST,
        WordPressSteps.CLEANUP,
        WordPressSteps.ACKNOWLEDGE,
    ):
        try:
            logger.info("[%s] Running step: %s", msg_id, step.value)

            if step == WordPressSteps.BUILD_ARTICLE:
                keywords = fields.get("keywords", "No Keywords")
                article_type = fields.get("article_type", "")
                notes = fields.get("notes", "")
                chapters = _positive_int(fields.get("chapters"), 5)
                tone = fields.get("tone", "informative")
                audience = fields.get("audience", "general")
                requested_words = _positive_int(fields.get("max_words"), 500)
                # Token usage includes JSON, HTML wrappers, and chapter
                # headings; a 3,000-token floor avoids predictable truncation
                # for small jobs while longer jobs scale with requested size.
                max_tokens = max(3000, int(requested_words * chapters * 1.5))

                context["article"] = article_builder.build_structure(
                    keywords=keywords,
                    article_type=article_type,
                    notes=notes,
                    num_chapters=chapters,
                    tone=tone,
                    audience=audience,
                    max_tokens=max_tokens,
                )

            elif step == WordPressSteps.STORE_TEMP:
                store_temp_article(msg_id, context["article"])

            elif step == WordPressSteps.GENERATE_IMAGE:
                # Kept for the optional workflow.  It is not in the default
                # step list above, so deployments do not need an image key.
                article = context["article"]
                context["image_data"] = image_service.generate(
                    article.get("title", ""), article.get("imagePrompt", "")
                )

            elif step == WordPressSteps.COMBINE_HTML:
                context["content_html"] = combine_article_html(context["article"])

            elif step == WordPressSteps.CREATE_POST:
                tenant_id = fields.get("tenant_id")
                if tenant_id:
                    # Web-dashboard-originated job: the caller already
                    # knows which tenant to publish to (no chat identity
                    # to resolve one from).
                    tenant_id = int(tenant_id)
                elif platform and chat_id:
                    tenant_id = get_or_create_tenant(platform, chat_id)
                else:
                    raise RuntimeError("job has neither tenant_id nor platform/chat_id; cannot resolve its tenant site")

                connection = get_wp_connection(tenant_id)
                if not connection:
                    raise RuntimeError("tenant has no connected site")

                site = SiteConnectorClient(connection["site_url"], connection["secret"])
                article = context["article"]
                result = site.create_post(
                    {
                        "title": article.get("title", "Untitled"),
                        "content": context["content_html"],
                        "slug": article.get("slug"),
                        "status": "publish",
                    }
                )
                context["post_id"] = result.get("post_id")
                context["post_url"] = result.get("url")

            elif step == WordPressSteps.CLEANUP:
                delete_temp_article(msg_id)

            elif step == WordPressSteps.ACKNOWLEDGE:
                send_success_message(fields, context.get("post_url"))
                broker.ack(GROUP, msg_id)
                logger.info("[%s] Completed successfully", msg_id)
                return True

        except SiteConnectorError as exc:
            logger.error("[%s] Failed at %s: %s", msg_id, step.value, exc)
            send_failure_message(fields, str(exc))
            broker.ack(GROUP, msg_id)
            return False
        except Exception:
            logger.exception("[%s] Failed at %s", msg_id, step.value)
            send_failure_message(fields, "یک خطای غیرمنتظره پیش اومد.")
            broker.ack(GROUP, msg_id)
            return False

    # Defensive fallback if the step list is changed without ACKNOWLEDGE.
    logger.error("[%s] Article pipeline ended without acknowledgement", msg_id)
    send_failure_message(fields, "یک خطای غیرمنتظره پیش اومد.")
    broker.ack(GROUP, msg_id)
    return False


def run_forever():
    configure_worker_logging()
    init_db()
    logger.info("Article Worker started. Waiting for jobs...")
    while True:
        messages = broker.consume(GROUP, CONSUMER, block=5000, count=1)
        if not messages:
            continue

        for _stream_name, stream_messages in messages:
            for msg_id, fields in stream_messages:
                logger.info("Received article job %s", msg_id)
                process_chain(msg_id, fields)


def send_success_message(fields, post_url=None):
    platform = fields.get("platform")
    chat_id = fields.get("chat_id")
    if not platform or not chat_id:
        logger.warning("Cannot send article success message: missing platform/chat_id")
        return False

    text = "✅ مقاله با موفقیت ساخته و روی سایتت منتشر شد."
    if post_url:
        text += f"\n🔗 {post_url}"

    delivered = send_platform_message(platform, chat_id, text)
    if not delivered:
        logger.warning("Failed to deliver article success message to %s:%s", platform, chat_id)
    return delivered


def send_failure_message(fields, reason: str):
    platform = fields.get("platform")
    chat_id = fields.get("chat_id")
    if not platform or not chat_id:
        logger.warning("Cannot send article failure message: missing platform/chat_id")
        return False

    return send_platform_message(platform, chat_id, f"⚠️ ساخت مقاله ناموفق بود: {reason}")


if __name__ == "__main__":
    run_forever()