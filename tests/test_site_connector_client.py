from unittest.mock import MagicMock, patch

import pytest
import requests

from clients.site_connector_client import SiteConnectorClient, SiteConnectorError
from config import Config


def _response(*, ok=True, status=200, body=None, text=""):
    response = MagicMock()
    response.ok = ok
    response.status_code = status
    response.text = text
    response.json.return_value = {"success": True} if body is None else body
    return response


def test_create_post_uses_tenant_site_endpoint_and_payload(monkeypatch):
    monkeypatch.setattr(Config, "TIMEOUT", 21)
    client = SiteConnectorClient("https://merchant.example/", "site-secret")
    payload = {"title": "مقاله", "content": "<p>متن</p>", "status": "publish"}

    with patch(
        "clients.site_connector_client.requests.post",
        return_value=_response(body={"success": True, "post_id": 42, "url": "https://merchant.example/p/42"}),
    ) as post:
        result = client.create_post(payload)

    assert result["post_id"] == 42
    post.assert_called_once_with(
        "https://merchant.example/wp-json/odview/v1/create-post",
        headers={"X-ODVIEW-SECRET": "site-secret", "User-Agent": "Authomatical-Bot"},
        json=payload,
        timeout=21,
    )


def test_site_connector_translates_site_and_network_failures():
    client = SiteConnectorClient("https://merchant.example", "secret")

    with patch(
        "clients.site_connector_client.requests.post",
        return_value=_response(ok=False, status=403, text="forbidden"),
    ):
        with pytest.raises(SiteConnectorError, match="کلید امنیتی"):
            client.create_post({"title": "x", "content": "y"})

    with patch(
        "clients.site_connector_client.requests.post",
        return_value=_response(ok=False, status=500, text="X-ODVIEW-SECRET=site-secret"),
    ):
        with pytest.raises(SiteConnectorError) as error:
            client.create_post({"title": "x", "content": "y"})
    assert "site-secret" not in str(error.value)

    with patch(
        "clients.site_connector_client.requests.post",
        side_effect=requests.ConnectionError("offline"),
    ):
        with pytest.raises(SiteConnectorError, match="انتشار مقاله ناموفق"):
            client.create_post({"title": "x", "content": "y"})
