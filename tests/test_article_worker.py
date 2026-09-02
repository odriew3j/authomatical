from unittest.mock import MagicMock

from clients.site_connector_client import SiteConnectorError
from workers import article_worker as worker


class FakeBroker:
    def __init__(self, on_ack=None):
        self.redis = MagicMock()
        self.acks = []
        self.on_ack = on_ack

    def ack(self, group, msg_id):
        if self.on_ack:
            self.on_ack(group, msg_id)
        self.acks.append((group, msg_id))
        return True


class FakeArticleBuilder:
    def __init__(self):
        self.kwargs = None

    def build_structure(self, **kwargs):
        self.kwargs = kwargs
        return {
            "title": "راهنمای عینک",
            "slug": "sunglasses-buying-guide-123abc",
            "subtitle": "انتخاب آگاهانه",
            "introduction": "<p>مقدمه</p>",
            "imagePrompt": "editorial sunglasses on a table",
            "chapters": [{"title": "فصل <اول>", "content": "<p>محتوای فصل</p>"}],
            "conclusions": "<p>جمع‌بندی</p>",
        }


class SuccessfulSite:
    instances = []
    inspect_before_publish = None

    def __init__(self, site_url, secret):
        self.site_url = site_url
        self.secret = secret
        self.payload = None
        self.__class__.instances.append(self)

    def create_post(self, payload):
        self.payload = payload
        if self.__class__.inspect_before_publish:
            self.__class__.inspect_before_publish()
        return {"success": True, "post_id": 31, "url": "https://tenant.example/guide"}


class FailingSite(SuccessfulSite):
    def create_post(self, payload):
        self.payload = payload
        raise SiteConnectorError("کلید امنیتی نامعتبر است")


def _create_durable_job(test_db, *, platform="telegram", chat_id=1001, with_connection=True, **kwargs):
    tenant_id = test_db.get_or_create_tenant(platform, chat_id)
    if with_connection:
        test_db.save_wp_connection(tenant_id, "https://tenant.example", "tenant-secret")
    job_id = test_db.create_article_job(
        tenant_id,
        keywords=kwargs.pop("keywords", "راهنمای انتخاب عینک"),
        **kwargs,
    )
    test_db.mark_article_job_queued(job_id, "1710000000000-0")
    return tenant_id, job_id


def _install_worker_dependencies(monkeypatch, fake_broker, fake_builder, site_class):
    site_class.instances = []
    site_class.inspect_before_publish = None
    monkeypatch.setattr(worker, "broker", fake_broker)
    monkeypatch.setattr(worker, "article_builder", fake_builder)
    monkeypatch.setattr(worker, "SiteConnectorClient", site_class)


