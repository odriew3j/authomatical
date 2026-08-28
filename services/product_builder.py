import logging
import json
import re
import datetime

from clients.ninerouter_client import NineRouterClient


logger = logging.getLogger(__name__)


class ProductBuilder:

    def __init__(self, client=None):
        self.client = client or NineRouterClient()

    def _extract_json(self, content):
        if not content:
            raise ValueError("AI returned empty content.")

        content = content.strip()

        # Remove markdown code fences
        content = re.sub(
            r"^```json\s*",
            "",
            content,
            flags=re.IGNORECASE,
        )

        content = re.sub(
            r"^```\s*",
            "",
            content,
        )

        content = re.sub(
            r"\s*```$",
            "",
            content,
        )

        content = content.strip()

        # First try direct JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting outermost JSON object
        start = content.find("{")
        end = content.rfind("}")

        if start != -1 and end != -1 and end > start:
            candidate = content[start:end + 1]

            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON returned by AI: {exc}"
                ) from exc

        raise ValueError(
            f"No JSON object found in AI response: "
            f"{content[:1000]}"
        )

    def generate_full_product(
        self,
        title,
        category="",
        brand="",
        tags=None,
        tone="informative",
        audience="general",
        max_tokens=2000,
    ):

        tags_str = ",".join(tags or [])

        prompt = f"""
You are an expert content writer and SEO specialist
for a WooCommerce eyewear store.

Today's date is {datetime.date.today().isoformat()}.

Input:

Product title:
{title}

Category:
{category}

Brand:
{brand or "Generate a suitable brand if missing"}

Tags:
{tags_str}

Tone:
{tone}

Audience:
{audience}

Requirements:

1. Generate a friendly, persuasive product description.

2. Description must use HTML only.

Allowed HTML:
<p>
<ul>
<li>
<b>
<i>

3. Fully SEO optimized.

4. Generate:
- SEO title
- Meta description
- Focus keywords
- Social media hashtags

5. Output ONLY valid JSON.

6. Required JSON structure:

{{
    "description": "<html>",
    "seo": {{
        "title": "...",
        "description": "...",
        "keywords": "keyword1,keyword2"
    }},
    "hashtags": "#tag1,#tag2"
}}

7. Content must feel premium and professional.

8. DO NOT mention:
- price
- discount
- currency
- payment
- shipping
- financial terms

9. Do not use Markdown.

10. Do not wrap the JSON in ```json.

Return ONLY the JSON object.
"""

        res = self.client.chat(
            [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            max_tokens=max_tokens,
        )

        try:
            message = res["choices"][0]["message"]

            content = message.get("content")

            if not content:
                raise ValueError(
                    "AI returned no content."
                )

            logger.info(
                "Product AI response model=%s finish_reason=%s",
                res.get("model"),
                res["choices"][0].get("finish_reason"),
            )

            return self._extract_json(content)

        except Exception as exc:

            logger.error(
                "Product generation/parsing failed: %s",
                exc,
            )

            # Log useful response for debugging
            logger.error(
                "Raw AI response: %s",
                str(res)[:5000],
            )

            raise