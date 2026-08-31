"""Background worker that turns durable Article jobs into WordPress posts.

PostgreSQL is the Article source of truth.  Redis is only a transport stream:
each new stream entry contains ``job_id`` and the worker obtains every request,
tenant, notification and WordPress-connection detail from that durable row.
Legacy Redis entries without a durable ID are intentionally left untouched for
explicit investigation/backfill; they are never inferred into a tenant site.
"""
import html
import logging
from typing import Any

from clients.notify_client import send_platform_message
from clients.site_connector_client import SiteConnectorClient, SiteConnectorError
from config import Config
from database.db import init_db
from database.repository import (
    ARTICLE_JOB_CLAIMED,
    ARTICLE_JOB_IN_PROGRESS,
    ARTICLE_JOB_MISSING,
    ARTICLE_JOB_TERMINAL,
    claim_pending_article_job,
    get_wp_connection,
    list_pending_article_job_ids,
    mark_article_job_failed,
    mark_article_job_queued,
    mark_article_job_success,
    save_article_result,
)
from messaging.redis_broker import RedisBroker
from services.article_builder import ArticleBuilder
from services.image_service import ImageService
from utils.logging_utils import configure_worker_logging, redact_sensitive_text

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
    """Read a positive job integer without letting malformed DB content
    terminate the worker."""

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _durable_job_id(fields: dict[str, Any]) -> int | None:
    """Return the durable Article ID carried by a new-format Redis entry.

    Do not fall back to a stream ID, tenant_id, platform or chat_id.  Those
    fallbacks would reintroduce the cross-tenant legacy behavior this worker
    is intentionally replacing.
    """

    raw_job_id = fields.get("job_id")
    if isinstance(raw_job_id, bytes):
        raw_job_id = raw_job_id.decode("utf-8", errors="replace")
    try:
        job_id = int(str(raw_job_id).strip())
    except (TypeError, ValueError):
        return None
    return job_id if job_id > 0 else None


def _temp_key(job_id: int) -> str:
    """Temporary Redis state is keyed by the durable DB ID, never b'ID'."""

    return f"article_temp:{int(job_id)}"


def store_temp_article(job_id: int, article_data: dict[str, Any]) -> None:
    """Keep short-lived diagnostic/intermediate data in Redis.

    This is intentionally best-effort in ``process_chain``: generated output
    is persisted in article_results before WordPress publishing, so a Redis
    hash outage must not become the system's sole record or block a valid job.
    """

    key = _temp_key(job_id)
    broker.redis.hset(
        key,
        mapping={str(field): str(value) for field, value in article_data.items()},
    )
    broker.redis.expire(key, Config.ARTICLE_TEMP_TTL_SECONDS)


def delete_temp_article(job_id: int) -> None:
    broker.redis.delete(_temp_key(job_id))


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


def _ack_terminal(msg_id: Any) -> None:
    """ACK only after the durable terminal state was committed.

    An ACK transport failure is logged but does not rewrite a terminal DB job.
    If Redis later redelivers that message, the worker sees SUCCESS/FAILED and
    safely ACKs the duplicate without publishing again.
    """

    try:
        acknowledged = broker.ack(GROUP, msg_id)
    except Exception:
        logger.exception("[%s] Redis ACK raised after durable terminal state", msg_id)
        return
    if not acknowledged:
        logger.warning("[%s] Redis ACK was not confirmed after durable terminal state", msg_id)


def _safe_send_success(job: dict[str, Any], post_url: str | None) -> None:
    try:
        send_success_message(job, post_url)
    except Exception:
        # Notification availability must not turn an already-published,
        # durable SUCCESS into a WordPress retry.
        logger.exception("[%s] Could not send success notification", job["id"])


def _safe_send_failure(job: dict[str, Any], reason: str) -> None:
    try:
        send_failure_message(job, reason)
    except Exception:
        # Same terminal rule for failures: recording/ACKing must not depend on
        # a remote Telegram/Bale delivery succeeding.
        logger.exception("[%s] Could not send failure notification", job["id"])


def _record_failure_and_ack(
    msg_id: Any,
    job: dict[str, Any],
    technical_reason: Any,
    user_reason: str,
) -> bool:
    """Persist FAILED and its attempt before notifying/ACKing the stream."""

    try:
        persisted = mark_article_job_failed(
            job["id"], technical_reason, attempt_id=job["attempt_id"]
        )
    except Exception:
        logger.exception("[%s] Could not persist article failure; leaving Redis entry pending", msg_id)
        return False

    if not persisted:
        logger.error("[%s] Article failure was not persisted; leaving Redis entry pending", msg_id)
        return False

    _safe_send_failure(job, user_reason)
    _ack_terminal(msg_id)
    return False


