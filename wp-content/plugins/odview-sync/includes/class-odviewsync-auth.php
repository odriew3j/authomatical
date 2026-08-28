<?php

if (!defined('ABSPATH')) exit;

class ODviewSync_Auth {

    private $option_key = 'odview_sync_secret';

    public function __construct() {
        add_action('admin_menu', [$this, 'add_menu']);
        add_action('admin_init', [$this, 'generate_secret']);
        add_action('admin_post_odview_sync_regenerate', [$this, 'handle_regenerate']);
    }

    // Generate on first install
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

    public function handle_regenerate() {
        if (!current_user_can('manage_options')) {
            wp_die('دسترسی غیرمجاز');
        }
        check_admin_referer('odview_sync_regenerate');
        update_option($this->option_key, wp_generate_password(40, false));
        wp_safe_redirect(admin_url('admin.php?page=odview-sync&regenerated=1'));
        exit;
    }

    // Admin page showing secret + connection instructions
    public function add_menu() {
        add_menu_page('ODview Sync', 'اتصال به بازو', 'manage_options', 'odview-sync', [$this, 'render_page'], 'dashicons-admin-links');
    }

    public function render_page() {
        if (!current_user_can('manage_options')) return;

        $secret   = get_option($this->option_key);
        $site_url = get_site_url();
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

            <table class="form-table">
                <tr>
                    <th scope="row">۱. آدرس سایت</th>
                    <td><input type="text" value="<?php echo esc_attr($site_url); ?>" style="width:420px" readonly onclick="this.select()"></td>
                </tr>
                <tr>
                    <th scope="row">۲. کلید امنیتی</th>
                    <td>
                        <input type="text" value="<?php echo esc_attr($secret); ?>" style="width:420px;font-family:monospace" readonly onclick="this.select()">
                        <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>" style="display:inline-block;margin-inline-start:8px">
                            <?php wp_nonce_field('odview_sync_regenerate'); ?>
                            <input type="hidden" name="action" value="odview_sync_regenerate">
                            <button type="submit" class="button" onclick="return confirm('با ساخت کلید جدید، اتصال فعلی ربات به این سایت قطع می‌شود و باید دوباره وصل شوید. ادامه می‌دهید؟');">ساخت کلید جدید</button>
                        </form>
                    </td>
                </tr>
            </table>

            <div class="odview-sync-instructions">
                <h2>راهنمای اتصال</h2>
                <ol>
                    <li>در بله یا تلگرام گفتگو با بازوی خودتان را شروع کنید (<code>/start</code>).</li>
                    <li>گزینه‌ی «۱. وارد کردن اطلاعات وردپرس» را انتخاب کنید.</li>
                    <li>آدرس سایت و سپس کلید امنیتی بالا را همان‌طور که هست کپی و برای بازو ارسال کنید.</li>
                    <li>بازو به‌صورت خودکار اتصال را تست می‌کند و در صورت موفقیت، از این پس محصول‌ها و دسته‌بندی‌ها فقط از همین سایت خوانده و نوشته می‌شوند.</li>
                </ol>
                <p><strong>نکته امنیتی:</strong> کلید امنیتی را فقط داخل چت بازوی خودتان بفرستید و در جای دیگری منتشر نکنید. هر کسی این کلید را داشته باشد می‌تواند در سایت شما محصول بسازد.</p>
            </div>
        </div>
        <?php
    }
}