def test_process_chain_uses_durable_job_tenant_and_persists_success_before_ack(test_db, monkeypatch):
    tenant_id, job_id = _create_durable_job(
        test_db,
        keywords="کلیدواژهٔ واقعی ذخیره‌شده",
        article_type="راهنمای خرید",
        notes="برای تازه‌کارها",
    )
    statuses_seen_at_ack = []
    broker = FakeBroker(on_ack=lambda *_args: statuses_seen_at_ack.append(test_db.get_article_job(job_id)["status"]))
    builder = FakeArticleBuilder()
    sent = MagicMock(return_value=True)
    _install_worker_dependencies(monkeypatch, broker, builder, SuccessfulSite)
    monkeypatch.setattr(worker, "send_platform_message", sent)

    completed = worker.process_chain(
        "stream-1-0",
        {
            "job_id": str(job_id),
            # Deliberately hostile/stale queue fields must be ignored.
            "keywords": "نباید استفاده شود",
            "tenant_id": "999",
            "platform": "bale",
            "chat_id": "attacker-chat",
        },
    )

    assert completed is True
    assert builder.kwargs["keywords"] == "کلیدواژهٔ واقعی ذخیره‌شده"
    assert builder.kwargs["article_type"] == "راهنمای خرید"
    assert builder.kwargs["notes"] == "برای تازه‌کارها"
    assert builder.kwargs["max_tokens"] == 3750
    site = SuccessfulSite.instances[0]
    assert site.site_url == "https://tenant.example"
    assert site.secret == "tenant-secret"
    assert site.payload["title"] == "راهنمای عینک"
    assert site.payload["slug"] == "sunglasses-buying-guide-123abc"
    assert site.payload["status"] == "publish"
    assert "<h2>فصل &lt;اول&gt;</h2>" in site.payload["content"]
    assert "<p>جمع‌بندی</p>" in site.payload["content"]

    broker.redis.hset.assert_called_once()
    assert broker.redis.hset.call_args.args[0] == f"article_temp:{job_id}"
    broker.redis.expire.assert_called_once_with(f"article_temp:{job_id}", worker.Config.ARTICLE_TEMP_TTL_SECONDS)
    broker.redis.delete.assert_called_once_with(f"article_temp:{job_id}")
    assert broker.acks == [(worker.GROUP, "stream-1-0")]
    assert statuses_seen_at_ack == ["SUCCESS"]

    durable_job = test_db.get_article_job(job_id, tenant_id=tenant_id)
    assert durable_job["status"] == "SUCCESS"
    assert durable_job["wordpress_post_id"] == 31
    assert durable_job["wordpress_post_url"] == "https://tenant.example/guide"
    assert durable_job["attempts"][0]["status"] == "SUCCESS"
    assert durable_job["results"][0]["title"] == "راهنمای عینک"
    assert durable_job["results"][0]["content_html"] == site.payload["content"]
    assert sent.call_args.args[:2] == ("telegram", "1001")
    assert "https://tenant.example/guide" in sent.call_args.args[2]


def test_process_chain_forwards_featured_image_url_to_create_post(test_db, monkeypatch):
    tenant_id, job_id = _create_durable_job(
        test_db,
        featured_image_url="https://tenant.example/wp-content/uploads/cover.jpg",
    )
    broker = FakeBroker()
    builder = FakeArticleBuilder()
    _install_worker_dependencies(monkeypatch, broker, builder, SuccessfulSite)
    monkeypatch.setattr(worker, "send_platform_message", MagicMock(return_value=True))

    completed = worker.process_chain("stream-1-0", {"job_id": str(job_id)})

    assert completed is True
    site = SuccessfulSite.instances[0]
    assert site.payload["featured_image"] == "https://tenant.example/wp-content/uploads/cover.jpg"


def test_process_chain_sends_none_featured_image_when_job_has_no_image(test_db, monkeypatch):
    tenant_id, job_id = _create_durable_job(test_db)
    broker = FakeBroker()
    builder = FakeArticleBuilder()
    _install_worker_dependencies(monkeypatch, broker, builder, SuccessfulSite)
    monkeypatch.setattr(worker, "send_platform_message", MagicMock(return_value=True))

    worker.process_chain("stream-1-0", {"job_id": str(job_id)})

    site = SuccessfulSite.instances[0]
    assert site.payload["featured_image"] is None


def test_worker_persists_generated_result_before_wordpress_publish(test_db, monkeypatch):
    _tenant_id, job_id = _create_durable_job(test_db)
    broker = FakeBroker()
    builder = FakeArticleBuilder()
    _install_worker_dependencies(monkeypatch, broker, builder, SuccessfulSite)
    monkeypatch.setattr(worker, "send_platform_message", MagicMock(return_value=True))

    observed = []

    def inspect_before_publish():
        job = test_db.get_article_job(job_id)
        observed.append((job["status"], len(job["results"]), job["results"][0]["title"]))

    SuccessfulSite.inspect_before_publish = inspect_before_publish

    assert worker.process_chain("stream-2-0", {"job_id": str(job_id)}) is True
    assert observed == [("PROCESSING", 1, "راهنمای عینک")]


