import re
import json
import logging

from clients.ninerouter_client import NineRouterClient


logger = logging.getLogger(__name__)


class ArticleBuilder:

    def __init__(self, client=None):
        self.client = client or NineRouterClient()

    def safe_json_load(self, content):

        if not content:
            raise ValueError(
                "AI returned empty content."
            )

        content = content.strip()

        # Remove markdown fences
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

        # Direct JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Extract JSON object
        start = content.find("{")
        end = content.rfind("}")

        if start == -1 or end == -1 or end <= start:
            raise ValueError(
                "No JSON object found in AI response."
            )

        candidate = content[start:end + 1]

        try:
            return json.loads(candidate)

        except json.JSONDecodeError as exc:

            logger.error(
                "JSON decode error: %s",
                exc,
            )

            logger.error(
                "AI content: %s",
                content[:5000],
            )

            raise ValueError(
                f"Invalid JSON returned by AI: {exc}"
            ) from exc

    def build_structure(
        self,
        keywords,
        num_chapters=5,
        tone="informative",
        audience="general",
        max_tokens=4000,
        include_sections=None,
    ):

        include_sections = include_sections or [
            "title",
            "subtitle",
            "introduction",
            "conclusions",
            "imagePrompt",
            "chapters",
        ]

        prompt = f"""
You are an expert SEO article writer.

Topic:
{keywords}

Tone:
{tone}

Audience:
{audience}

Number of chapters:
{num_chapters}

Required fields:
{json.dumps(include_sections, ensure_ascii=False)}

Requirements:

1. Create a detailed SEO-friendly article.

2. Use HTML formatting only inside text fields.

Allowed HTML:
<p>
<ul>
<li>
<b>
<i>
<h2>
<h3>

3. Create exactly {num_chapters} chapters.

4. Chapters must be logically related.

5. The article must be fluent and coherent.

6. Return ONLY valid JSON.

7. Do NOT use Markdown.

8. Do NOT use ```json.

Required JSON structure:

{{
    "title": "...",
    "subtitle": "...",
    "introduction": "<p>...</p>",
    "imagePrompt": "...",
    "chapters": [
        {{
            "title": "...",
            "content": "<p>...</p>"
        }}
    ],
    "conclusions": "<p>...</p>"
}}

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

            choice = res["choices"][0]

            message = choice.get("message") or {}

            content = message.get("content")

            if not content:
                raise ValueError(
                    "AI returned empty article content."
                )

            logger.info(
                "Article AI response model=%s finish_reason=%s",
                res.get("model"),
                choice.get("finish_reason"),
            )

            article_json = self.safe_json_load(content)

            if not article_json:
                raise ValueError(
                    "Failed to parse article JSON."
                )

            return article_json

        except Exception as exc:

            logger.error(
                "Article generation/parsing failed: %s",
                exc,
            )

            logger.error(
                "Raw AI response: %s",
                str(res)[:5000],
            )

            raise