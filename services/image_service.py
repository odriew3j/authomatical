from clients.ninerouter_client import NineRouterClient


class ImageService:
    """Optional article-image generator.

    Image generation is currently disabled in the normal article pipeline,
    so keep its API client lazy instead of making every article worker require
    a NineRouter key merely to start up.
    """

    def __init__(self, client=None):
        self.client = client

    def _get_client(self):
        if self.client is None:
            self.client = NineRouterClient()
        return self.client

    def generate(self, title, image_prompt):
        prompt = f"Photographic image for article titled: {title}. {image_prompt}, realistic."
        return self._get_client().generate_image(prompt)
