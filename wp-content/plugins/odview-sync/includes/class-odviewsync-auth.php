<?php

if (!defined('ABSPATH')) exit;

class ODviewSync_Auth {

    private $option_key = 'odview_sync_secret';

    public function __construct() {
        add_action('admin_menu', [$this, 'add_menu']);
        add_action('admin_init', [$this, 'generate_secret']);
        add_action('admin_enqueue_scripts', [$this, 'enqueue_admin_assets']);
        add_action('admin_post_odview_sync_regenerate', [$this, 'handle_regenerate']);
        add_action('wp_ajax_odview_sync_generate_connect_token', [$this, 'handle_generate_connect_token']);
        add_action('wp_ajax_odview_sync_check_connect_status', [$this, 'handle_check_connect_status']);
    }

    // Generate on first install. This secret authenticates only server-to-server
    // plugin calls; the one-click UI never places it in a deep link or QR code.
    public function generate_secret() {
        if (!get_option($this->option_key)) {
            $secret = wp_generate_password(40, false);
            update_option($this->option_key, $secret);
        }
    }

    public static function validate($request) {
        $secret = get_option('odview_sync_secret');
        $header = $request->get_header('x-odview-secret');

        if (!$secret || !$header || !hash_equals($secret, $header)) {
            return new WP_Error('forbidden', 'Invalid Secret Key', ['status' => 403]);
        }

        return true;
    }

    public function enqueue_admin_assets($hook_suffix) {
        if ($hook_suffix !== 'toplevel_page_odview-sync') {
            return;
        }
        wp_enqueue_style(
            'odview-sync-admin',
            plugins_url('assets/admin.css', ODVIEW_SYNC_PLUGIN_FILE),
            [],
            ODVIEW_SYNC_VERSION
        );
    }

    public function handle_regenerate() {
        if (!current_user_can('manage_options')) {
            wp_die('دسترسی غیرمجاز');
        }
        check_admin_referer('odview_sync_regenerate');
        update_option($this->option_key, wp_generate_password(40, false));
        wp_safe_redirect(admin_url('admin.php?page=odview-sync&regenerated=1'));
        exit;
    }

    // The backend address is a developer-controlled constant (see
    // odview-sync.php), never a site owner's option. This only re-validates
    // the constant's shape — the same rules the old settings-page field
    // enforced — so a bad value fails loudly instead of silently building a
    // broken QR/deep-link URL.
    private function backend_url() {
        $url = defined('ODVIEW_SYNC_BACKEND_URL') ? untrailingslashit((string) ODVIEW_SYNC_BACKEND_URL) : '';
        if (!$url) {
            return '';
        }
        $parts = wp_parse_url($url);
        if (!$parts || empty($parts['host']) || empty($parts['scheme']) || strtolower($parts['scheme']) !== 'https') {
            return '';
        }
        if (isset($parts['user']) || isset($parts['pass']) || isset($parts['query']) || isset($parts['fragment']) ||
            (!empty($parts['path']) && trim($parts['path'], '/') !== '')) {
            // The pairing backend is mounted at its hostname root. Reject a
            // path prefix rather than silently constructing a broken QR URL.
            return '';
        }
        return wp_http_validate_url($url) ? $url : '';
    }

    private function redirect_to_settings($args = []) {
        $url = add_query_arg($args, admin_url('admin.php?page=odview-sync'));
        wp_safe_redirect($url);
        exit;
    }

    private function generated_connect_token() {
        // 32 random bytes become exactly 43 unpadded base64url characters:
        // 256 bits of entropy while keeping connect_<token> under Telegram's
        // 64-character deep-link payload limit.
        try {
            return rtrim(strtr(base64_encode(random_bytes(32)), '+/', '-_'), '=');
        } catch (Exception $exception) {
            return '';
        }
    }

    private function valid_platform($platform) {
        return in_array($platform, ['telegram', 'bale'], true);
    }

