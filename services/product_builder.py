import datetime
import json
import logging
import re

from clients.ninerouter_client import NineRouterClient
from clients.openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)


class ProductBuilder:

    def __init__(self, client=None):
        # self.client = client or NineRouterClient()
        self.client = client or OpenRouterClient()

    # ---------------------------------------------------------
    # Extract JSON from model output — tolerant of <think> blocks,
    # markdown code fences, and surrounding prose.
    # ---------------------------------------------------------
    @staticmethod
    def extract_json(content):
        if not content:
            return None

        content = content.strip()

        # Strip a reasoning block some models prepend (e.g. deepseek-r1)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()

        # Strip ```json ... ``` / ``` ... ``` fences
        content = re.sub(r"^```json\s*", "", content, flags=re.IGNORECASE)
        content = re.sub(r"^```\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        content = content.strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = content[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                logger.warning("Product JSON parsing failed: %s", exc)

        return None

    def generate_full_product(
        self,
        title,
        category="",
        brand="",
        tags=None,
        tone="informative",
        audience="general",
        max_tokens=2500,
    ):
        tags_str = ",".join(tags or [])

        prompt = f"""
You are an expert SEO content writer for a premium WooCommerce eyewear store.

Today's date: {datetime.date.today().isoformat()}

Product information:
- Product title: {title}
- Category: {category}
- Brand: {brand or "Generate a suitable brand name if necessary"}
- Tags: {tags_str}
- Tone: {tone}
- Audience: {audience}

Create premium, professional product content.

Requirements:
1. Write a persuasive product description in HTML.
2. Allowed HTML tags only: <p> <ul> <li> <b> <i>
3. Fully SEO optimize the content.
4. Generate: SEO title, meta description, focus keywords, social media hashtags.
5. Do NOT mention: price, discount, currency, payment, shipping, cost, or any financial term.
6. Do not invent technical specifications that were not provided.
7. Return ONLY valid JSON, no Markdown, no <think> blocks.

Required JSON structure (exactly these keys):
{{
    "description": "<p>...</p>",
    "seo": {{
        "title": "...",
        "description": "...",
        "keywords": "keyword1,keyword2,keyword3"
    }},
    "hashtags": "#tag1,#tag2,#tag3"
}}
"""

        res = self.client.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.4,
        )

        choice = res["choices"][0]
        message = choice.get("message", {})
        content = message.get("content") or ""
        finish_reason = choice.get("finish_reason")

        logger.info(
            "Product generation completed: model=%s finish_reason=%s",
            res.get("model"), finish_reason,
        )
        if finish_reason == "length":
            logger.warning("Product generation was truncated (max_tokens reached).")

        result = self.extract_json(content)
        if result is not None:
            return result

        logger.error("Could not parse product JSON. Raw content:\n%s", content[:5000])
        # Fallback so the caller still gets a usable-ish dict rather than
        # a crash — the product will still be created, just with a plain
        # (non-AI-structured) description.
        return {
            "description": content or f"<p>{title}</p>",
            "seo": {"title": title, "description": (content or title)[:150], "keywords": ""},
            "hashtags": "",
        }
