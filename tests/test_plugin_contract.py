from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "wp-content" / "plugins" / "odview-sync"


def test_plugin_exposes_authenticated_create_post_endpoint():
    api = (PLUGIN / "includes" / "class-odviewsync-api.php").read_text(encoding="utf-8")
    article = (PLUGIN / "includes" / "class-odviewsync-article.php").read_text(encoding="utf-8")

    assert "'/create-post'" in api
    assert "'callback' => [$this, 'create_post']" in api
    assert "ODviewSync_Article::create" in api
    assert "'permission_callback' => ['ODviewSync_Auth', 'validate']" in api
    assert "wp_insert_post" in article


def test_plugin_validates_product_slug_as_strict_ascii_and_resolves_conflicts():
    product = (PLUGIN / "includes" / "class-odviewsync-product.php").read_text(encoding="utf-8")

    assert "preg_match('/^[a-z0-9]+(?:-[a-z0-9]+)*$/', $slug)" in product
    assert "wp_generate_uuid4" in product
    assert "wp_unique_post_slug" in product
