import time
from unittest.mock import MagicMock

import pytest

from clients.site_connector_client import SiteConnectorError
from config import Config
from services import connect_security
from services.blueprints import connect as connect_module
from services.connect_app import app as connect_app


TOKEN = "A" * 43
SITE_URL = "https://shop.example.com"
SECRET = "wordpress-shared-secret"
ISSUED_AT = int(time.time())


@pytest.fixture
def client():
    connect_app.testing = True
    return connect_app.test_client()


def _headers(
    platform="telegram",
    site_url=SITE_URL,
    token=TOKEN,
    secret=SECRET,
    issued_at=ISSUED_AT,
):
    return {
        "X-ODVIEW-CONNECT-PROOF": connect_security.connect_proof(
            secret, platform, site_url, token, issued_at,
        ),
    }


def _valid_body(
    platform="telegram",
    site_url=SITE_URL,
    token=TOKEN,
    secret=SECRET,
    issued_at=ISSUED_AT,
):
    return {
        "token": token,
        "platform": platform,
        "site_url": site_url,
        "secret": secret,
        "issued_at": issued_at,
    }


def test_dedicated_connect_app_exposes_only_pairing_surface(client):
    assert client.get("/").status_code == 404
    assert client.get("/healthz").get_json() == {"status": "ok"}


