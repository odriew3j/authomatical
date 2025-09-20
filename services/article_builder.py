import re
import json
import logging
from clients.openrouter_client import OpenRouterClient

class ArticleBuilder:
    def __init__(self, client=None):
        self.client = client or OpenRouterClient()
        logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

    def safe_json_load(self, content):
        """Parse JSON safely, remove ```json … ``` blocks"""
        try:
            if isinstance(content, dict):
                return content
            # Remove ```json ... ``` or ``` ... ```
            content = re.sub(r"^```json|```$", "", content.strip(), flags=re.MULTILINE)
            content = re.sub(r"^```|```$", "", content.strip(), flags=re.MULTILINE)
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                return json.loads(match.group())
            logging.error(f"No JSON found in content: {content}")
            return None
        except json.JSONDecodeError as e:
            logging.error(f"JSON decode error: {e} | Content: {content}")
            return None
        

    def build_structure(
        self,
        keywords,
        num_chapters=5,
        tone="informative",
        audience="general",
        max_tokens=2000,
        include_sections=None
    ):
        """
        Build a detailed SEO-friendly article structure.
        Parameters:
            keywords: main keywords or topic
            num_chapters: number of chapters
            tone: writing style (informative, persuasive, friendly, technical)
            audience: target audience
            max_tokens: approximate max tokens for the article
            include_sections: list of optional fields ['title', 'subtitle', 'introduction', 'conclusions', 'imagePrompt', 'chapters']
        """
        include_sections = include_sections or ["title", "subtitle", "introduction", "conclusions", "imagePrompt", "chapters"]

        prompt = f"""
        Write a SEO-friendly article based on the topic "{keywords}".
        Output only valid JSON with the following structure:
        Tone: {tone}
        Audience: {audience}
        Output only valid JSON including fields: {include_sections}.
        Use HTML formatting, no Markdown.
        - Use {num_chapters} chapters.
        - Output only valid JSON.
        - Use HTML for bold, italic, lists; no Markdown.
        - Chapters must be related and fluent.
        """

        try:
            res = self.client.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens)
            content = res["choices"][0]["message"]["content"]
            logging.info(f"Raw content from OpenRouter:\n{content}")

            # Use safe JSON parser
            article_json = self.safe_json_load(content)
            if not article_json:
                raise ValueError("Failed to parse JSON from OpenRouter")
        except Exception as e:
            logging.error(f"Error parsing OpenRouter response: {e}")
            raise

        return article_json