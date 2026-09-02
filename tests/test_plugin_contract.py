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


def test_plugin_offers_server_side_one_click_pairing_without_external_qr_or_secret_links():
    auth = (PLUGIN / "includes" / "class-odviewsync-auth.php").read_text(encoding="utf-8")
    css = (PLUGIN / "assets" / "admin.css").read_text(encoding="utf-8")

    assert "odview_sync_backend_url" in auth
    assert "admin_post_odview_sync_save_backend_url" in auth
    assert "wp_ajax_odview_sync_generate_connect_token" in auth
    assert "current_user_can('manage_options')" in auth
    assert "check_ajax_referer('odview_sync_generate_connect_token', 'nonce', false)" in auth
    assert "random_bytes(32)" in auth
    assert "hash_hmac('sha256'" in auth
    assert "wp_safe_remote_post" in auth
    assert "X-ODVIEW-CONNECT-PROOF" in auth
    assert "'token' => $token" in auth
    assert "'secret' => $secret" in auth
    assert "'issued_at' => $issued_at" in auth
    assert "data-platform=\"telegram\"" in auth
    assert "data-platform=\"bale\"" in auth
    assert "qr_paths" in auth
    assert "referrerPolicy = 'no-referrer'" in auth
    assert "window.open('about:blank', '_blank')" in auth
    assert "api.qrserver.com" not in auth
    assert "quickchart.io" not in auth
    assert "odview-pairing-card" in css


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