def _finalize_published_after_ancillary_error(
    msg_id: Any,
    job: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    """Recover if an error happens *after* create_post returned successfully.

    The WordPress side effect may already exist, so marking this attempt as a
    generic failed/retryable job could lead to a duplicate post.  Retry the
    durable SUCCESS write instead; if PostgreSQL is unavailable, retain the
    Redis entry for manual recovery rather than ACKing it blindly.
    """

    try:
        persisted = mark_article_job_success(
            job["id"],
            job["attempt_id"],
            context.get("post_id"),
            context.get("post_url"),
        )
    except Exception:
        logger.exception("[%s] WordPress post exists but SUCCESS could not be persisted", msg_id)
        return False

    if not persisted:
        logger.error("[%s] WordPress post exists but SUCCESS was rejected; leaving Redis entry pending", msg_id)
        return False

    try:
        delete_temp_article(job["id"])
    except Exception:
        logger.exception("[%s] Could not remove temporary article after publish", msg_id)
    _safe_send_success(job, context.get("post_url"))
    _ack_terminal(msg_id)
    return True


def process_chain(msg_id: Any, fields: dict[str, Any]) -> bool:
    """Run one durable Article job and ACK every *persisted* terminal result.

    Known success/failure outcomes are ACKed deliberately to avoid duplicate
    WordPress publishing after ambiguous external failures.  Messages that
    lack a durable job ID (the two legacy stream entries included) are neither
    ACKed nor inferred from untrusted platform/chat fields; they remain
    observation data until an explicit backfill policy is chosen.
    """

    job_id = _durable_job_id(fields)
    if job_id is None:
        logger.warning(
            "[%s] Legacy or malformed article stream entry has no valid durable job_id; "
            "leaving it unacknowledged for explicit migration",
            msg_id,
        )
        return False

    try:
        claim = claim_pending_article_job(job_id)
    except Exception:
        logger.exception("[%s] Could not claim durable article job=%s; leaving Redis entry pending", msg_id, job_id)
        return False

    if claim.outcome != ARTICLE_JOB_CLAIMED:
        if claim.outcome == ARTICLE_JOB_TERMINAL:
            # A duplicate stream delivery of a job already recorded as SUCCESS
            # or FAILED is safe to remove — no external work is performed.
            logger.info("[%s] Durable article job=%s is already terminal; ACKing duplicate", msg_id, job_id)
            _ack_terminal(msg_id)
        elif claim.outcome == ARTICLE_JOB_IN_PROGRESS:
            logger.warning("[%s] Durable article job=%s is already processing; leaving entry pending", msg_id, job_id)
        elif claim.outcome == ARTICLE_JOB_MISSING:
            logger.warning("[%s] Durable article job=%s does not exist; leaving entry pending for investigation", msg_id, job_id)
        else:
            logger.warning("[%s] Could not claim durable article job=%s (%s)", msg_id, job_id, claim.outcome)
        return False

    job = claim.job
    assert job is not None  # narrow type for the checks below
    context: dict[str, Any] = {}

    try:
        logger.info("[%s] Running durable article job=%s attempt=%s", msg_id, job["id"], job["attempt_number"])

        chapters = _positive_int(job.get("chapters"), 5)
        requested_words = _positive_int(job.get("max_words"), 500)
        # Token usage includes JSON, HTML wrappers, and chapter headings; a
        # 3,000-token floor avoids predictable truncation for small jobs while
        # longer jobs scale with requested size.
        max_tokens = max(3000, int(requested_words * chapters * 1.5))

        context["article"] = article_builder.build_structure(
            keywords=job["keywords"],
            article_type=job.get("article_type", ""),
            notes=job.get("notes", ""),
            num_chapters=chapters,
            tone=job.get("tone", "informative"),
            audience=job.get("audience", "general"),
            max_tokens=max_tokens,
        )

        # Make the generated output durable before any external side effect.
        # Redis temporary state comes afterward and is strictly optional.
        context["content_html"] = combine_article_html(context["article"])
        save_article_result(
            job["id"],
            job["attempt_id"],
            context["article"],
            context["content_html"],
        )

        try:
            store_temp_article(job["id"], context["article"])
        except Exception:
            logger.exception("[%s] Could not store optional temporary article data", msg_id)

        # Site selection starts exclusively at durable job -> tenant_id ->
        # verified WordPress connection.  Redis data has no authority here.
        connection = get_wp_connection(job["tenant_id"])
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
        # Set this immediately after the external call returns.  Anything that
        # fails afterward (including a malformed success response) must favor
        # recording SUCCESS over a duplicate retry.
        context["wordpress_post_created"] = True
        if not isinstance(result, dict):
            raise RuntimeError("WordPress publish returned an invalid response")
        context["post_id"] = result.get("post_id")
        context["post_url"] = result.get("url")

        if not mark_article_job_success(
            job["id"], job["attempt_id"], context["post_id"], context["post_url"]
        ):
            raise RuntimeError("Could not persist successful WordPress publish outcome")

    except SiteConnectorError as exc:
        logger.error("[%s] Article job=%s failed while talking to its tenant site: %s", msg_id, job["id"], exc)
        return _record_failure_and_ack(msg_id, job, str(exc), str(exc))
    except Exception as exc:
        if context.get("wordpress_post_created"):
            logger.exception("[%s] Error after WordPress post creation for job=%s", msg_id, job["id"])
            return _finalize_published_after_ancillary_error(msg_id, job, context)

        logger.exception("[%s] Article job=%s failed", msg_id, job["id"])
        technical_reason = f"{type(exc).__name__}: {exc}"
        return _record_failure_and_ack(
            msg_id,
            job,
            technical_reason,
            "یک خطای غیرمنتظره پیش اومد.",
        )

    # Cleanup/notification are explicitly after durable SUCCESS.  Neither can
    # convert a completed publish into a retryable job.
    try:
        delete_temp_article(job["id"])
    except Exception:
        logger.exception("[%s] Could not remove temporary article after success", msg_id)

    _safe_send_success(job, context.get("post_url"))
    _ack_terminal(msg_id)
    logger.info("[%s] Durable article job=%s completed successfully", msg_id, job["id"])
    return True


def recover_pending_article_jobs() -> None:
    """Re-emit unclaimed durable jobs after a worker/Redis interruption.

    There is intentionally no automatic replay for PROCESSING/FAILED jobs:
    either may have crossed the non-transactional WordPress publish boundary.
    PENDING jobs have no worker attempt yet, so putting their durable ID on
    Redis again is safe even if a prior XADD succeeded just before a crash.
    """

    try:
        pending_job_ids = list_pending_article_job_ids()
    except Exception:
        logger.exception("Could not load pending durable Article jobs for queue recovery")
        return

    if not pending_job_ids:
        return

    logger.info("Recovering %s pending durable Article job(s) into Redis", len(pending_job_ids))
    for job_id in pending_job_ids:
        try:
            queue_message_id = broker.publish({"job_id": str(job_id)})
        except Exception:
            # Keep it PENDING so a later worker startup can recover it; unlike
            # a user-facing submission failure, this is an internal retry of a
            # job that was already accepted durably.
            logger.exception("Could not recover pending durable Article job=%s into Redis", job_id)
            continue

        try:
            mark_article_job_queued(job_id, queue_message_id)
        except Exception:
            # The stream transport is already present.  The PENDING row can
            # still be claimed, and any later startup may harmlessly emit a
            # duplicate durable ID that the claim gate will suppress.
            logger.exception("Could not record recovery stream ID for article job=%s", job_id)


def run_forever() -> None:
    configure_worker_logging()
    init_db()
    recover_pending_article_jobs()
    logger.info("Article Worker started. Waiting for durable jobs...")
    while True:
        messages = broker.consume(GROUP, CONSUMER, block=5000, count=1)
        if not messages:
            continue

        for _stream_name, stream_messages in messages:
            for msg_id, fields in stream_messages:
                logger.info("Received article queue entry %s", msg_id)
                process_chain(msg_id, fields)


def send_success_message(job: dict[str, Any], post_url: str | None = None) -> bool:
    """Notify using the platform/chat snapshot loaded from a durable job."""

    platform = job.get("platform")
    chat_id = job.get("chat_id") or job.get("platform_chat_id")
    if not platform or not chat_id:
        logger.warning("Cannot send article success message for job=%s: missing durable platform/chat", job.get("id"))
        return False

    text = "✅ مقاله با موفقیت ساخته و روی سایتت منتشر شد."
    if post_url:
        text += f"\n🔗 {post_url}"

    delivered = send_platform_message(platform, chat_id, text)
    if not delivered:
        logger.warning("Failed to deliver article success message to durable job=%s", job.get("id"))
    return delivered


def send_failure_message(job: dict[str, Any], reason: str) -> bool:
    """Notify using only the durable job notification snapshot."""

    platform = job.get("platform")
    chat_id = job.get("chat_id") or job.get("platform_chat_id")
    if not platform or not chat_id:
        logger.warning("Cannot send article failure message for job=%s: missing durable platform/chat", job.get("id"))
        return False

    safe_reason = redact_sensitive_text(reason)[:1000]
    return send_platform_message(platform, chat_id, f"⚠️ ساخت مقاله ناموفق بود: {safe_reason}")


if __name__ == "__main__":
    run_forever()
