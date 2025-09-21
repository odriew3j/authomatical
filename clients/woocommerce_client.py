import requests, time
from config import Config
from utils.helpers import log

class WooCommerceClient:
    def __init__(self):
        self.auth = (Config.WORDPRESS_USER, Config.WORDPRESS_PASSWORD)
        self.url = Config.WORDPRESS_URL  # The site URL should start with /wp-json/wc/v3/products

    def create_product(self, data: dict):
        """Create a new product in WooCommerce"""
        for attempt in range(Config.MAX_RETRIES):
            try:
                res = requests.post(f"{self.url}/wp-json/wc/v3/products", auth=self.auth, json=data, timeout=Config.TIMEOUT)
                if res.status_code in (200,201):
                    return res.json()
                else:
                    log(f"[Retry {attempt+1}] WooCommerce create product error: {res.text}")
            except requests.exceptions.RequestException as e:
                log(f"[Retry {attempt+1}] WooCommerce request error: {e}")
            time.sleep(2)
        raise Exception("Failed to create product.")

    def update_product(self, product_id, data: dict):
        """Update existing product"""
        for attempt in range(Config.MAX_RETRIES):
            try:
                res = requests.put(f"{self.url}/wp-json/wc/v3/products/{product_id}", auth=self.auth, json=data, timeout=Config.TIMEOUT)
                if res.status_code == 200:
                    return res.json()
                else:
                    log(f"[Retry {attempt+1}] WooCommerce update product error: {res.text}")
            except requests.exceptions.RequestException as e:
                log(f"[Retry {attempt+1}] WooCommerce request error: {e}")
            time.sleep(2)
        raise Exception("Failed to update product.")

    def upload_product_media(self, product_id, image_bytes, filename="image.jpg"):
        """Upload photo for product"""
        files = {"file": (filename, image_bytes, "image/jpeg")}
        for attempt in range(Config.MAX_RETRIES):
            try:
                res = requests.post(f"{self.url}/wp-json/wp/v2/media", auth=self.auth, files=files, timeout=Config.TIMEOUT)
                if res.status_code == 201:
                    media_id = res.json()["id"]
                    # Assign image to product
                    self.update_product(product_id, {"images": [{"id": media_id}]})
                    return media_id
                else:
                    log(f"[Retry {attempt+1}] WooCommerce media upload error: {res.text}")
            except requests.exceptions.RequestException as e:
                log(f"[Retry {attempt+1}] WooCommerce media request error: {e}")
            time.sleep(2)
        log("Failed to upload media.")
        return None
