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

    resp = client.post("/articles/publish_article", json={"tenant_id": 1})
    assert resp.status_code == 400


def test_publish_article_rejects_unconnected_tenant(client, monkeypatch):
    monkeypatch.setattr(article_module, "get_wp_connection", lambda tenant_id: None)

    resp = client.post("/articles/publish_article", json={"tenant_id": 3, "keywords": "موضوع"})

    assert resp.status_code == 400
    assert "وصل نکرده" in resp.get_json()["message"]


def test_publish_article_queues_job_with_tenant_id_and_grounding_fields(client, monkeypatch):
    monkeypatch.setattr(
        article_module, "get_wp_connection",
        lambda tenant_id: {"site_url": "https://tenant.example", "secret": "s3cr3t"},
    )
    fake_broker = MagicMock()
    fake_broker.publish.return_value = b"1-0"
    monkeypatch.setattr(article_module, "broker", fake_broker)

    resp = client.post("/articles/publish_article", json={
        "tenant_id": 9,
        "keywords": "راهنمای انتخاب عینک",
        "article_type": "راهنمای خرید",
        "notes": "برای کاربران تازه‌کار",
    })

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "queued"
    assert body["job_id"] == "1-0"

    queued = fake_broker.publish.call_args.args[0]
    assert queued["tenant_id"] == "9"
    assert queued["article_type"] == "راهنمای خرید"
    assert queued["notes"] == "برای کاربران تازه‌کار"


def test_publish_article_explains_redis_failure(client, monkeypatch):
    monkeypatch.setattr(
        article_module, "get_wp_connection",
        lambda tenant_id: {"site_url": "https://tenant.example", "secret": "s3cr3t"},
    )
    fake_broker = MagicMock()
    fake_broker.publish.side_effect = RuntimeError("Redis is unavailable: down")
    monkeypatch.setattr(article_module, "broker", fake_broker)

    resp = client.post("/articles/publish_article", json={"tenant_id": 1, "keywords": "موضوع"})

    assert resp.status_code == 503
    assert "Redis" in resp.get_json()["message"]