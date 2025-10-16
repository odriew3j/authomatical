import logging
import json
import re
import datetime

from clients.openrouter_client import OpenRouterClient

class ProductBuilder:
    def __init__(self, client=None):
        self.client = client or OpenRouterClient()
        logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

    def generate_full_product(
        self, title, price=0, sale_price=None, category="", brand="", tags=None, 
        tone="informative", audience="general", max_tokens=1200
    ):
        tags_str = ",".join(tags or [])
        prompt = f"""
        You are an expert content writer and SEO specialist for a WooCommerce eyewear store. 
        Today's date is {datetime.date.today().isoformat()}.

        Input:
        - Product title: {title}
        - Category: {category}
        - Brand: {brand or 'AI will generate a suitable brand if missing'}
        - Price: {price}
        - Sale price: {sale_price if sale_price else 'N/A'}

        Requirements:
        1. Generate a **friendly, conversational, and persuasive product description** in HTML format, using <p>, <ul>, <li>, <b>, <i> tags where appropriate.
        2. Make the description **SEO-friendly**, attractive to buyers, and fully optimized for modern search engines as of today.
        3. Suggest **SEO metadata**: title, meta description, and focus keywords based on the product and category.
        4. Suggest **relevant, trending hashtags** for social media promotion (comma-separated).
        5. Ensure all output is **up-to-date, relevant, and professional**, while still being easy and enjoyable for the user to read.
        6. Output **strictly valid JSON only** with fields:

        {{
        "description": "<html...>",
        "seo": {{
            "title": "...",
            "description": "...",
            "keywords": "comma,separated,list"
        }},
        "hashtags": "comma,separated"
        }}
        """
        res = self.client.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens)
        content = res["choices"][0]["message"]["content"]

        try:
            content = re.sub(r"^```json|```$", "", content.strip(), flags=re.MULTILINE)
            content = re.sub(r"^```|```$", "", content.strip(), flags=re.MULTILINE)
            return json.loads(content)
        except Exception:
            # fallback: JSON 
            return {
                "description": content,
                "seo": {"title": title, "description": content[:150], "keywords": ""},
                "hashtags": ""
            }
