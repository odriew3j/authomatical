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


def test_plugin_validates_article_slug_as_strict_ascii_and_resolves_conflicts():
    """Articles get the exact same link-safety guarantee as products: an
    AI-returned Persian (or missing) slug must never reach wp_insert_post
    unvalidated."""
    article = (PLUGIN / "includes" / "class-odviewsync-article.php").read_text(encoding="utf-8")

    assert "preg_match('/^[a-z0-9]+(?:-[a-z0-9]+)*$/', $slug)" in article
    assert "wp_generate_uuid4" in article
    assert "wp_unique_post_slug" in article


def test_plugin_attaches_featured_image_only_from_local_media_library():
    """create-post accepts a `featured_image` URL and resolves it with
    attachment_url_to_postid — which only matches attachments already on
    THIS site, never an arbitrary external image. This is what makes the
    Python-side "upload first, then create the job/post" ordering (see
    workers/common_handlers.py and services/blueprints/article.py) the
    only way a featured image actually gets attached."""
    article = (PLUGIN / "includes" / "class-odviewsync-article.php").read_text(encoding="utf-8")

    assert "$data['featured_image']" in article
    assert "attachment_url_to_postid($data['featured_image'])" in article
    assert "set_post_thumbnail($post_id, $attachment_id)" in article