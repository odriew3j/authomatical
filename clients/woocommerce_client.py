import requests, time, os
from requests.auth import HTTPBasicAuth
from config import Config
from utils.helpers import log


class WooCommerceClient:
    def __init__(self):
        self.base_url = f"{Config.WORDPRESS_URL}/wp-json/wc/v3"
        self.media_url = f"{Config.WORDPRESS_URL}/wp-json/wp/v2/media"
        self.auth = HTTPBasicAuth(Config.WC_CONSUMER_KEY, Config.WC_CONSUMER_SECRET)
        self.headers = {"User-Agent": "Mozilla/5.0"}

    def _request(self, method, endpoint, **kwargs):
        """Unified request handler with retry & logging"""
        url = f"{self.base_url}{endpoint}"
        for attempt in range(Config.MAX_RETRIES):
            try:
                res = requests.request(
                    method,
                    url,
                    auth=self.auth,
                    headers=self.headers,
                    timeout=Config.TIMEOUT,
                    **kwargs
                )

                if res.status_code in (200, 201):
                    return res.json()

                log(
                    f"[Retry {attempt+1}] {method.upper()} {url} failed | "
                    f"Status={res.status_code}, Reason={res.reason}, Response={res.text}"
                )

            except requests.exceptions.RequestException as e:
                log(f"[Retry {attempt+1}] Request error on {method.upper()} {url}: {e}")

            time.sleep(2)

        raise Exception(f"Failed after {Config.MAX_RETRIES} retries: {method.upper()} {url}")

    # ---- Product Methods ----
    def create_product(self, data: dict):
        return self._request("post", "/products", json=data)

    def update_product(self, product_id, data: dict):
        return self._request("put", f"/products/{product_id}", json=data)

    # ---- Category Methods ----
    def get_or_create_category(self, name):
        res = self._request("get", "/products/categories", params={"search": name})
        if res:
            return res[0]["id"]

        res = self._request("post", "/products/categories", json={"name": name})
        return res["id"]

    # ---- Tag Methods ----
    def get_or_create_tag(self, name):
        res = self._request("get", "/products/tags", params={"search": name})
        if res:
            return res[0]["id"]

        res = self._request("post", "/products/tags", json={"name": name})
        return res["id"]

    # ---- Media Upload ----
    def upload_product_media(self, product_id, image_bytes, filename="image.jpg"):
        headers = {**self.headers, "Content-Disposition": f'attachment; filename="{filename}"'}
        files = {"file": (filename, image_bytes, "image/jpeg")}
        data = {"post": product_id}

        for attempt in range(Config.MAX_RETRIES):
            try:
                res = requests.post(
                    self.media_url,
                    auth=self.auth,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=Config.TIMEOUT,
                )
                if res.status_code == 201:
                    return res.json()["id"]

                log(f"[Retry {attempt+1}] Media upload error: {res.status_code} | {res.text}")
            except requests.exceptions.RequestException as e:
                log(f"[Retry {attempt+1}] Media upload request error: {e}")
            time.sleep(2)

        log("❌ Failed to upload media after retries.")
        return None
