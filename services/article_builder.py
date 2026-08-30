import json
import logging
import re

from clients.ninerouter_client import NineRouterClient
from clients.openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)


class ArticleBuilder:

    def __init__(self, client=None):
        # Delay API-key validation until generation is actually requested.
        # That keeps worker imports and test discovery independent of a live
        # OpenRouter configuration while preserving the same runtime client.
        self.client = client

    def _get_client(self):
        if self.client is None:
            # self.client = NineRouterClient()
            self.client = OpenRouterClient()
        return self.client

    # Shared with ProductBuilder's approach: tolerant of <think> blocks,
    # markdown fences, and prose wrapped around the JSON object.
    @staticmethod
    def extract_json(content):
        if not content:
            return None

        content = content.strip()
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()
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
        if start == -1 or end == -1 or end <= start:
            logger.error("No JSON object found in AI response:\n%s", content[:5000])
            return None

        candidate = content[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            logger.error("Article JSON decode error: %s | content:\n%s", exc, content[:5000])
            return None

    # Kept for backwards compatibility with any external caller still
    # using the old method name.
    def safe_json_load(self, content):
        return self.extract_json(content)

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
            "title", "subtitle", "introduction", "conclusions", "imagePrompt", "chapters"
        ]

        prompt = f"""
Write a detailed, SEO-friendly article in PERSIAN for Persian-speaking
readers.

Topic: {keywords}
Tone: {tone}
Audience: {audience}
Number of chapters: {num_chapters}
Required fields: {json.dumps(include_sections, ensure_ascii=False)}

CRITICAL — content must be concrete and real, never vague filler:
1. Every chapter must say something specific, accurate, and useful about
   the topic — real facts, real how-tos, real comparisons. Do not pad
   with generic sentences that could apply to any topic ("this is very
   important", "there are many benefits", "in today's world").
2. Do not invent statistics, studies, or specific claims you can't
   support in general knowledge terms — stick to well-established,
   broadly true information about the topic.
3. Use HTML formatting inside text fields only. Allowed tags: <p> <ul> <li> <b> <i> <h2> <h3>
4. Create exactly {num_chapters} chapters, logically connected and fluent.
5. Return ONLY valid JSON, no Markdown, no <think> blocks.

Required JSON structure (exactly these keys):
{{
    "title": "...",
    "subtitle": "...",
    "introduction": "<p>...</p>",
    "imagePrompt": "...",
    "chapters": [
        {{"title": "...", "content": "<p>...</p>"}}
    ],
    "conclusions": "<p>...</p>"
}}
"""

        res = self.client.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.4,
        )

        choice = res["choices"][0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        finish_reason = choice.get("finish_reason")

        logger.info(
            "Article generation: model=%s finish_reason=%s",
            res.get("model"), finish_reason,
        )
        if finish_reason == "length":
            logger.warning("Article generation was truncated (max_tokens reached).")

        article_json = self.extract_json(content)
        if not article_json:
            logger.error("Raw AI response (article):\n%s", str(res)[:5000])
            raise ValueError("Failed to parse JSON from 9Router response.")

        return article_json