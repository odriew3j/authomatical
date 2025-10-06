import logging
from clients.openrouter_client import OpenRouterClient

class ProductBuilder:
    def __init__(self, client=None):
        self.client = client or OpenRouterClient()
        logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

    def generate_description(self, title, keywords="", tone="informative", audience="general", max_tokens=600):
        prompt = f"""
        Write a professional product description for an online store.
        Product: {title}
        Keywords: {keywords}
        Tone: {tone}
        Audience: {audience}
        Requirements:
        - Use SEO-friendly wording
        - Highlight main features and benefits
        - Write in HTML (paragraphs, lists, bold/italic where useful)
        """
        res = self.client.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens)
        return res["choices"][0]["message"]["content"]

    def generate_seo(self, title, keywords="", max_tokens=200):
        prompt = f"""
        Generate SEO metadata for a WooCommerce product.
        Product title: {title}
        Keywords: {keywords}
        Output JSON with fields: 
        {{
          "title": "...",
          "description": "...",
          "keywords": "comma,separated,list"
        }}
        """
        res = self.client.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens)
        content = res["choices"][0]["message"]["content"]

        import json, re
        try:
            content = re.sub(r"^```json|```$", "", content.strip(), flags=re.MULTILINE)
            content = re.sub(r"^```|```$", "", content.strip(), flags=re.MULTILINE)
            return json.loads(content)
        except Exception:
            return {"title": title, "description": content[:150], "keywords": keywords}
