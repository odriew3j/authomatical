import sqlite3

from database.repository import (
    ARTICLE_JOB_CLAIMED,
    ARTICLE_JOB_TERMINAL,
)


def test_tenant_isolation_across_platforms(test_db):
    """Same numeric chat_id on telegram vs bale must never collide."""
    t_tg = test_db.get_or_create_tenant("telegram", 111)
    t_bale = test_db.get_or_create_tenant("bale", 111)
    assert t_tg != t_bale


def test_get_or_create_tenant_is_idempotent(test_db):
    t1 = test_db.get_or_create_tenant("telegram", 111)
    t2 = test_db.get_or_create_tenant("telegram", 111)
    assert t1 == t2


def test_wp_connection_roundtrip_and_isolation(test_db):
    t_tg = test_db.get_or_create_tenant("telegram", 111)
    t_bale = test_db.get_or_create_tenant("bale", 111)

    test_db.save_wp_connection(t_tg, "https://siteA.example", "secretA")
    test_db.save_wp_connection(t_bale, "https://siteB.example", "secretB")

    conn_tg = test_db.get_wp_connection(t_tg)
    conn_bale = test_db.get_wp_connection(t_bale)

    assert conn_tg == {"site_url": "https://siteA.example", "secret": "secretA"}
    assert conn_bale == {"site_url": "https://siteB.example", "secret": "secretB"}


def test_unconnected_tenant_returns_none(test_db):
    t = test_db.get_or_create_tenant("telegram", 999)
    assert test_db.get_wp_connection(t) is None


def test_secret_is_encrypted_at_rest(test_db, tmp_path):
    t = test_db.get_or_create_tenant("telegram", 111)
    test_db.save_wp_connection(t, "https://site.example", "my-plaintext-secret")

    import database.db as dbmod
    db_file = dbmod.engine.url.database
    raw = sqlite3.connect(db_file)
    row = raw.execute(
        "SELECT secret_encrypted FROM wp_connections WHERE tenant_id=?", (t,)
    ).fetchone()
    assert "my-plaintext-secret" not in row[0]


def test_delete_wp_connection(test_db):
    t = test_db.get_or_create_tenant("telegram", 111)
    test_db.save_wp_connection(t, "https://site.example", "s3cr3t")
    assert test_db.delete_wp_connection(t) is True
    assert test_db.get_wp_connection(t) is None
    assert test_db.delete_wp_connection(t) is False  # already gone


# -------- Durable Article job repository --------
def test_article_job_persists_request_and_tenant_snapshot(test_db):
    tenant_id = test_db.get_or_create_tenant("telegram", 111, "کاربر")

    job_id = test_db.create_article_job(
        tenant_id,
        keywords="راهنمای انتخاب عینک",
        article_type="راهنمای خرید",
        notes="برای تازه‌کارها",
        chapters="6",
        max_words="700",
        tone="friendly",
        audience="new shoppers",
        featured_image_url="https://tenant.example/wp-content/uploads/cover.jpg",
        source="bot",
    )

    job = test_db.get_article_job(job_id, tenant_id=tenant_id)
    assert job is not None
    assert job["id"] == job_id
    assert job["tenant_id"] == tenant_id
    assert job["platform"] == "telegram"
    assert job["chat_id"] == "111"
    assert job["source"] == "bot"
    assert job["keywords"] == "راهنمای انتخاب عینک"
    assert job["article_type"] == "راهنمای خرید"
    assert job["notes"] == "برای تازه‌کارها"
    assert job["chapters"] == 6
    assert job["max_words"] == 700
    assert job["featured_image_url"] == "https://tenant.example/wp-content/uploads/cover.jpg"
    assert job["status"] == "PENDING"
    assert job["requested_at"] is not None
    assert job["attempts"] == []
    assert job["results"] == []


def test_article_job_featured_image_defaults_to_none_and_is_optional(test_db):
    tenant_id = test_db.get_or_create_tenant("telegram", 333)
    job_id = test_db.create_article_job(tenant_id, keywords="موضوع بدون تصویر")

    job = test_db.get_article_job(job_id, tenant_id=tenant_id)
    assert job["featured_image_url"] is None


def test_article_job_tenant_scoped_reads_never_cross_tenants(test_db):
    telegram_tenant = test_db.get_or_create_tenant("telegram", 111)
    bale_tenant = test_db.get_or_create_tenant("bale", 111)
    tg_job = test_db.create_article_job(telegram_tenant, keywords="موضوع تلگرام")
    bale_job = test_db.create_article_job(bale_tenant, keywords="موضوع بله")

    assert test_db.get_article_job(tg_job, tenant_id=bale_tenant) is None
    assert test_db.get_article_job(bale_job, tenant_id=telegram_tenant) is None
    assert [job["id"] for job in test_db.list_article_jobs(tenant_id=telegram_tenant)] == [tg_job]
    assert [job["id"] for job in test_db.list_article_jobs(tenant_id=bale_tenant)] == [bale_job]


