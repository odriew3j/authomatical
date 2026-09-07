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
    main = (PLUGIN / "odview-sync.php").read_text(encoding="utf-8")

    # Backend address is a developer/build-time constant, never a site-owner
    # option: no admin-post handler, form, or wp_option persists a
    # per-site value, and the SaaS UI never renders an editable field for it.
    assert "define('ODVIEW_SYNC_BACKEND_URL'" in main
    assert "odview_sync_backend_url" not in auth
    assert "admin_post_odview_sync_save_backend_url" not in auth
    assert "name=\"backend_url\"" not in auth
    assert "ODVIEW_SYNC_BACKEND_URL" in auth
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


def test_plugin_reflects_existing_connection_before_offering_to_pair_again():
    """The settings page must not always show the pairing buttons: it checks
    /api/connect/status first and only reveals the chooser once it knows the
    site isn't already connected, so a returning admin sees a clear
    CONNECTED state instead of being invited to pair again by default."""
    auth = (PLUGIN / "includes" / "class-odviewsync-auth.php").read_text(encoding="utf-8")

    # Server side: a dedicated, nonce- and capability-checked, read-only
    # status action. It must never create/modify/delete a connection.
    assert "wp_ajax_odview_sync_check_connect_status" in auth
    assert "public function handle_check_connect_status" in auth
    status_handler = auth.split("public function handle_check_connect_status")[1].split(
        "public function", 1
    )[0]
    assert "current_user_can('manage_options')" in status_handler
    assert "check_ajax_referer('odview_sync_check_connect_status', 'nonce', false)" in status_handler
    assert "create_pending_connection" not in status_handler
    assert "save_wp_connection" not in status_handler
    # A network/backend hiccup must degrade to "unknown", never crash the
    # page or silently claim a connection that was never confirmed.
    assert "is_wp_error($response)" in status_handler
    assert "!is_array($decoded_body)" in status_handler

    # Client side: chooser starts hidden and is only shown once we have an
    # answer, so a page load never flashes "choose a bot" at someone who is
    # already connected; a confirmed connection renders its own state.
    assert "chooser.hidden = true;" in auth
    assert "function showConnected(" in auth
    assert "odview-connected-card" in auth

    # Buttons are disabled while a request is in flight, and any in-progress
    # completion poll is cleared before starting a new one — a double-click
    # or a second pairing attempt cannot leave two conflicting polls running.
    assert "setBusy(true);" in auth
    assert "if (pollTimer) { window.clearInterval(pollTimer); pollTimer = null; }" in auth

    # Success is reflected without a manual page refresh: after a link is
    # generated, the page polls status until the bot-side Start completes.
    assert "function pollUntilConnected(" in auth
    assert "pollUntilConnected(payload.data.platform, payload.data.expires_in);" in auth


def test_plugin_manual_connection_fallback_still_present_and_secondary():
    """The one-click flow must be the primary path; the pre-existing manual
    chat-based connection stays available only as a collapsed fallback."""
    auth = (PLUGIN / "includes" / "class-odviewsync-auth.php").read_text(encoding="utf-8")

    assert "<details class=\"odview-manual-connect\">" in auth
    assert "اتصال دستی / بازیابی" in auth
    # The manual path's own regenerate action keeps its own capability,
    # nonce and confirm-before-destructive-action guards.
    assert "admin_post_odview_sync_regenerate" in auth
    assert "check_admin_referer('odview_sync_regenerate')" in auth
    assert "onclick=\"return confirm(" in auth


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