def test_register_proves_site_then_returns_only_platform_bound_link_and_local_qr(client, monkeypatch):
    captured = {}

    class VerifiedSite:
        def __init__(self, site_url, secret, **kwargs):
            captured["client"] = (site_url, secret, kwargs)

        def ping(self):
            return {"success": True, "site_url": SITE_URL, "site_name": "Store"}

    def create_pending(**kwargs):
        captured["pending"] = kwargs

    monkeypatch.setattr(connect_module, "init_db", lambda: None)
    monkeypatch.setattr(connect_module, "assert_site_host_is_public", lambda site_url: captured.setdefault("resolved", site_url))
    monkeypatch.setattr(connect_module, "SiteConnectorClient", VerifiedSite)
    monkeypatch.setattr(connect_module, "create_pending_connection", create_pending)
    monkeypatch.setattr(Config, "TELEGRAM_BOT_USERNAME", "ExampleConnectBot")
    monkeypatch.setattr(Config, "BALE_BOT_USERNAME", None)
    monkeypatch.setattr(Config, "CONNECT_TOKEN_TTL_SECONDS", 600)
    monkeypatch.setattr(Config, "CONNECT_VERIFICATION_TIMEOUT_SECONDS", 13)

    response = client.post(
        "/api/connect/register",
        json=_valid_body(),
        headers=_headers(),
        base_url="https://connect.example.com",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["platform"] == "telegram"
    assert body["deep_links"] == {
        "telegram": "https://t.me/ExampleConnectBot?start=connect_" + TOKEN,
    }
    assert body["qr_paths"] == {
        "telegram": "/api/connect/qr/" + TOKEN + ".svg?platform=telegram",
    }
    assert SECRET not in response.get_data(as_text=True)
    assert response.headers["Cache-Control"].startswith("no-store")
    assert response.headers["Referrer-Policy"] == "no-referrer"

    assert captured["resolved"] == SITE_URL
    assert captured["client"] == (SITE_URL, SECRET, {"timeout": 13, "allow_redirects": False})
    assert captured["pending"] == {
        "token": TOKEN,
        "platform": "telegram",
        "site_url": SITE_URL,
        "secret": SECRET,
        "ttl_seconds": 600,
    }


def test_register_real_repository_record_is_encrypted_and_platform_bound(client, test_db, monkeypatch):
    class VerifiedSite:
        def __init__(self, *_args, **_kwargs):
            pass

        def ping(self):
            return {"success": True, "site_url": SITE_URL}

    monkeypatch.setattr(connect_module, "assert_site_host_is_public", lambda _url: None)
    monkeypatch.setattr(connect_module, "SiteConnectorClient", VerifiedSite)
    monkeypatch.setattr(Config, "TELEGRAM_BOT_USERNAME", "ExampleConnectBot")

    response = client.post("/api/connect/register", json=_valid_body(), headers=_headers())

    assert response.status_code == 200
    # Different platform = no credential release and no consumption.
    assert test_db.consume_pending_connection(TOKEN, "bale") is None
    assert test_db.consume_pending_connection(TOKEN, "telegram") == {
        "site_url": SITE_URL,
        "secret": SECRET,
    }


def test_register_rejects_payload_override_and_bad_proof_before_site_or_database_use(client, monkeypatch):
    site = MagicMock()
    create = MagicMock()
    monkeypatch.setattr(connect_module, "SiteConnectorClient", site)
    monkeypatch.setattr(connect_module, "create_pending_connection", create)

    body = _valid_body()
    body["payload"] = "connect_attacker-controlled-value"
    response = client.post("/api/connect/register", json=body, headers=_headers())

    assert response.status_code == 400
    assert "SECRET" not in response.get_data(as_text=True)
    site.assert_not_called()
    create.assert_not_called()

    response = client.post("/api/connect/register", json=_valid_body())
    assert response.status_code == 403
    site.assert_not_called()
    create.assert_not_called()


def test_register_rejects_an_expired_signed_request_before_site_or_database_use(client, monkeypatch):
    site = MagicMock()
    create = MagicMock()
    old_issued_at = ISSUED_AT - 301
    monkeypatch.setattr(connect_module, "SiteConnectorClient", site)
    monkeypatch.setattr(connect_module, "create_pending_connection", create)
    monkeypatch.setattr(Config, "CONNECT_REGISTRATION_PROOF_MAX_AGE_SECONDS", 300)

    response = client.post(
        "/api/connect/register",
        json=_valid_body(issued_at=old_issued_at),
        headers=_headers(issued_at=old_issued_at),
    )

    assert response.status_code == 400
    site.assert_not_called()
    create.assert_not_called()


def test_register_rejects_unsafe_site_and_unverified_plugin_without_persisting(client, monkeypatch):
    create = MagicMock()
    monkeypatch.setattr(connect_module, "create_pending_connection", create)
    monkeypatch.setattr(Config, "TELEGRAM_BOT_USERNAME", "ExampleConnectBot")

    unsafe_url = "https://127.0.0.1"
    response = client.post(
        "/api/connect/register",
        json=_valid_body(site_url=unsafe_url),
        headers=_headers(site_url=unsafe_url),
    )
    assert response.status_code == 400
    create.assert_not_called()

    class RejectingSite:
        def __init__(self, *_args, **_kwargs):
            pass

        def ping(self):
            raise SiteConnectorError("invalid secret")

    monkeypatch.setattr(connect_module, "assert_site_host_is_public", lambda _url: None)
    monkeypatch.setattr(connect_module, "SiteConnectorClient", RejectingSite)
    response = client.post("/api/connect/register", json=_valid_body(), headers=_headers())

    assert response.status_code == 422
    assert SECRET not in response.get_data(as_text=True)
    create.assert_not_called()


def test_register_requires_authenticated_ping_to_report_the_same_site(client, monkeypatch):
    create = MagicMock()

    class DifferentSite:
        def __init__(self, *_args, **_kwargs):
            pass

        def ping(self):
            return {"success": True, "site_url": "https://other.example.com"}

    monkeypatch.setattr(connect_module, "assert_site_host_is_public", lambda _url: None)
    monkeypatch.setattr(connect_module, "SiteConnectorClient", DifferentSite)
    monkeypatch.setattr(connect_module, "create_pending_connection", create)
    monkeypatch.setattr(Config, "TELEGRAM_BOT_USERNAME", "ExampleConnectBot")

    response = client.post("/api/connect/register", json=_valid_body(), headers=_headers())

    assert response.status_code == 422
    create.assert_not_called()


def test_register_builds_a_distinct_bale_deep_link_for_the_selected_platform(client, monkeypatch):
    token = "B" * 43
    create = MagicMock()
    monkeypatch.setattr(connect_module, "_plugin_proves_site_control", lambda *_args: True)
    monkeypatch.setattr(connect_module, "init_db", lambda: None)
    monkeypatch.setattr(connect_module, "create_pending_connection", create)
    monkeypatch.setattr(Config, "BALE_BOT_USERNAME", "ExampleBaleBot")

    response = client.post(
        "/api/connect/register",
        json=_valid_body(platform="bale", token=token),
        headers=_headers(platform="bale", token=token),
    )

    assert response.status_code == 200
    assert response.get_json()["deep_links"] == {
        "bale": "https://ble.ir/ExampleBaleBot?start=connect_" + token,
    }
    assert create.call_args.kwargs["platform"] == "bale"


def test_register_does_not_create_a_link_for_an_unconfigured_platform(client, monkeypatch):
    proof_site = MagicMock()
    monkeypatch.setattr(connect_module, "SiteConnectorClient", proof_site)
    monkeypatch.setattr(Config, "BALE_BOT_USERNAME", None)

    token = "B" * 43
    response = client.post(
        "/api/connect/register",
        json=_valid_body(platform="bale", token=token),
        headers=_headers(platform="bale", token=token),
    )

    assert response.status_code == 503
    proof_site.assert_not_called()


def test_qr_is_generated_locally_only_for_an_active_matching_platform_token(client, monkeypatch):
    available = MagicMock(return_value=True)
    monkeypatch.setattr(connect_module, "init_db", lambda: None)
    monkeypatch.setattr(connect_module, "pending_connection_is_available", available)
    monkeypatch.setattr(Config, "TELEGRAM_BOT_USERNAME", "ExampleConnectBot")

    response = client.get(f"/api/connect/qr/{TOKEN}.svg?platform=telegram")

    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"
    assert response.headers["Cache-Control"].startswith("no-store")
    assert response.headers["Referrer-Policy"] == "no-referrer"
    svg = response.get_data(as_text=True)
    assert "<svg" in svg
    # SvgPathImage encodes QR modules, not an external URL/data URI or a raw
    # token that another service could trivially consume.
    assert TOKEN not in svg
    assert "t.me" not in svg
    available.assert_called_once_with(TOKEN, "telegram")

    available.reset_mock()
    response = client.get(f"/api/connect/qr/{TOKEN}.svg?platform=not-a-bot")
    assert response.status_code == 404
    available.assert_not_called()
