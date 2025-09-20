import requests
from config import Config

class OpenRouterClient:
    BASE = "https://openrouter.ai/api/v1"

    def __init__(self, api_key=None, verify_ssl=True):
        self.api_key = api_key or Config.OPENROUTER_API_KEY
        self.verify_ssl = verify_ssl
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def chat(self, messages, model="gpt-4o-mini", max_tokens=500):
        url = f"{self.BASE}/chat/completions"
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
        for i in range(Config.MAX_RETRIES):
            r = requests.post(url, json=payload, headers=self.headers, timeout=Config.TIMEOUT, verify=self.verify_ssl)
            if r.ok: return r.json()
        r.raise_for_status()

    def generate_image(self, prompt, model="dall-e-3", size="1792x1024"):
        url = f"{self.BASE}/images/generate"
        payload = {"model": model, "prompt": prompt, "size": size}
        for i in range(Config.MAX_RETRIES):
            r = requests.post(url, json=payload, headers=self.headers, timeout=Config.TIMEOUT, verify=self.verify_ssl)
            if r.ok: return r.json()
        r.raise_for_status()
