import json
from unittest.mock import MagicMock

import pytest

import services.web_app as web_app_module
import services.blueprints.product as product_module
import services.blueprints.article as article_module
from clients.site_connector_client import SiteConnectorError


@pytest.fixture
def client():
    web_app_module.app.testing = True
    return web_app_module.app.test_client()


# -------------------- /api/tenants --------------------

def test_list_tenants_returns_repository_data(client, monkeypatch):
    monkeypatch.setattr(web_app_module, "init_db", lambda: None)
    monkeypatch.setattr(
        web_app_module,
        "list_connected_tenants",
        lambda: [{"tenant_id": 1, "platform": "bale", "chat_id": "42", "display_name": None, "site_url": "https://shop.example"}],
    )

    resp = client.get("/api/tenants")

    assert resp.status_code == 200
    assert resp.get_json()[0]["site_url"] == "https://shop.example"


def test_article_dashboard_reads_durable_history_not_redis(client, monkeypatch):
    monkeypatch.setattr(web_app_module, "init_db", lambda: None)
    monkeypatch.setattr(
        web_app_module,
        "list_article_jobs",
        lambda limit: [{
            "id": 71,
            "tenant_id": 7,
            "keywords": "موضوع پایدار",
            "article_type": "آموزشی",
            "notes": "نکته",
            "status": "SUCCESS",
            "requested_at": "2026-09-01T10:00:00",
            "completed_at": "2026-09-01T10:01:00",
        }],
    )
    redis = MagicMock()
    monkeypatch.setattr(web_app_module.article_broker, "redis", redis)

    resp = client.get("/api/jobs/article")

    assert resp.status_code == 200
    assert resp.get_json() == [{
        "id": "71",
        "tenant_id": 7,
        "status": "SUCCESS",
        "requested_at": "2026-09-01T10:00:00",
        "completed_at": "2026-09-01T10:01:00",
        "data": {"keywords": "موضوع پایدار", "article_type": "آموزشی", "notes": "نکته"},
    }]
    redis.xrevrange.assert_not_called()


def test_article_dashboard_never_deletes_or_requeues_legacy_redis_entries(client, monkeypatch):
    redis = MagicMock()
    monkeypatch.setattr(web_app_module.article_broker, "redis", redis)

    delete_response = client.post("/api/jobs/article/delete/legacy-1")
    requeue_response = client.post("/api/jobs/article/requeue/legacy-1")

    assert delete_response.status_code == 409
    assert requeue_response.status_code == 409
    redis.xdel.assert_not_called()
    redis.xrange.assert_not_called()


# -------------------- /products/publish_product --------------------

def test_publish_product_requires_tenant_id(client):
    resp = client.post("/products/publish_product", json={"title": "محصول"})
    assert resp.status_code == 400
    assert "tenant_id" in resp.get_json()["message"]


def test_publish_product_requires_title(client):
    resp = client.post("/products/publish_product", json={"tenant_id": 1})
    assert resp.status_code == 400
    assert "عنوان" in resp.get_json()["message"]


def test_publish_product_rejects_unconnected_tenant(client, monkeypatch):
    monkeypatch.setattr(product_module, "get_wp_connection", lambda tenant_id: None)

    resp = client.post("/products/publish_product", json={"tenant_id": 5, "title": "محصول"})

    assert resp.status_code == 400
    assert "وصل نکرده" in resp.get_json()["message"]


def test_publish_product_creates_synchronously_with_grounding_fields(client, monkeypatch):
    """Regression guard: this used to publish a job onto product_jobs for a
    worker that no longer exists (workers/product_worker.py is deprecated).
    It must now call the site directly and never touch that dead queue."""
    monkeypatch.setattr(
        product_module, "get_wp_connection",
        lambda tenant_id: {"site_url": "https://tenant.example", "secret": "s3cr3t"},
    )

    captured_builder_kwargs = {}

    class FakeBuilder:
        def generate_full_product(self, **kwargs):
            captured_builder_kwargs.update(kwargs)
            return {
                "description": "<p>توضیح</p>",
                "slug": "eyewear-medical-frame-abc123",
                "brand": "TestBrand",
                "hashtags": "#a,#b",
                "seo": {"title": "seo", "description": "seo-desc", "keywords": "k1,k2"},
            }

    monkeypatch.setattr(product_module, "_get_builder", lambda: FakeBuilder())

    captured_site_payload = {}

    class FakeSite:
        def __init__(self, site_url, secret):
            assert site_url == "https://tenant.example"
            assert secret == "s3cr3t"

        def create_product(self, payload):
            captured_site_payload.update(payload)
            return {"success": True, "product_id": 99, "url": "https://tenant.example/p/99"}

    monkeypatch.setattr(product_module, "SiteConnectorClient", FakeSite)

    resp = client.post("/products/publish_product", json={
        "tenant_id": 7,
        "title": "عینک طبی فریم فلزی",
        "product_type": "عینک طبی",
        "user_notes": "فریم تیتانیوم",
        "price": 100000,
        "category": "medical-lens",
    })

    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"status": "created", "product_id": 99, "url": "https://tenant.example/p/99"}

    assert captured_builder_kwargs["product_type"] == "عینک طبی"
    assert captured_builder_kwargs["user_notes"] == "فریم تیتانیوم"
    assert captured_site_payload["slug"] == "eyewear-medical-frame-abc123"
    assert captured_site_payload["category"] == "medical-lens"