    private function expected_deep_link($url, $platform, $token) {
        if (!is_string($url) || !wp_http_validate_url($url)) {
            return false;
        }
        $parts = wp_parse_url($url);
        $expected_host = $platform === 'telegram' ? 't.me' : 'ble.ir';
        if (!$parts || empty($parts['scheme']) || strtolower($parts['scheme']) !== 'https' ||
            empty($parts['host']) || strtolower($parts['host']) !== $expected_host) {
            return false;
        }
        $query = [];
        parse_str(isset($parts['query']) ? $parts['query'] : '', $query);
        return isset($query['start']) && is_string($query['start']) &&
            hash_equals('connect_' . $token, $query['start']);
    }

    private function backend_qr_path($path, $platform, $token) {
        if (!is_string($path)) {
            return false;
        }
        // The backend returns only this exact relative route. The plugin adds
        // its already validated HTTPS backend origin, so a response cannot
        // switch the browser to an external QR service and leak the token.
        $expected = '/api/connect/qr/' . rawurlencode($token) . '.svg?platform=' . rawurlencode($platform);
        return hash_equals($expected, $path);
    }

    private function backend_error_message($decoded_body) {
        if (!is_array($decoded_body) || empty($decoded_body['message']) || !is_string($decoded_body['message'])) {
            return 'ارتباط امن با سرور اتصال ناموفق بود. تنظیمات را بررسی و دوباره تلاش کنید.';
        }
        return sanitize_text_field($decoded_body['message']);
    }

    public function handle_generate_connect_token() {
        if (!current_user_can('manage_options')) {
            wp_send_json_error(['message' => 'دسترسی غیرمجاز است.'], 403);
        }
        if (!check_ajax_referer('odview_sync_generate_connect_token', 'nonce', false)) {
            wp_send_json_error(['message' => 'درخواست امنیتی معتبر نیست. صفحه را تازه‌سازی کنید.'], 403);
        }

        $platform = isset($_POST['platform']) ? sanitize_key(wp_unslash($_POST['platform'])) : '';
        if (!$this->valid_platform($platform)) {
            wp_send_json_error(['message' => 'پلتفرم انتخاب‌شده معتبر نیست.'], 400);
        }

        $backend_url = $this->backend_url();
        if (!$backend_url) {
            wp_send_json_error(['message' => 'سرویس اتصال به‌درستی پیکربندی نشده است. با پشتیبانی تماس بگیرید.'], 500);
        }

        $site_url = untrailingslashit(get_site_url());
        if (strtolower((string) wp_parse_url($site_url, PHP_URL_SCHEME)) !== 'https') {
            wp_send_json_error(['message' => 'برای اتصال یک‌کلیکی، آدرس عمومی HTTPS برای سایت وردپرس لازم است.'], 400);
        }

        $secret = get_option($this->option_key);
        if (!is_string($secret) || $secret === '') {
            wp_send_json_error(['message' => 'کلید امنیتی افزونه در دسترس نیست.'], 500);
        }

        $token = $this->generated_connect_token();
        if (!$token) {
            wp_send_json_error(['message' => 'ساخت امن لینک اتصال ناموفق بود. دوباره تلاش کنید.'], 500);
        }

        // This HMAC and the JSON body travel only from the WordPress server to
        // the configured HTTPS backend. A short freshness window on issued_at
        // also prevents a captured request body from reviving an old link.
        // Neither value is injected into page markup.
        $issued_at = time();
        $proof = hash_hmac('sha256', $platform . "\n" . $site_url . "\n" . $token . "\n" . $issued_at, $secret);
        $response = wp_safe_remote_post($backend_url . '/api/connect/register', [
            'timeout' => 20,
            'redirection' => 0,
            'sslverify' => true,
            'headers' => [
                'Content-Type' => 'application/json; charset=utf-8',
                'Accept' => 'application/json',
                'X-ODVIEW-CONNECT-PROOF' => $proof,
                'User-Agent' => 'ODview-Sync/' . ODVIEW_SYNC_VERSION,
            ],
            'body' => wp_json_encode([
                'token' => $token,
                'platform' => $platform,
                'site_url' => $site_url,
                'secret' => $secret,
                'issued_at' => $issued_at,
            ]),
        ]);

        if (is_wp_error($response)) {
            // Deliberately do not expose or log request details; they include
            // the WordPress shared secret in the server-to-server JSON body.
            wp_send_json_error(['message' => 'سرور اتصال در دسترس نیست. URL و دسترسی اینترنتی سایت را بررسی کنید.'], 502);
        }

        $status = (int) wp_remote_retrieve_response_code($response);
        $decoded_body = json_decode(wp_remote_retrieve_body($response), true);
        if ($status < 200 || $status >= 300 || !is_array($decoded_body) || ($decoded_body['status'] ?? '') !== 'ok') {
            $safe_status = ($status >= 400 && $status < 600) ? $status : 502;
            wp_send_json_error(['message' => $this->backend_error_message($decoded_body)], $safe_status);
        }

        $deep_link = isset($decoded_body['deep_links'][$platform]) ? $decoded_body['deep_links'][$platform] : '';
        $qr_path = isset($decoded_body['qr_paths'][$platform]) ? $decoded_body['qr_paths'][$platform] : '';
        if (!$this->expected_deep_link($deep_link, $platform, $token) ||
            !$this->backend_qr_path($qr_path, $platform, $token)) {
            wp_send_json_error(['message' => 'پاسخ سرور اتصال معتبر نیست. دوباره تلاش کنید.'], 502);
        }
        $qr_url = $backend_url . $qr_path;

        // Do not return token, secret or HMAC as standalone fields. The token
        // appears only inside the necessary short-lived bot link / local QR URL.
        wp_send_json_success([
            'platform' => $platform,
            'deep_link' => esc_url_raw($deep_link),
            'qr_url' => esc_url_raw($qr_url),
            'expires_in' => min(max((int) ($decoded_body['expires_in'] ?? 0), 0), 900),
        ]);
    }

