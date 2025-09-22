import requests, time
from config import Config
from utils.helpers import log

class WordPressClient:
    def __init__(self):
        self.auth = (Config.WORDPRESS_USER, Config.WORDPRESS_PASSWORD)

    def create_post(self, title, content, status="draft"):
        post_data = {"title": title, "content": content, "status": status}
        for attempt in range(Config.MAX_RETRIES):
            try:
                res = requests.post(f"{Config.WORDPRESS_URL}/wp-json/wp/v2/posts", auth=self.auth, json=post_data, timeout=Config.TIMEOUT)
                if res.status_code == 201:
                    return res.json()["id"]
                else: log(f"[Retry {attempt+1}] WP post error: status={res.status_code}, body={res.text}")
            except requests.exceptions.RequestException as e:
                log(f"[Retry {attempt+1}] WP request error: {type(e).__name__}: {e}")

            time.sleep(2)
        raise Exception("Failed to create post.")

    def upload_media(self, post_id, image_bytes, filename="featured.jpg"):
        files = {"file": (filename, image_bytes, "image/jpeg")}
        res = requests.post(f"{Config.WORDPRESS_URL}/wp-json/wp/v2/media", auth=self.auth, files=files, timeout=Config.TIMEOUT)
        if res.status_code == 201:
            media_id = res.json()["id"]
            requests.post(f"{Config.WORDPRESS_URL}/wp-json/wp/v2/posts/{post_id}", auth=self.auth, json={"featured_media": media_id}, timeout=Config.TIMEOUT)
            return media_id
        else:
            log(f"WP image upload error: {res.text}")
            return None
