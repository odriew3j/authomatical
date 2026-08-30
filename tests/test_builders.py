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