def test_process_chain_records_failure_result_and_acks_after_terminal_status(test_db, monkeypatch):
    tenant_id, job_id = _create_durable_job(test_db, platform="bale", chat_id=2002)
    statuses_seen_at_ack = []
    broker = FakeBroker(on_ack=lambda *_args: statuses_seen_at_ack.append(test_db.get_article_job(job_id)["status"]))
    builder = FakeArticleBuilder()
    sent = MagicMock(return_value=True)
    _install_worker_dependencies(monkeypatch, broker, builder, FailingSite)
    monkeypatch.setattr(worker, "send_platform_message", sent)

    completed = worker.process_chain("stream-3-0", {"job_id": str(job_id)})

    assert completed is False
    assert broker.acks == [(worker.GROUP, "stream-3-0")]
    assert statuses_seen_at_ack == ["FAILED"]
    # Failed publishing retains the temporary record until its expiry, while
    # the authoritative structured output is in PostgreSQL.
    broker.redis.delete.assert_not_called()
    durable_job = test_db.get_article_job(job_id, tenant_id=tenant_id)
    assert durable_job["status"] == "FAILED"
    assert "کلید امنیتی نامعتبر" in durable_job["error_message"]
    assert durable_job["attempts"][0]["status"] == "FAILED"
    assert durable_job["results"][0]["title"] == "راهنمای عینک"
    assert sent.call_args.args[:2] == ("bale", "2002")
    assert "کلید امنیتی نامعتبر" in sent.call_args.args[2]


def test_process_chain_never_uses_global_site_when_durable_tenant_is_unconnected(test_db, monkeypatch):
    _tenant_id, job_id = _create_durable_job(test_db, with_connection=False)
    broker = FakeBroker()
    builder = FakeArticleBuilder()
    sent = MagicMock(return_value=True)
    _install_worker_dependencies(monkeypatch, broker, builder, SuccessfulSite)
    monkeypatch.setattr(worker, "send_platform_message", sent)

    completed = worker.process_chain("stream-4-0", {"job_id": str(job_id), "platform": "telegram", "chat_id": "other"})

    assert completed is False
    assert SuccessfulSite.instances == []
    assert broker.acks == [(worker.GROUP, "stream-4-0")]
    assert test_db.get_article_job(job_id)["status"] == "FAILED"
    assert "یک خطای غیرمنتظره" in sent.call_args.args[2]


