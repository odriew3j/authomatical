import mimetypes
import os

import requests

from config import Config


class SiteConnectorError(Exception):
    """Raised for any failure talking to a tenant's site (unreachable,
    wrong secret, plugin missing, WooCommerce missing, etc.)."""


class SiteConnectorClient:
    """Talks to one merchant's WordPress/WooCommerce site through the
    'ODview Sync' companion plugin (wp-content/plugins/odview-sync),
    authenticated with that site's own secret (X-ODVIEW-SECRET header).

    Every call is scoped to a single site_url + secret pair — callers
    must construct a fresh instance per tenant from database/repository.py,
    never share one instance across users.
    """

    def __init__(
        self,
        site_url: str,
        secret: str,
        *,
        timeout: int | float | None = None,
        allow_redirects: bool = True,
    ):
        self.base_url = site_url.rstrip("/") + "/wp-json/odview/v1"
        self.headers = {"X-ODVIEW-SECRET": secret, "User-Agent": "Authomatical-Bot"}
        self.timeout = Config.TIMEOUT if timeout is None else timeout
        self.allow_redirects = allow_redirects

    def _handle(self, resp: requests.Response):
        if resp.status_code == 403:
            raise SiteConnectorError("کلید امنیتی نامعتبر است یا سایت اجازهٔ دسترسی نمی‌دهد.")
        if resp.status_code == 404:
            raise SiteConnectorError("افزونهٔ ODview Sync روی این سایت پیدا نشد یا نصب/فعال نیست.")
        if not resp.ok:
            # Do not reflect a remote response body into worker logs or a bot
            # chat. A broken/malicious endpoint could echo the X-ODVIEW-SECRET
            # header in its body; the status code is sufficient for recovery.
            raise SiteConnectorError(f"خطای سایت ({resp.status_code}).")
        try:
            return resp.json()
        except ValueError:
            raise SiteConnectorError("پاسخ سایت قابل خواندن نبود (JSON نامعتبر).")

    def ping(self) -> dict:
        try:
            resp = requests.get(
                f"{self.base_url}/ping",
                headers=self.headers,
                timeout=self.timeout,
                allow_redirects=self.allow_redirects,
            )
        except requests.RequestException as e:
            raise SiteConnectorError(f"اتصال به سایت برقرار نشد: {e}")
        return self._handle(resp)

    def get_categories(self) -> list:
        try:
            resp = requests.get(f"{self.base_url}/categories", headers=self.headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise SiteConnectorError(f"دریافت دسته‌بندی‌ها ناموفق بود: {e}")
        data = self._handle(resp)
        return data if isinstance(data, list) else data.get("categories", [])

    def upload_media(self, file_path: str, mime_type: str = None) -> dict:
        mime_type = mime_type or mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f, mime_type)}
                resp = requests.post(
                    f"{self.base_url}/upload-media",
                    headers=self.headers,
                    files=files,
                    timeout=self.timeout,
                )
        except requests.RequestException as e:
            raise SiteConnectorError(f"آپلود تصویر ناموفق بود: {e}")
        return self._handle(resp)

    def create_product(self, payload: dict) -> dict:
        try:
            resp = requests.post(
                f"{self.base_url}/create-product",
                headers=self.headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise SiteConnectorError(f"ساخت محصول ناموفق بود: {e}")
        return self._handle(resp)

    def create_post(self, payload: dict) -> dict:
        try:
            resp = requests.post(
                f"{self.base_url}/create-post",
                headers=self.headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise SiteConnectorError(f"انتشار مقاله ناموفق بود: {e}")
        return self._handle(resp)