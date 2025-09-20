from clients.wordpress_client import WordPressClient

class WordPressPostModule:
    def __init__(self):
        self.wp = WordPressClient()

    def create_post(self, title, content, status="draft"):
        return self.wp.create_post(title, content, status)

    def upload_media(self, post_id, image_bytes, filename="featured.jpg"):
        return self.wp.upload_media(post_id, image_bytes, filename)