def test_post_created_before_success_write_is_never_downgraded_to_retryable_failure(test_db, monkeypatch):
    _tenant_id, job_id = _create_durable_job(test_db)
    broker = FakeBroker()
    _install_worker_dependencies(monkeypatch, broker, FakeArticleBuilder(), SuccessfulSite)
    sent = MagicMock(return_value=True)
    monkeypatch.setattr(worker, "send_platform_message", sent)

    # Simulate a transient/ambiguous failure after WordPress has returned a
    # post ID but before the first durable SUCCESS write is accepted.  The
    # worker retries only that persistence write; it must not create a second
    # WordPress post or mark the job FAILED.
    real_mark_success = worker.mark_article_job_success
    calls = []

    def flaky_mark_success(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            return False
        return real_mark_success(*args, **kwargs)

    monkeypatch.setattr(worker, "mark_article_job_success", flaky_mark_success)

    assert worker.process_chain("stream-post-created-1", {"job_id": str(job_id)}) is True
    assert len(SuccessfulSite.instances) == 1
    assert len(calls) == 2
    assert test_db.get_article_job(job_id)["status"] == "SUCCESS"
    assert broker.acks == [(worker.GROUP, "stream-post-created-1")]
    assert "موفقیت" in sent.call_args.args[2]


def test_temporary_redis_hash_failure_does_not_discard_durable_job(test_db, monkeypatch):
    _tenant_id, job_id = _create_durable_job(test_db)
    broker = FakeBroker()
    broker.redis.hset.side_effect = RuntimeError("Redis hash unavailable")
    builder = FakeArticleBuilder()
    _install_worker_dependencies(monkeypatch, broker, builder, SuccessfulSite)
    monkeypatch.setattr(worker, "send_platform_message", MagicMock(return_value=True))

    assert worker.process_chain("stream-5-0", {"job_id": str(job_id)}) is True
    assert test_db.get_article_job(job_id)["status"] == "SUCCESS"
    assert broker.acks == [(worker.GROUP, "stream-5-0")]


def test_notification_failure_does_not_turn_success_into_publish_retry(test_db, monkeypatch):
    _tenant_id, job_id = _create_durable_job(test_db)
    broker = FakeBroker()
    _install_worker_dependencies(monkeypatch, broker, FakeArticleBuilder(), SuccessfulSite)
    monkeypatch.setattr(worker, "send_platform_message", MagicMock(side_effect=RuntimeError("bot API unavailable")))

    assert worker.process_chain("stream-6-0", {"job_id": str(job_id)}) is True
    assert test_db.get_article_job(job_id)["status"] == "SUCCESS"
    assert broker.acks == [(worker.GROUP, "stream-6-0")]


def test_worker_startup_recovers_only_unclaimed_durable_jobs(test_db, monkeypatch):
    tenant_id = test_db.get_or_create_tenant("telegram", 800)
    pending_job = test_db.create_article_job(tenant_id, keywords="باید دوباره در صف قرار بگیرد")
    failed_job = test_db.create_article_job(tenant_id, keywords="شکست خورده")
    test_db.mark_article_job_failed(failed_job, "queue failed")
    processing_job = test_db.create_article_job(tenant_id, keywords="در حال پردازش")
    test_db.claim_pending_article_job(processing_job)

    broker = FakeBroker()
    broker.publish = MagicMock(return_value="recovered-1-0")
    monkeypatch.setattr(worker, "broker", broker)

    worker.recover_pending_article_jobs()

    broker.publish.assert_called_once_with({"job_id": str(pending_job)})
    recovered = test_db.get_article_job(pending_job)
    assert recovered["status"] == "PENDING"
    assert recovered["queue_message_id"] == "recovered-1-0"
    assert test_db.get_article_job(failed_job)["status"] == "FAILED"
    assert test_db.get_article_job(processing_job)["status"] == "PROCESSING"


def test_legacy_message_without_durable_id_is_preserved_not_acked_or_published(monkeypatch):
    broker = FakeBroker()
    builder = FakeArticleBuilder()
    monkeypatch.setattr(worker, "broker", broker)
    monkeypatch.setattr(worker, "article_builder", builder)
    claim = MagicMock()
    monkeypatch.setattr(worker, "claim_pending_article_job", claim)

    completed = worker.process_chain(
        "legacy-stream-1",
        {
            "keywords": "مقالهٔ قدیمی",
            "platform": "telegram",
            "chat_id": "1001",
            "tenant_id": "77",
        },
    )

    assert completed is False
    claim.assert_not_called()
    assert builder.kwargs is None
    assert broker.acks == []
    broker.redis.hset.assert_not_called()


def test_unknown_durable_job_id_is_preserved_for_investigation(test_db, monkeypatch):
    broker = FakeBroker()
    monkeypatch.setattr(worker, "broker", broker)

    completed = worker.process_chain("unknown-stream-1", {"job_id": "999999"})

    assert completed is False
    assert broker.acks == []


def test_duplicate_terminal_message_is_acked_without_second_publish(test_db, monkeypatch):
    tenant_id, job_id = _create_durable_job(test_db)
    claim = test_db.claim_pending_article_job(job_id)
    test_db.mark_article_job_failed(job_id, "already recorded", attempt_id=claim.job["attempt_id"])

    broker = FakeBroker()
    builder = FakeArticleBuilder()
    monkeypatch.setattr(worker, "broker", broker)
    monkeypatch.setattr(worker, "article_builder", builder)

    assert worker.process_chain("duplicate-stream-1", {"job_id": str(job_id)}) is False
    assert test_db.get_article_job(job_id, tenant_id=tenant_id)["status"] == "FAILED"
    assert builder.kwargs is None
    assert broker.acks == [(worker.GROUP, "duplicate-stream-1")]


def test_invalid_job_numbers_use_durable_safe_defaults(test_db, monkeypatch):
    _tenant_id, job_id = _create_durable_job(test_db, chapters="not-a-number", max_words="0")
    broker = FakeBroker()
    builder = FakeArticleBuilder()
    _install_worker_dependencies(monkeypatch, broker, builder, SuccessfulSite)
    monkeypatch.setattr(worker, "send_platform_message", MagicMock(return_value=True))

    assert worker.process_chain("stream-7-0", {"job_id": str(job_id)}) is True
    assert builder.kwargs["num_chapters"] == 5
    assert builder.kwargs["max_tokens"] == 3750
