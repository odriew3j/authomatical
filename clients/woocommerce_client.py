import requests, time
from config import Config
from utils.helpers import log

class WooCommerceClient:
    def __init__(self):
        self.auth = (Config.WC_CONSUMER_KEY, Config.WC_CONSUMER_SECRET)
        self.url = f"{Config.WORDPRESS_URL}/wp-json/wc/v3"

    def create_product(self, data: dict):
        for attempt in range(Config.MAX_RETRIES):
            try:
                res = requests.post(
                    f"{self.url}/products",
                    auth=self.auth,
                    json=data,
                    timeout=Config.TIMEOUT
                )

                if res.status_code in (200, 201):
                    return res.json()
                else:
                    log(
                        f"[Retry {attempt+1}] "
                        f"Create product failed: status={res.status_code}, "
                        f"reason={res.reason}, "
                        f"response={res.text}, "
                        f"sent_data={data}"
                    )
            except requests.exceptions.RequestException as e:
                log(f"[Retry {attempt+1}] WooCommerce request error: {e}")
            time.sleep(2)

        raise Exception("Failed to create product.")


    def update_product(self, product_id, data: dict):
        for attempt in range(Config.MAX_RETRIES):
            try:
                res = requests.put(f"{self.url}/products/{product_id}", auth=self.auth, json=data, timeout=Config.TIMEOUT)
                if res.status_code == 200:
                    return res.json()
                else:
                    log(f"[Retry {attempt+1}] WooCommerce update product error: {res.text}")
            except requests.exceptions.RequestException as e:
                log(f"[Retry {attempt+1}] WooCommerce request error: {e}")
            time.sleep(2)
        raise Exception("Failed to update product.")
    
    def get_or_create_category(self, name):
        res = requests.get(f"{self.url}/products/categories", auth=self.auth, params={"search": name})
        if res.status_code == 200 and res.json():
            return res.json()[0]["id"]
        res = requests.post(f"{self.url}/products/categories", auth=self.auth, json={"name": name})
        if res.status_code in (200, 201):
            return res.json()["id"]
        raise Exception(f"Failed to get/create category {name}")

    def get_or_create_tag(self, name):
        res = requests.get(f"{self.url}/products/tags", auth=self.auth, params={"search": name})
        if res.status_code == 200 and res.json():
            return res.json()[0]["id"]
        res = requests.post(f"{self.url}/products/tags", auth=self.auth, json={"name": name})
        if res.status_code in (200, 201):
            return res.json()["id"]
        raise Exception(f"Failed to get/create tag {name}")


    def upload_product_media(self, product_id, image_bytes, filename="image.jpg"):
        files = {"file": (filename, image_bytes, "image/jpeg")}
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

        for attempt in range(Config.MAX_RETRIES):
            try:
                res = requests.post(
                    f"{Config.WORDPRESS_URL}/wp-json/wp/v2/media",
                    auth=self.auth,
                    files=files,
                    headers=headers,
                    data={"post": product_id},   # attach media
                    timeout=Config.TIMEOUT
                )
                if res.status_code == 201:
                    return res.json()["id"]
                else:
                    log(f"[Retry {attempt+1}] WooCommerce media upload error: {res.text}")
            except requests.exceptions.RequestException as e:
                log(f"[Retry {attempt+1}] WooCommerce media request error: {e}")
            time.sleep(2)
        log("Failed to upload media.")
        return None
