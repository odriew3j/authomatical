"""Small interactive CLI for submitting a durable Article job locally.

The CLI used to XADD raw article fields without a tenant, which made Redis the
only identity/history source and could not safely select a WordPress site.  It
now follows the same PostgreSQL-first path as the bot and web form.
"""
from database.db import init_db
from database.repository import (
    create_article_job,
    get_wp_connection,
    mark_article_job_failed,
    mark_article_job_queued,
)
from messaging.redis_broker import RedisBroker
from utils.helpers import log


if __name__ == "__main__":
    init_db()
    log("=== Durable Article Job Publisher ===")

    try:
        tenant_id = int(input("Tenant ID (a connected tenant from the database): ").strip())
    except ValueError:
        raise SystemExit("Tenant ID must be a positive integer.")
    if tenant_id <= 0 or not get_wp_connection(tenant_id):
        raise SystemExit("That tenant does not have a verified WordPress connection.")

    keywords = input("Enter main keywords/topic: ")
    chapters = input("Number of chapters (default 5): ")
    max_words = input("Max words per chapter/section (optional, default 500): ")
    tone = input("Tone (informative, persuasive, friendly, technical) [informative]: ")
    audience = input("Audience (general, developers, marketers, etc.) [general]: ")

    try:
        job_id = create_article_job(
            tenant_id,
            keywords=keywords,
            chapters=chapters or 5,
            max_words=max_words or 500,
            tone=tone or "informative",
            audience=audience or "general",
            source="cli",
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    broker = RedisBroker(stream="article_jobs")
    try:
        queue_message_id = broker.publish({"job_id": str(job_id)})
    except RuntimeError as exc:
        mark_article_job_failed(job_id, f"Redis queue publish failed: {exc}")
        raise SystemExit(f"Job {job_id} was recorded as FAILED because Redis is unavailable.") from exc

    mark_article_job_queued(job_id, queue_message_id)
    log(f"Queued durable article job id={job_id} (stream entry {queue_message_id})")