def test_publish_product_surfaces_ai_failure_as_502(client, monkeypatch):
    monkeypatch.setattr(
        product_module, "get_wp_connection",
        lambda tenant_id: {"site_url": "https://tenant.example", "secret": "s3cr3t"},
    )

    class FailingBuilder:
        def generate_full_product(self, **kwargs):
            raise RuntimeError("9Router API error 401: invalid key")

    monkeypatch.setattr(product_module, "_get_builder", lambda: FailingBuilder())

    resp = client.post("/products/publish_product", json={"tenant_id": 1, "title": "x"})

    assert resp.status_code == 502
    assert "هوش مصنوعی" in resp.get_json()["message"]


def test_publish_product_surfaces_site_rejection_as_502(client, monkeypatch):
    monkeypatch.setattr(
        product_module, "get_wp_connection",
        lambda tenant_id: {"site_url": "https://tenant.example", "secret": "s3cr3t"},
    )
    monkeypatch.setattr(
        product_module, "_get_builder",
        lambda: MagicMock(generate_full_product=lambda **k: {
            "description": "d", "slug": "x-1", "brand": "b", "hashtags": "",
            "seo": {"title": "t", "description": "d", "keywords": ""},
        }),
    )

    class RejectingSite:
        def __init__(self, *a):
            pass

        def create_product(self, payload):
            raise SiteConnectorError("کلید امنیتی نامعتبر است")

    monkeypatch.setattr(product_module, "SiteConnectorClient", RejectingSite)

    resp = client.post("/products/publish_product", json={"tenant_id": 1, "title": "x"})

    assert resp.status_code == 502
    assert "کلید امنیتی" in resp.get_json()["message"]


def test_tenant_categories_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        product_module, "get_wp_connection",
        lambda tenant_id: {"site_url": "https://tenant.example", "secret": "s3cr3t"},
    )

    class FakeSite:
        def __init__(self, *a):
            pass

        def get_categories(self):
            return [{"id": 1, "name": "دسته", "slug": "cat"}]

    monkeypatch.setattr(product_module, "SiteConnectorClient", FakeSite)

    resp = client.get("/products/api/tenants/1/categories")

    assert resp.status_code == 200
    assert resp.get_json() == [{"id": 1, "name": "دسته", "slug": "cat"}]


# -------------------- /articles/publish_article --------------------

def test_publish_article_requires_tenant_id_and_keywords(client):
    resp = client.post("/articles/publish_article", json={"keywords": "test"})
    assert resp.status_code == 400
    assert "tenant_id" in resp.get_json()["message"]

    resp = client.post("/articles/publish_article", json={"tenant_id": 1})
    assert resp.status_code == 400
    assert "مقاله" in resp.get_json()["message"]


def test_publish_article_rejects_unconnected_tenant(client, monkeypatch):
    monkeypatch.setattr(article_module, "get_wp_connection", lambda tenant_id: None)

    resp = client.post("/articles/publish_article", json={"tenant_id": 3, "keywords": "موضوع"})

    assert resp.status_code == 400
    assert "وصل نکرده" in resp.get_json()["message"]


def test_publish_article_persists_then_queues_only_durable_job_id(client, monkeypatch):
    monkeypatch.setattr(
        article_module,
        "get_wp_connection",
        lambda tenant_id: {"site_url": "https://tenant.example", "secret": "s3cr3t"},
    )
    fake_broker = MagicMock()
    events = []

    def publish(payload):
        events.append(("publish", payload))
        return "1710000000000-0"

    fake_broker.publish.side_effect = publish

    def create_job(tenant_id, **kwargs):
        events.append(("create", tenant_id, kwargs))
        return 91

    def mark_queued(job_id, queue_message_id):
        events.append(("queued", job_id, queue_message_id))
        return True

    monkeypatch.setattr(article_module, "create_article_job", create_job)
    monkeypatch.setattr(article_module, "mark_article_job_queued", mark_queued)
    monkeypatch.setattr(article_module, "broker", fake_broker)

    resp = client.post("/articles/publish_article", json={
        "tenant_id": 9,
        "keywords": "راهنمای انتخاب عینک",
        "article_type": "راهنمای خرید",
        "notes": "برای کاربران تازه‌کار",
    })

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "queued", "job_id": 91}
    assert events[0] == ("create", 9, {
        "keywords": "راهنمای انتخاب عینک",
        "article_type": "راهنمای خرید",
        "notes": "برای کاربران تازه‌کار",
        "chapters": 5,
        "max_words": 500,
        "tone": "informative",
        "audience": "general",
        "featured_image_url": None,
        "source": "web",
    })
    fake_broker.publish.assert_called_once_with({"job_id": "91"})
    assert events[1] == ("publish", {"job_id": "91"})
    assert events[2] == ("queued", 91, "1710000000000-0")