    // Read-only: lets the settings page show CONNECTED (and which platform)
    // up front instead of always presenting the pairing buttons, so a site
    // owner who already paired doesn't wonder whether clicking again is
    // safe. Never creates, changes, or deletes a connection — a failed or
    // unclear answer here must never block the normal pairing buttons below.
    public function handle_check_connect_status() {
        if (!current_user_can('manage_options')) {
            wp_send_json_error(['message' => 'دسترسی غیرمجاز است.'], 403);
        }
        if (!check_ajax_referer('odview_sync_check_connect_status', 'nonce', false)) {
            wp_send_json_error(['message' => 'درخواست امنیتی معتبر نیست.'], 403);
        }

        $backend_url = $this->backend_url();
        $secret = get_option($this->option_key);
        if (!$backend_url || !is_string($secret) || $secret === '') {
            wp_send_json_success(['connected' => false, 'checked' => false]);
        }

        $site_url = untrailingslashit(get_site_url());
        $issued_at = time();
        $proof = hash_hmac('sha256', "status\n{$site_url}\n{$issued_at}", $secret);

        $response = wp_safe_remote_post($backend_url . '/api/connect/status', [
            'timeout' => 10,
            'redirection' => 0,
            'sslverify' => true,
            'headers' => [
                'Content-Type' => 'application/json; charset=utf-8',
                'Accept' => 'application/json',
                'X-ODVIEW-CONNECT-PROOF' => $proof,
                'User-Agent' => 'ODview-Sync/' . ODVIEW_SYNC_VERSION,
            ],
            'body' => wp_json_encode([
                'site_url' => $site_url,
                'secret' => $secret,
                'issued_at' => $issued_at,
            ]),
        ]);

        // A network hiccup or a backend blip is not "not connected" — it's
        // unknown. The page falls back to the pairing buttons either way,
        // but keeps the two cases distinct for support/debugging later.
        if (is_wp_error($response)) {
            wp_send_json_success(['connected' => false, 'checked' => false]);
        }
        $status = (int) wp_remote_retrieve_response_code($response);
        $decoded_body = json_decode(wp_remote_retrieve_body($response), true);
        if ($status < 200 || $status >= 300 || !is_array($decoded_body) || ($decoded_body['status'] ?? '') !== 'ok') {
            wp_send_json_success(['connected' => false, 'checked' => false]);
        }

        if (empty($decoded_body['connected'])) {
            wp_send_json_success(['connected' => false, 'checked' => true]);
        }

        $platform = is_string($decoded_body['platform'] ?? null) ? sanitize_key($decoded_body['platform']) : '';
        wp_send_json_success([
            'connected' => true,
            'checked' => true,
            'platform' => $this->valid_platform($platform) ? $platform : '',
        ]);
    }

