import re

from services.product_builder import ProductBuilder
from services.article_builder import ArticleBuilder


product_builder = ProductBuilder.__new__(ProductBuilder)
article_builder = ArticleBuilder.__new__(ArticleBuilder)


def test_product_extract_json_plain():
    content = '{"description":"<p>hi</p>","seo":{"title":"t","description":"d","keywords":"k"},"hashtags":"#a"}'
    result = product_builder.extract_json(content)
    assert result["description"] == "<p>hi</p>"


def test_product_extract_json_markdown_fenced():
    content = '```json\n{"description":"<p>hi</p>","seo":{"title":"t","description":"d","keywords":"k"},"hashtags":"#a"}\n```'
    result = product_builder.extract_json(content)
    assert result is not None and "description" in result


def test_product_extract_json_strips_think_block():
    """The exact deepseek-r1 shape from the user's real log."""
    content = (
        "<think>\nOkay, let's break down this query...\n</think>\n\n"
        '{"description":"<p>hi</p>","seo":{"title":"t","description":"d","keywords":"k"},"hashtags":"#a"}'
    )
    result = product_builder.extract_json(content)
    assert result is not None and result["description"] == "<p>hi</p>"


def test_product_extract_json_unrecoverable_truncation_returns_none():
    content = '{"description": "<p>Perfect for eve'
    assert product_builder.extract_json(content) is None


def test_product_generate_full_product_falls_back_on_bad_json():
    """When the AI never produces valid JSON, generate_full_product
    should still return a usable dict instead of raising."""
    fake_client = type("FakeClient", (), {})()
    fake_client.chat = lambda *a, **k: {
        "model": "test",
        "choices": [{"finish_reason": "length", "message": {"content": "not json at all"}}],
    }
    pb = ProductBuilder(client=fake_client)
    result = pb.generate_full_product(title="Test Product")
    assert "description" in result and "seo" in result


def test_article_extract_json_strips_think_block():
    content = "<think>reasoning...</think>\n{\"title\":\"t\",\"chapters\":[]}"
    result = article_builder.extract_json(content)
    assert result == {"title": "t", "chapters": []}


def test_article_build_structure_raises_on_unparsable_content():
    fake_client = type("FakeClient", (), {})()
    fake_client.chat = lambda *a, **k: {
        "model": "test",
        "choices": [{"finish_reason": "stop", "message": {"content": "definitely not json"}}],
    }
    ab = ArticleBuilder(client=fake_client)
    try:
        ab.build_structure(keywords="test")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_article_builder_lazily_creates_its_default_client_before_chat(monkeypatch):
    """Regression test for a lazy client being constructed but then bypassed
    by a stale `self.client.chat(...)` call in build_structure."""
    fake_client = type("FakeClient", (), {})()
    fake_client.chat = lambda *a, **k: {
        "model": "test",
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": '{"title":"t","chapters":[]}'},
        }],
    }
    created = []

    def make_client():
        created.append(True)
        return fake_client

    monkeypatch.setattr("services.article_builder.OpenRouterClient", make_client)
    builder = ArticleBuilder()

    result = builder.build_structure(keywords="test")

    assert result["title"] == "t"
    assert result["chapters"] == []
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", result["slug"])
    assert created == [True]
    assert builder.client is fake_client


def test_article_build_structure_always_returns_ascii_unique_slug():
    """Mirrors ProductBuilder's link-safety guarantee: regardless of what
    (if anything) the model returns for "slug", the final result must be
    English/ASCII and unique — never a Persian permalink."""
    client = type("FakeClient", (), {})()
    client.chat = lambda *a, **k: {
        "model": "test",
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": '{"title":"راهنمای عینک","chapters":[],"slug":"راهنمای-انتخاب-عینک"}'},
        }],
    }
    ab = ArticleBuilder(client=client)

    result = ab.build_structure(keywords="عینک آفتابی")

    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", result["slug"])
    assert "راهنمای" not in result["slug"]


def test_article_build_structure_grounds_prompt_in_type_and_notes():
    """Mirrors the product builder's grounding test: article_type and notes
    must actually reach the prompt, not just be accepted and ignored."""
    calls = []

    class CapturingClient:
        def chat(self, messages, **kwargs):
            calls.append(messages)
            return {
                "model": "test",
                "choices": [{"finish_reason": "stop", "message": {"content": '{"title":"t","chapters":[]}'}}],
            }

    ab = ArticleBuilder(client=CapturingClient())
    ab.build_structure(
        keywords="عینک آفتابی",
        article_type="راهنمای خرید",
        notes="مخاطب افراد تازه‌کار است",
    )

    prompt = calls[0][0]["content"]
    assert "راهنمای خرید" in prompt
    assert "مخاطب افراد تازه‌کار است" in prompt


def test_article_build_structure_treats_x_as_skipped_notes():
    calls = []

    class CapturingClient:
        def chat(self, messages, **kwargs):
            calls.append(messages)
            return {
                "model": "test",
                "choices": [{"finish_reason": "stop", "message": {"content": '{"title":"t","chapters":[]}'}}],
            }

    ab = ArticleBuilder(client=CapturingClient())
    ab.build_structure(keywords="عینک آفتابی", notes="x")

    prompt = calls[0][0]["content"]
    assert "چیزی داده نشده" in prompt