def test_article_lifecycle_records_attempt_result_and_wordpress_outcome(test_db):
    tenant_id = test_db.get_or_create_tenant("telegram", 222)
    job_id = test_db.create_article_job(tenant_id, keywords="موضوع")

    assert test_db.mark_article_job_queued(job_id, b"1710000000000-0") is True
    claim = test_db.claim_pending_article_job(job_id)
    assert claim.outcome == ARTICLE_JOB_CLAIMED
    assert claim.job["id"] == job_id
    assert claim.job["attempt_number"] == 1
    assert claim.job["attempt_id"]

    article = {
        "title": "عنوان مقاله",
        "slug": "article-title-123abc",
        "subtitle": "زیرعنوان",
        "introduction": "<p>مقدمه</p>",
        "chapters": [{"title": "فصل اول", "content": "<p>متن</p>"}],
        "conclusions": "<p>نتیجه</p>",
        "imagePrompt": "editorial product photography",
    }
    result_id = test_db.save_article_result(
        job_id, claim.job["attempt_id"], article, "<p>مقدمه</p>\n<h2>فصل اول</h2>"
    )
    assert result_id
    assert test_db.mark_article_job_success(
        job_id,
        claim.job["attempt_id"],
        wordpress_post_id="44",
        wordpress_post_url="https://tenant.example/article-title-123abc",
    ) is True

    job = test_db.get_article_job(job_id)
    assert job["status"] == "SUCCESS"
    assert job["retry_count"] == 0
    assert job["queue_message_id"] == "1710000000000-0"
    assert job["queued_at"] is not None
    assert job["started_at"] is not None
    assert job["completed_at"] is not None
    assert job["wordpress_post_id"] == 44
    assert job["wordpress_post_url"].endswith("article-title-123abc")
    assert len(job["attempts"]) == 1
    attempt = job["attempts"][0]
    assert attempt["id"] == claim.job["attempt_id"]
    assert attempt["job_id"] == job_id
    assert attempt["attempt_number"] == 1
    assert attempt["status"] == "SUCCESS"
    assert attempt["error_message"] is None
    assert attempt["started_at"] is not None
    assert attempt["completed_at"] is not None
    assert job["results"][0]["attempt_id"] == claim.job["attempt_id"]
    assert job["results"][0]["slug"] == "article-title-123abc"
    assert job["results"][0]["chapters"] == article["chapters"]
    assert job["results"][0]["image_prompt"] == "editorial product photography"
    assert job["results"][0]["content_html"].startswith("<p>مقدمه")
    assert test_db.claim_pending_article_job(job_id).outcome == ARTICLE_JOB_TERMINAL


def test_article_failure_keeps_attempt_and_generated_result_for_audit(test_db):
    tenant_id = test_db.get_or_create_tenant("bale", 333)
    job_id = test_db.create_article_job(tenant_id, keywords="موضوع ناموفق")
    claim = test_db.claim_pending_article_job(job_id)
    assert claim.outcome == ARTICLE_JOB_CLAIMED

    test_db.save_article_result(
        job_id,
        claim.job["attempt_id"],
        {"title": "مقاله تولیدشده", "chapters": []},
        "<p>محتوا</p>",
    )
    assert test_db.mark_article_job_failed(
        job_id,
        "WordPress rejected the post: X-ODVIEW-SECRET=top-secret",
        attempt_id=claim.job["attempt_id"],
    ) is True

    job = test_db.get_article_job(job_id)
    assert job["status"] == "FAILED"
    assert job["completed_at"] is not None
    assert job["attempts"][0]["status"] == "FAILED"
    assert "top-secret" not in job["error_message"]
    assert job["results"][0]["title"] == "مقاله تولیدشده"
    # Terminal failures are deliberately not auto-claimed into a retry.
    assert test_db.claim_pending_article_job(job_id).outcome == ARTICLE_JOB_TERMINAL


def test_article_queue_failure_is_durable_without_fabricating_worker_attempt(test_db):
    tenant_id = test_db.get_or_create_tenant("telegram", 404)
    job_id = test_db.create_article_job(tenant_id, keywords="صف در دسترس نیست")

    assert test_db.mark_article_job_failed(job_id, "Redis queue publish failed: down") is True
    job = test_db.get_article_job(job_id)
    assert job["status"] == "FAILED"
    assert "Redis queue publish failed" in job["error_message"]
    assert job["attempts"] == []
    assert job["results"] == []


def test_article_job_creation_rejects_unknown_tenant_and_empty_keywords(test_db):
    tenant_id = test_db.get_or_create_tenant("telegram", 444)
    try:
        test_db.create_article_job(99999, keywords="موضوع")
        assert False, "expected an unknown tenant error"
    except ValueError as exc:
        assert "does not exist" in str(exc)

    try:
        test_db.create_article_job(tenant_id, keywords="  ")
        assert False, "expected empty keywords error"
    except ValueError as exc:
        assert "keywords" in str(exc)
