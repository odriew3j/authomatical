"""Repository functions for tenant-scoped durable application data.

The article helpers in this module deliberately make PostgreSQL/SQLite the
source of truth.  Redis may transport an ``article_jobs.id`` to a worker, but
it is never consulted for tenant ownership, Article request data, lifecycle
state, results, or WordPress connection selection.
"""
import datetime
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func

from database.db import SessionLocal
from database.models import (
    Tenant,
    WPConnection,
    ArticleAttempt,
    ArticleJob,
    ArticleJobStatus,
    ArticleResult,
)
from database.crypto import encrypt, decrypt
from utils.logging_utils import redact_sensitive_text


ARTICLE_JOB_CLAIMED = "claimed"
ARTICLE_JOB_MISSING = "missing"
ARTICLE_JOB_IN_PROGRESS = "in_progress"
ARTICLE_JOB_TERMINAL = "terminal"


@dataclass(frozen=True)
class ArticleJobClaim:
    """Result of atomically claiming a pending article job for one worker."""

    outcome: str
    job: dict[str, Any] | None = None


def _utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _iso(value: datetime.datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text(value: Any, default: str = "", limit: int | None = None) -> str:
    if value is None:
        value = default
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    value = str(value).strip()
    if not value:
        value = default
    return value[:limit] if limit is not None else value


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_error_message(value: Any) -> str:
    """Retain useful failure context without allowing an unbounded/secrets
    bearing upstream exception to become permanent database content."""

    text = redact_sensitive_text(value).strip()
    return text[:4000] or "Article processing failed without an error message."


def _safe_chapters(value: Any) -> str:
    # ArticleBuilder normally supplies a list.  Store unexpected values too
    # (rather than losing an AI output because it was oddly shaped), in a
    # JSON form that remains portable across PostgreSQL and SQLite.
    try:
        return json.dumps(value if value is not None else [], ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return "[]"


def _decode_chapters(value: str | None) -> Any:
    if not value:
        return []
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return []


def _attempt_to_dict(attempt: ArticleAttempt) -> dict[str, Any]:
    return {
        "id": attempt.id,
        "job_id": attempt.job_id,
        "attempt_number": attempt.attempt_number,
        "status": attempt.status,
        "error_message": attempt.error_message,
        "started_at": _iso(attempt.started_at),
        "completed_at": _iso(attempt.completed_at),
    }


def _result_to_dict(result: ArticleResult) -> dict[str, Any]:
    return {
        "id": result.id,
        "job_id": result.job_id,
        "attempt_id": result.attempt_id,
        "title": result.title,
        "slug": result.slug,
        "subtitle": result.subtitle,
        "introduction": result.introduction,
        "chapters": _decode_chapters(result.chapters_json),
        "chapters_json": result.chapters_json,
        "conclusions": result.conclusions,
        "image_prompt": result.image_prompt,
        "content_html": result.content_html,
        "created_at": _iso(result.created_at),
        "updated_at": _iso(result.updated_at),
    }


def _job_to_dict(job: ArticleJob, include_history: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": job.id,
        "tenant_id": job.tenant_id,
        "platform": job.platform,
        "chat_id": job.platform_chat_id,
        "platform_chat_id": job.platform_chat_id,
        "source": job.source,
        "keywords": job.keywords,
        "article_type": job.article_type,
        "notes": job.notes,
        "chapters": job.chapters,
        "max_words": job.max_words,
        "tone": job.tone,
        "audience": job.audience,
        "status": job.status,
        "retry_count": job.retry_count,
        "error_message": job.error_message,
        "queue_message_id": job.queue_message_id,
        "requested_at": _iso(job.requested_at),
        "queued_at": _iso(job.queued_at),
        "started_at": _iso(job.started_at),
        "completed_at": _iso(job.completed_at),
        "updated_at": _iso(job.updated_at),
        "wordpress_post_id": job.wordpress_post_id,
        "wordpress_post_url": job.wordpress_post_url,
    }
    if include_history:
        data["attempts"] = [_attempt_to_dict(attempt) for attempt in job.attempts]
        data["results"] = [_result_to_dict(result) for result in job.results]
    return data


def get_or_create_tenant(platform: str, chat_id, display_name: str = None) -> int:
    """Returns the tenant_id for (platform, chat_id), creating the row on
    first contact. This is the single point that ties a bot conversation
    to a specific user's own data — every DB read/write for that
    conversation goes through this tenant_id, so one person's site
    credentials are never visible to another person's session."""

    chat_id = str(chat_id)
    with SessionLocal() as session:
        tenant = (
            session.query(Tenant)
            .filter_by(platform=platform, platform_chat_id=chat_id)
            .first()
        )
        if tenant:
            if display_name and tenant.display_name != display_name:
                tenant.display_name = display_name
                session.commit()
            return tenant.id

        tenant = Tenant(platform=platform, platform_chat_id=chat_id, display_name=display_name)
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        return tenant.id


def save_wp_connection(tenant_id: int, site_url: str, secret: str, verified: bool = True) -> None:
    with SessionLocal() as session:
        conn = session.query(WPConnection).filter_by(tenant_id=tenant_id).first()
        enc_secret = encrypt(secret)
        if conn:
            conn.site_url = site_url
            conn.secret_encrypted = enc_secret
            conn.verified = verified
        else:
            conn = WPConnection(
                tenant_id=tenant_id,
                site_url=site_url,
                secret_encrypted=enc_secret,
                verified=verified,
            )
            session.add(conn)
        session.commit()


def get_wp_connection(tenant_id: int) -> dict | None:
    """Returns {'site_url': ..., 'secret': ...} for a verified connection,
    or None if this tenant hasn't connected a site yet."""

    with SessionLocal() as session:
        conn = (
            session.query(WPConnection)
            .filter_by(tenant_id=tenant_id, verified=True)
            .first()
        )
        if not conn:
            return None
        return {"site_url": conn.site_url, "secret": decrypt(conn.secret_encrypted)}


def delete_wp_connection(tenant_id: int) -> bool:
    with SessionLocal() as session:
        conn = session.query(WPConnection).filter_by(tenant_id=tenant_id).first()
        if not conn:
            return False
        session.delete(conn)
        session.commit()
        return True


def list_connected_tenants() -> list[dict]:
    """Every tenant with a verified site connection — used by the admin
    web dashboard to let an operator pick which tenant's site to act on
    (the web app has no chat identity of its own, unlike the bot)."""

    with SessionLocal() as session:
        rows = (
            session.query(Tenant, WPConnection)
            .join(WPConnection, WPConnection.tenant_id == Tenant.id)
            .filter(WPConnection.verified.is_(True))
            .order_by(Tenant.id)
            .all()
        )
        return [
            {
                "tenant_id": tenant.id,
                "platform": tenant.platform,
                "chat_id": tenant.platform_chat_id,
                "display_name": tenant.display_name,
                "site_url": conn.site_url,
            }
            for tenant, conn in rows
        ]


# -------- Durable Article job lifecycle --------
def create_article_job(
    tenant_id: int,
    *,
    keywords: Any,
    article_type: Any = "",
    notes: Any = "",
    chapters: Any = 5,
    max_words: Any = 500,
    tone: Any = "informative",
    audience: Any = "general",
    source: Any = "bot",
) -> int:
    """Create a durable pending Article job before it is sent to Redis.

    Platform and chat metadata are copied from the existing tenant row rather
    than caller/queue input.  This prevents a caller from assigning an article
    to one tenant while claiming another user's notification identity.
    """

    normalized_keywords = _text(keywords)
    if not normalized_keywords:
        raise ValueError("Article keywords are required.")

    with SessionLocal() as session:
        tenant = session.get(Tenant, int(tenant_id))
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id} does not exist.")

        job = ArticleJob(
            tenant_id=tenant.id,
            platform=tenant.platform,
            platform_chat_id=tenant.platform_chat_id,
            source=_text(source, default="bot", limit=32),
            keywords=normalized_keywords,
            article_type=_text(article_type, limit=255),
            notes=_text(notes),
            chapters=_positive_int(chapters, 5),
            max_words=_positive_int(max_words, 500),
            tone=_text(tone, default="informative", limit=100),
            audience=_text(audience, default="general", limit=255),
            status=ArticleJobStatus.PENDING.value,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job.id


def mark_article_job_queued(job_id: int, queue_message_id: Any) -> bool:
    """Record successful Redis XADD without treating the stream ID as the
    durable job ID.  It is intentionally a best-effort audit field."""

    with SessionLocal() as session:
        job = session.get(ArticleJob, int(job_id))
        if job is None or job.status != ArticleJobStatus.PENDING.value:
            return False
        job.queue_message_id = _text(queue_message_id, limit=100)
        job.queued_at = _utcnow()
        session.commit()
        return True


def claim_pending_article_job(job_id: int) -> ArticleJobClaim:
    """Atomically move one *pending* job to PROCESSING and create its attempt.

    FAILED is deliberately not auto-claimed.  The worker ACKs terminal
    failures specifically to avoid duplicate WordPress posts after ambiguous
    external failures; a future/manual retry workflow must explicitly create a
    new queue transition instead of accidentally replaying a failed stream
    message.
    """

    with SessionLocal() as session:
        job = (
            session.query(ArticleJob)
            .filter(ArticleJob.id == int(job_id))
            .with_for_update()
            .one_or_none()
        )
        if job is None:
            return ArticleJobClaim(ARTICLE_JOB_MISSING)

        if job.status != ArticleJobStatus.PENDING.value:
            outcome = (
                ARTICLE_JOB_TERMINAL
                if job.status in (ArticleJobStatus.SUCCESS.value, ArticleJobStatus.FAILED.value)
                else ARTICLE_JOB_IN_PROGRESS
            )
            return ArticleJobClaim(outcome)

        prior_attempt_number = (
            session.query(func.max(ArticleAttempt.attempt_number))
            .filter(ArticleAttempt.job_id == job.id)
            .scalar()
            or 0
        )
        attempt_number = int(prior_attempt_number) + 1
        now = _utcnow()
        attempt = ArticleAttempt(
            job_id=job.id,
            attempt_number=attempt_number,
            status=ArticleJobStatus.PROCESSING.value,
            started_at=now,
        )
        job.status = ArticleJobStatus.PROCESSING.value
        job.started_at = now
        job.completed_at = None
        job.error_message = None
        # Attempt 1 means zero retries have occurred.  This preserves a clear
        # retry count without losing the full count in article_attempts.
        job.retry_count = attempt_number - 1
        session.add(attempt)
        session.flush()

        worker_job = {
            "id": job.id,
            "tenant_id": job.tenant_id,
            "platform": job.platform,
            "chat_id": job.platform_chat_id,
            "keywords": job.keywords,
            "article_type": job.article_type,
            "notes": job.notes,
            "chapters": job.chapters,
            "max_words": job.max_words,
            "tone": job.tone,
            "audience": job.audience,
            "attempt_id": attempt.id,
            "attempt_number": attempt.attempt_number,
        }
        session.commit()
        return ArticleJobClaim(ARTICLE_JOB_CLAIMED, worker_job)


def save_article_result(
    job_id: int,
    attempt_id: int,
    article: dict[str, Any],
    content_html: str,
) -> int:
    """Persist generated article output before WordPress publishing begins."""

    article = article if isinstance(article, dict) else {}
    with SessionLocal() as session:
        attempt = session.get(ArticleAttempt, int(attempt_id))
        if attempt is None or attempt.job_id != int(job_id):
            raise ValueError("Article attempt does not belong to this job.")

        result = session.query(ArticleResult).filter_by(attempt_id=attempt.id).one_or_none()
        values = {
            "job_id": int(job_id),
            "attempt_id": attempt.id,
            "title": _text(article.get("title"), default="Untitled", limit=500),
            "slug": _text(article.get("slug"), limit=500) or None,
            "subtitle": _text(article.get("subtitle")) or None,
            "introduction": _text(article.get("introduction")) or None,
            "chapters_json": _safe_chapters(article.get("chapters")),
            "conclusions": _text(article.get("conclusions")) or None,
            "image_prompt": _text(article.get("imagePrompt", article.get("image_prompt"))) or None,
            "content_html": str(content_html or ""),
        }
        if result is None:
            result = ArticleResult(**values)
            session.add(result)
        else:
            for key, value in values.items():
                setattr(result, key, value)
        session.commit()
        session.refresh(result)
        return result.id


def mark_article_job_success(
    job_id: int,
    attempt_id: int,
    wordpress_post_id: Any = None,
    wordpress_post_url: Any = None,
) -> bool:
    """Persist the terminal successful publishing outcome before Redis ACK."""

    with SessionLocal() as session:
        job = session.get(ArticleJob, int(job_id))
        attempt = session.get(ArticleAttempt, int(attempt_id))
        if job is None or attempt is None or attempt.job_id != job.id:
            return False
        if job.status == ArticleJobStatus.SUCCESS.value:
            return True

        now = _utcnow()
        job.status = ArticleJobStatus.SUCCESS.value
        job.completed_at = now
        job.error_message = None
        job.wordpress_post_id = _optional_int(wordpress_post_id)
        job.wordpress_post_url = _text(wordpress_post_url) or None
        attempt.status = ArticleJobStatus.SUCCESS.value
        attempt.completed_at = now
        attempt.error_message = None
        session.commit()
        return True


def mark_article_job_failed(
    job_id: int,
    error_message: Any,
    attempt_id: int | None = None,
) -> bool:
    """Persist a terminal failure (and its attempt when one was started).

    A completed successful job is never downgraded by a later ancillary error,
    such as a notification or Redis cleanup failure.
    """

    with SessionLocal() as session:
        job = session.get(ArticleJob, int(job_id))
        if job is None or job.status == ArticleJobStatus.SUCCESS.value:
            return False

        now = _utcnow()
        error = _safe_error_message(error_message)
        job.status = ArticleJobStatus.FAILED.value
        job.completed_at = now
        job.error_message = error

        if attempt_id is not None:
            attempt = session.get(ArticleAttempt, int(attempt_id))
            if attempt is None or attempt.job_id != job.id:
                raise ValueError("Article attempt does not belong to this job.")
            attempt.status = ArticleJobStatus.FAILED.value
            attempt.completed_at = now
            attempt.error_message = error

        session.commit()
        return True


def get_article_job(job_id: int, tenant_id: int | None = None) -> dict[str, Any] | None:
    """Fetch one durable job and its attempt/result history.

    Supplying ``tenant_id`` is the safe API for tenant-facing callers: a job
    belonging to any other tenant is indistinguishable from a missing job.
    The worker intentionally omits it because it begins from the durable job
    itself and uses that row's tenant_id for the WordPress lookup.
    """

    with SessionLocal() as session:
        query = session.query(ArticleJob).filter(ArticleJob.id == int(job_id))
        if tenant_id is not None:
            query = query.filter(ArticleJob.tenant_id == int(tenant_id))
        job = query.one_or_none()
        return _job_to_dict(job, include_history=True) if job is not None else None


def list_pending_article_job_ids(limit: int = 100) -> list[int]:
    """Return durable jobs that have not yet been claimed by a worker.

    This is the small transactional-outbox recovery hook used at article
    worker startup.  Re-emitting a PENDING job is safe: claim_pending_article_job
    permits exactly one worker to transition it to PROCESSING, while terminal
    jobs are never automatically replayed after an ambiguous publish failure.
    """

    safe_limit = max(1, min(int(limit), 500))
    with SessionLocal() as session:
        rows = (
            session.query(ArticleJob.id)
            .filter(ArticleJob.status == ArticleJobStatus.PENDING.value)
            .order_by(ArticleJob.requested_at.asc(), ArticleJob.id.asc())
            .limit(safe_limit)
            .all()
        )
        return [row[0] for row in rows]


def list_article_jobs(tenant_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """List recent durable jobs, optionally restricted to one tenant."""

    safe_limit = max(1, min(int(limit), 200))
    with SessionLocal() as session:
        query = session.query(ArticleJob)
        if tenant_id is not None:
            query = query.filter(ArticleJob.tenant_id == int(tenant_id))
        jobs = query.order_by(ArticleJob.requested_at.desc(), ArticleJob.id.desc()).limit(safe_limit).all()
        return [_job_to_dict(job, include_history=False) for job in jobs]
