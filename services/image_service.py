from clients.openrouter_client import OpenRouterClient

class ImageService:
    def __init__(self):
        self.client = OpenRouterClient()

    def generate(self, title, image_prompt):
        prompt = f"Photographic image for article titled: {title}. {image_prompt}, realistic."
        return self.client.generate_image(prompt)
