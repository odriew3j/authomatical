"""Tenant-selected web entry point for durable Article jobs."""
import logging
import os
import sys

from flask import Blueprint, jsonify, render_template, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.repository import (
    create_article_job,
    get_wp_connection,
    mark_article_job_failed,
    mark_article_job_queued,
)
from messaging.redis_broker import RedisBroker
from utils.helpers import log

logger = logging.getLogger(__name__)

template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
article_bp = Blueprint("article_bp", __name__, template_folder=template_dir)
broker = RedisBroker(stream="article_jobs")


@article_bp.route("/publish_article", methods=["GET"])
def index():
    return render_template("index_articles.html")


@article_bp.route("/publish_article", methods=["POST"])
def publish_article():
    """Persist an Article request, then queue only its durable ``job_id``.

    The web dashboard has no chat identity of its own, so an operator must
    select an existing tenant.  The repository copies platform/chat metadata
    from that tenant and the worker later resolves job -> tenant -> WordPress
    connection without trusting request or Redis routing fields.
    """

    data = request.json or {}
    raw_tenant_id = data.get("tenant_id")
    keywords = (data.get("keywords") or "").strip()

    if raw_tenant_id in (None, ""):
        return jsonify({"status": "error", "message": "tenant_id لازم است."}), 400
    try:
        tenant_id = int(raw_tenant_id)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "tenant_id معتبر نیست."}), 400
    if tenant_id <= 0:
        return jsonify({"status": "error", "message": "tenant_id معتبر نیست."}), 400
    if not keywords:
        return jsonify({"status": "error", "message": "موضوع/کلیدواژهٔ مقاله لازم است."}), 400

    featured_image_url = (data.get("featured_image_url") or "").strip() or None
    if featured_image_url and not featured_image_url.startswith(("http://", "https://")):
        return jsonify({"status": "error", "message": "آدرس تصویر شاخص باید یک URL معتبر باشد."}), 400
    # Must already be on the TENANT's own WordPress media library — the
    # plugin resolves it with attachment_url_to_postid, which silently
    # ignores any URL it doesn't recognize as a local attachment (no error
    # surfaces back through create-post if it doesn't match).

    # Give an early, clear error rather than creating a job that cannot ever
    # publish.  The worker repeats this check because a site can disconnect
    # while a durable job is waiting in the queue.
    if not get_wp_connection(tenant_id):
        return jsonify({"status": "error", "message": "این تنانت سایتی وصل نکرده است."}), 400

    try:
        job_id = create_article_job(
            tenant_id,
            keywords=keywords,
            article_type=data.get("article_type", ""),
            notes=data.get("notes", ""),
            chapters=data.get("chapters", 5),
            max_words=data.get("max_words", 500),
            tone=data.get("tone", "informative"),
            audience=data.get("audience", "general"),
            featured_image_url=featured_image_url,
            source="web",
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        logger.exception("Could not persist web article request for tenant=%s", tenant_id)
        return jsonify({"status": "error", "message": "ثبت درخواست مقاله در دیتابیس ناموفق بود."}), 503

    try:
        queue_message_id = broker.publish({"job_id": str(job_id)})
    except RuntimeError as exc:
        try:
            mark_article_job_failed(job_id, f"Redis queue publish failed: {exc}")
        except Exception:
            logger.exception("Could not record web Redis queue failure for article job=%s", job_id)
        log(f"Could not queue durable article job id={job_id}: {exc}")
        return jsonify({
            "status": "error",
            "job_id": job_id,
            "message": "صف Redis در دسترس نیست؛ درخواست در تاریخچه با وضعیت ناموفق ثبت شد.",
        }), 503

    try:
        mark_article_job_queued(job_id, queue_message_id)
    except Exception:
        # XADD already succeeded, so leave the durable PENDING job processable
        # instead of falsely marking it failed just because queue metadata
        # could not be recorded right away.
        logger.exception("Could not record queue message ID for web article job=%s", job_id)

    log(f"Queued durable article job id={job_id} (stream entry {queue_message_id})")
    return jsonify({"job_id": job_id, "status": "queued"})