def test_publish_article_real_repository_path_creates_durable_job(test_db, client, monkeypatch):
    tenant_id = test_db.get_or_create_tenant("telegram", 901)
    test_db.save_wp_connection(tenant_id, "https://tenant.example", "tenant-secret")
    fake_broker = MagicMock()
    fake_broker.publish.return_value = "real-route-1-0"
    monkeypatch.setattr(article_module, "broker", fake_broker)

    response = client.post("/articles/publish_article", json={
        "tenant_id": tenant_id,
        "keywords": "راهنمای واقعی",
        "article_type": "آموزشی",
        "notes": "نتیجه باید پایدار بماند",
    })

    assert response.status_code == 200
    job_id = response.get_json()["job_id"]
    assert fake_broker.publish.call_args.args[0] == {"job_id": str(job_id)}
    job = test_db.get_article_job(job_id, tenant_id=tenant_id)
    assert job["status"] == "PENDING"
    assert job["queue_message_id"] == "real-route-1-0"
    assert job["keywords"] == "راهنمای واقعی"
    assert job["platform"] == "telegram"
    assert job["chat_id"] == "901"


def test_publish_article_accepts_featured_image_url(client, monkeypatch):
    monkeypatch.setattr(
        article_module,
        "get_wp_connection",
        lambda tenant_id: {"site_url": "https://tenant.example", "secret": "s3cr3t"},
    )
    events = []

    def create_job(tenant_id, **kwargs):
        events.append(kwargs)
        return 92

    monkeypatch.setattr(article_module, "create_article_job", create_job)
    monkeypatch.setattr(article_module, "mark_article_job_queued", lambda *_a: True)
    monkeypatch.setattr(article_module, "broker", MagicMock(publish=MagicMock(return_value="1-0")))

    resp = client.post("/articles/publish_article", json={
        "tenant_id": 9,
        "keywords": "راهنمای انتخاب عینک",
        "featured_image_url": "https://tenant.example/wp-content/uploads/cover.jpg",
    })

    assert resp.status_code == 200
    assert events[0]["featured_image_url"] == "https://tenant.example/wp-content/uploads/cover.jpg"


def test_publish_article_rejects_non_url_featured_image(client, monkeypatch):
    monkeypatch.setattr(
        article_module,
        "get_wp_connection",
        lambda tenant_id: {"site_url": "https://tenant.example", "secret": "s3cr3t"},
    )

    resp = client.post("/articles/publish_article", json={
        "tenant_id": 9,
        "keywords": "راهنمای انتخاب عینک",
        "featured_image_url": "not-a-url",
    })

    assert resp.status_code == 400
    assert "URL" in resp.get_json()["message"]


def test_publish_article_records_redis_failure_in_durable_job(client, monkeypatch):
    monkeypatch.setattr(
        article_module,
        "get_wp_connection",
        lambda tenant_id: {"site_url": "https://tenant.example", "secret": "s3cr3t"},
    )
    fake_broker = MagicMock()
    fake_broker.publish.side_effect = RuntimeError("Redis is unavailable: down")
    failed = MagicMock(return_value=True)
    monkeypatch.setattr(article_module, "create_article_job", lambda *_args, **_kwargs: 92)
    monkeypatch.setattr(article_module, "mark_article_job_failed", failed)
    monkeypatch.setattr(article_module, "broker", fake_broker)

    resp = client.post("/articles/publish_article", json={"tenant_id": 1, "keywords": "موضوع"})

    assert resp.status_code == 503
    assert resp.get_json()["job_id"] == 92
    assert "Redis" in resp.get_json()["message"]
    fake_broker.publish.assert_called_once_with({"job_id": "92"})
    failed.assert_called_once()
    assert failed.call_args.args[0] == 92
    assert "Redis queue publish failed" in failed.call_args.args[1]


def test_publish_article_does_not_queue_when_durable_creation_fails(client, monkeypatch):
    monkeypatch.setattr(
        article_module,
        "get_wp_connection",
        lambda tenant_id: {"site_url": "https://tenant.example", "secret": "s3cr3t"},
    )
    fake_broker = MagicMock()
    monkeypatch.setattr(article_module, "create_article_job", MagicMock(side_effect=RuntimeError("database down")))
    monkeypatch.setattr(article_module, "broker", fake_broker)

    resp = client.post("/articles/publish_article", json={"tenant_id": 1, "keywords": "موضوع"})

    assert resp.status_code == 503
    assert "دیتابیس" in resp.get_json()["message"]
    fake_broker.publish.assert_not_called()