    // Admin page: one-click pairing is the primary path; the old manual path
    // remains available as a recovery option for installations that cannot be
    // publicly reached by the backend.
    public function add_menu() {
        add_menu_page('ODview Sync', 'اتصال به بازو', 'manage_options', 'odview-sync', [$this, 'render_page'], 'dashicons-admin-links');
    }

    public function render_page() {
        if (!current_user_can('manage_options')) return;

        $secret = get_option($this->option_key);
        $site_url = get_site_url();
        $backend_url = $this->backend_url();
        $wc_active = class_exists('WooCommerce');
        ?>
        <div class="wrap odview-sync-wrap">
            <h1>اتصال سایت به بازو (بله / تلگرام)</h1>

            <?php if (isset($_GET['regenerated'])): ?>
                <div class="notice notice-success"><p>کلید امنیتی جدید ساخته شد. توجه: اگر قبلاً این سایت را در ربات وصل کرده‌اید، باید دوباره وصل کنید چون کلید قبلی دیگر معتبر نیست.</p></div>
            <?php endif; ?>
            <?php if (!$wc_active): ?>
                <div class="notice notice-warning"><p>⚠️ افزونه‌ی ووکامرس روی این سایت فعال نیست. ساخت محصول از طریق بازو نیاز به ووکامرس دارد.</p></div>
            <?php endif; ?>

            <section class="odview-pairing-card" aria-labelledby="odview-pairing-title">
                <div class="odview-pairing-card__heading">
                    <span class="dashicons dashicons-admin-links" aria-hidden="true"></span>
                    <div>
                        <h2 id="odview-pairing-title">اتصال امن با یک کلیک</h2>
                        <p>بله یا تلگرام را انتخاب کنید و لینک یا QR را باز کنید. هیچ کلید امنیتی در چت، لینک یا QR نمایش داده نمی‌شود.</p>
                    </div>
                </div>

                <?php if ($backend_url): ?>
                    <div id="odview-pairing-app" class="odview-pairing-app"
                        data-ajax-url="<?php echo esc_url(admin_url('admin-ajax.php')); ?>"
                        data-nonce="<?php echo esc_attr(wp_create_nonce('odview_sync_generate_connect_token')); ?>"
                        data-status-nonce="<?php echo esc_attr(wp_create_nonce('odview_sync_check_connect_status')); ?>">
                        <p id="odview-connection-status" class="odview-pairing-status" role="status" aria-live="polite">در حال بررسی وضعیت اتصال…</p>
                        <div id="odview-connected-card" class="odview-connected-card" hidden></div>
                        <div id="odview-pairing-chooser">
                            <h3>ربات موردنظر را انتخاب کنید</h3>
                            <div class="odview-pairing-actions">
                                <button type="button" class="button button-primary button-hero odview-pairing-button" data-platform="telegram">
                                    <span class="dashicons dashicons-format-chat" aria-hidden="true"></span> اتصال با تلگرام
                                </button>
                                <button type="button" class="button button-secondary button-hero odview-pairing-button" data-platform="bale">
                                    <span class="dashicons dashicons-format-chat" aria-hidden="true"></span> اتصال با بله
                                </button>
                            </div>
                        </div>
                        <p id="odview-pairing-status" class="odview-pairing-status" role="status" aria-live="polite"></p>
                        <div id="odview-pairing-result" class="odview-pairing-result" hidden></div>
                    </div>
                <?php else: ?>
                    <p class="odview-pairing-hint">سرویس اتصال در حال حاضر در دسترس نیست. لطفاً بعداً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.</p>
                <?php endif; ?>
            </section>

            <details class="odview-manual-connect">
                <summary>اتصال دستی / بازیابی</summary>
                <p>اگر سایت شما از اینترنت عمومی برای سرور بازو قابل دسترس نیست، می‌توانید مانند قبل اطلاعات زیر را فقط داخل چت بازوی خودتان وارد کنید.</p>
                <table class="form-table">
                    <tr>
                        <th scope="row">آدرس سایت</th>
                        <td><input type="text" value="<?php echo esc_attr($site_url); ?>" style="width:420px" readonly onclick="this.select()"></td>
                    </tr>
                    <tr>
                        <th scope="row">کلید امنیتی</th>
                        <td>
                            <input type="text" value="<?php echo esc_attr($secret); ?>" style="width:420px;font-family:monospace" readonly onclick="this.select()">
                            <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>" class="odview-regenerate-form">
                                <?php wp_nonce_field('odview_sync_regenerate'); ?>
                                <input type="hidden" name="action" value="odview_sync_regenerate">
                                <button type="submit" class="button" onclick="return confirm('با ساخت کلید جدید، اتصال فعلی ربات به این سایت قطع می‌شود و باید دوباره وصل شوید. ادامه می‌دهید؟');">ساخت کلید جدید</button>
                            </form>
                        </td>
                    </tr>
                </table>
                <ol>
                    <li>در بله یا تلگرام گفتگو با بازوی خودتان را شروع کنید (<code>/start</code>).</li>
                    <li>گزینه‌ی «۱. وارد کردن اطلاعات وردپرس» را انتخاب کنید.</li>
                    <li>آدرس سایت و سپس کلید امنیتی بالا را فقط در همان چت ارسال کنید.</li>
                </ol>
            </details>
        </div>

        <?php if ($backend_url): ?>
        <script>
        (function () {
            var app = document.getElementById('odview-pairing-app');
            if (!app || !window.fetch) return;

            var buttons = app.querySelectorAll('.odview-pairing-button');
            var status = document.getElementById('odview-pairing-status');
            var result = document.getElementById('odview-pairing-result');
            var connectionStatus = document.getElementById('odview-connection-status');
            var connectedCard = document.getElementById('odview-connected-card');
            var chooser = document.getElementById('odview-pairing-chooser');
            var names = {telegram: 'تلگرام', bale: 'بله'};

            function showChooser() {
                connectedCard.hidden = true;
                while (connectedCard.firstChild) connectedCard.removeChild(connectedCard.firstChild);
                chooser.hidden = false;
            }

            function showConnected(platform) {
                chooser.hidden = true;
                while (connectedCard.firstChild) connectedCard.removeChild(connectedCard.firstChild);

                var line = document.createElement('p');
                line.className = 'odview-connected-card__line';
                line.textContent = '✅ این سایت هم‌اکنون به ' + (names[platform] || 'بازو') + ' متصل است.';
                connectedCard.appendChild(line);

                var reconnect = document.createElement('button');
                reconnect.type = 'button';
                reconnect.className = 'button button-secondary';
                reconnect.textContent = 'اتصال به پیام‌رسان دیگر یا اتصال مجدد';
                reconnect.addEventListener('click', showChooser);
                connectedCard.appendChild(reconnect);

                connectedCard.hidden = false;
            }

            // Chooser starts hidden and only appears once we know the real
            // state, so a page load never flashes "choose a bot" in front of
            // someone who is already connected.
            chooser.hidden = true;

            function checkStatusOnce() {
                var form = new URLSearchParams();
                form.set('action', 'odview_sync_check_connect_status');
                form.set('nonce', app.getAttribute('data-status-nonce'));
                return fetch(app.getAttribute('data-ajax-url'), {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
                    body: form.toString()
                }).then(function (response) {
                    return response.json().catch(function () { return {}; });
                }).then(function (payload) {
                    return payload && payload.success ? payload.data : null;
                }).catch(function () { return null; });
            }

            checkStatusOnce().then(function (data) {
                connectionStatus.hidden = true;
                if (data && data.connected && data.platform) {
                    showConnected(data.platform);
                } else {
                    showChooser();
                }
            });

            // After a link is generated we don't know when the person presses
            // Start on their phone — that happens entirely outside this page.
            // Poll status a few times so a successful pairing is reflected
            // here automatically; stop well before the link itself expires.
            var pollTimer = null;
            function pollUntilConnected(platform, expiresInSeconds) {
                var attempts = 0;
                var maxAttempts = Math.min(Math.ceil((expiresInSeconds || 180) / 4), 45);
                if (pollTimer) window.clearInterval(pollTimer);
                pollTimer = window.setInterval(function () {
                    attempts += 1;
                    checkStatusOnce().then(function (data) {
                        if (data && data.connected) {
                            window.clearInterval(pollTimer);
                            clearResult();
                            status.textContent = '';
                            showConnected(data.platform || platform);
                        } else if (attempts >= maxAttempts) {
                            window.clearInterval(pollTimer);
                        }
                    });
                }, 4000);
            }

            function setBusy(busy) {
                buttons.forEach(function (button) { button.disabled = busy; });
            }

            function clearResult() {
                while (result.firstChild) result.removeChild(result.firstChild);
                result.hidden = true;
            }

            function showResult(data) {
                var card = document.createElement('div');
                card.className = 'odview-pairing-result__card';

                var text = document.createElement('div');
                var title = document.createElement('h3');
                title.textContent = 'لینک ' + (names[data.platform] || 'اتصال') + ' آماده است';
                text.appendChild(title);
                var explanation = document.createElement('p');
                explanation.textContent = 'دکمه را باز کنید یا QR را با گوشی اسکن کنید؛ ربات اتصال را خودکار بررسی می‌کند.';
                text.appendChild(explanation);
                var open = document.createElement('a');
                open.className = 'button button-primary button-hero';
                open.href = data.deep_link;
                open.target = '_blank';
                open.rel = 'noopener noreferrer';
                open.textContent = 'باز کردن ' + (names[data.platform] || 'ربات');
                text.appendChild(open);
                card.appendChild(text);

                var qrBox = document.createElement('div');
                qrBox.className = 'odview-pairing-qr';
                var image = document.createElement('img');
                image.src = data.qr_url;
                image.alt = 'QR اتصال با ' + (names[data.platform] || 'ربات');
                image.referrerPolicy = 'no-referrer';
                qrBox.appendChild(image);
                card.appendChild(qrBox);

                result.appendChild(card);
                result.hidden = false;
            }

            buttons.forEach(function (button) {
                button.addEventListener('click', function () {
                    var platform = button.getAttribute('data-platform');
                    // Open a harmless blank tab synchronously with the click.
                    // Once the server-to-server registration succeeds we can
                    // navigate it to the trusted bot link without a popup
                    // blocker; if a browser blocks it, the rendered fallback
                    // button below remains available.
                    var botWindow = window.open('about:blank', '_blank');
                    if (botWindow) {
                        botWindow.opener = null;
                    }
                    clearResult();
                    setBusy(true);
                    if (pollTimer) { window.clearInterval(pollTimer); pollTimer = null; }
                    status.textContent = 'در حال ساخت لینک امن و بررسی سایت…';

                    var form = new URLSearchParams();
                    form.set('action', 'odview_sync_generate_connect_token');
                    form.set('nonce', app.getAttribute('data-nonce'));
                    form.set('platform', platform);

                    fetch(app.getAttribute('data-ajax-url'), {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
                        body: form.toString()
                    }).then(function (response) {
                        return response.json().catch(function () { return {}; });
                    }).then(function (payload) {
                        if (!payload.success || !payload.data || !payload.data.deep_link || !payload.data.qr_url) {
                            throw new Error((payload.data && payload.data.message) || 'ساخت لینک اتصال ناموفق بود.');
                        }
                        showResult(payload.data);
                        var minutes = Math.ceil((payload.data.expires_in || 0) / 60);
                        if (botWindow && !botWindow.closed) {
                            botWindow.location.replace(payload.data.deep_link);
                            status.textContent = minutes ? 'ربات باز شد؛ لینک تا حدود ' + minutes + ' دقیقه معتبر است.' : 'ربات باز شد.';
                        } else {
                            status.textContent = minutes ? 'لینک امن تا حدود ' + minutes + ' دقیقه معتبر است؛ اگر ربات خودکار باز نشد، دکمهٔ پایین را بزنید.' : 'لینک امن آماده است.';
                        }
                        pollUntilConnected(payload.data.platform, payload.data.expires_in);
                    }).catch(function (error) {
                        if (botWindow && !botWindow.closed) {
                            botWindow.close();
                        }
                        status.textContent = error && error.message ? error.message : 'ساخت لینک اتصال ناموفق بود. دوباره تلاش کنید.';
                    }).finally(function () {
                        setBusy(false);
                    });
                });
            });
        }());
        </script>
        <?php endif; ?>
        <?php
    }
}
