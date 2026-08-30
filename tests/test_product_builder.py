import re
from types import SimpleNamespace
from unittest.mock import patch

from services.product_builder import ProductBuilder, make_unique_slug, slugify_ascii


class CapturingClient:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return {
            "model": "test-model",
            "choices": [{"finish_reason": "stop", "message": {"content": self.content}}],
        }


def test_slugify_ascii_transliterates_latin_and_drops_non_ascii():
    assert slugify_ascii("Café crème / Metal Frame") == "cafe-creme-metal-frame"
    assert slugify_ascii("عینک طبی") == "product"
    assert slugify_ascii("عینک medical frame") == "medical-frame"


def test_make_unique_slug_is_ascii_and_uses_suffix():
    with patch(
        "services.product_builder.uuid.uuid4",
        return_value=SimpleNamespace(hex="a1b2c3d4e5f6"),
    ):
        slug = make_unique_slug("Medical Lens Metal Frame Glasses")

    assert slug == "medical-lens-metal-frame-glasses-a1b2c3"
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)


def test_product_generation_uses_type_and_seller_notes_and_enforces_ascii_slug():
    client = CapturingClient(
        """{
            "description": "<p>فریم فلزی سبک</p>",
            "slug": "عینک-طبی",
            "brand": "نمونه",
            "seo": {"title": "عنوان سئو", "description": "توضیح سئو", "keywords": "عینک,طبی"},
            "hashtags": "#عینک,#طبی"
        }"""
    )
    builder = ProductBuilder(client=client)

    with patch(
        "services.product_builder.uuid.uuid4",
        return_value=SimpleNamespace(hex="abcdef123456"),
    ):
        result = builder.generate_full_product(
            title="عینک طبی فریم فلزی",
            category="عینک",
            product_type="عینک طبی",
            user_notes="فریم تیتانیوم و عدسی بلوکات دارد",
            tags=["طبی", "فریم فلزی"],
        )

    prompt = client.calls[0][0][0]["content"]
    assert "Product type" in prompt
    assert "عینک طبی" in prompt
    assert "فریم تیتانیوم و عدسی بلوکات دارد" in prompt
    assert result["slug"] == "product-abcdef"
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", result["slug"])
    assert result["seo"]["title"] == "عنوان سئو"


def test_product_generation_fallback_still_has_all_payload_fields_and_slug():
    client = CapturingClient("not valid json")
    builder = ProductBuilder(client=client)

    with patch(
        "services.product_builder.uuid.uuid4",
        return_value=SimpleNamespace(hex="123456abcdef"),
    ):
        result = builder.generate_full_product(title="محصول فارسی")

    assert result["description"] == "not valid json"
    assert result["seo"] == {
        "title": "محصول فارسی",
        "description": "محصول فارسی",
        "keywords": "",
    }
    assert result["brand"] == ""
    assert result["hashtags"] == ""
    assert result["slug"] == "product-123456"


def test_product_generation_normalizes_valid_but_incomplete_model_json():
    client = CapturingClient('{"description": "<p>متن</p>", "slug": "valid English slug"}')
    builder = ProductBuilder(client=client)

    with patch(
        "services.product_builder.uuid.uuid4",
        return_value=SimpleNamespace(hex="fedcba987654"),
    ):
        result = builder.generate_full_product(title="عنوان")

    assert result["slug"] == "valid-english-slug-fedcba"
    assert result["seo"]["title"] == "عنوان"
    assert result["seo"]["description"] == "عنوان"
    assert result["seo"]["keywords"] == ""
