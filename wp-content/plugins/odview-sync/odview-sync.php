<?php
/**
 * Plugin Name: ODview Sync — Bale & Telegram Bot Connector
 * Description: اتصال امن سایت وردپرس/ووکامرس به بازوی بله و بات تلگرام برای ساخت محصول، آپلود تصویر و مدیریت دسته‌بندی از طریق چت.
 * Version: 1.2.0
 * Author: Mohammad Mousavi
 */

if (!defined('ABSPATH')) exit;

define('ODVIEW_SYNC_VERSION', '1.2.0');
define('ODVIEW_SYNC_PLUGIN_FILE', __FILE__);

// The pairing backend is a single shared SaaS service; a site owner never
// needs to know or enter its address. Set the production value here before
// shipping a release build. A developer can point a local/staging site at a
// tunnel instead — without touching this file or building a separate
// plugin — by adding one line to that site's wp-config.php (evaluated
// before plugins load), e.g.:
//   define('ODVIEW_SYNC_BACKEND_URL', 'https://dev-tunnel.example.com');
if (!defined('ODVIEW_SYNC_BACKEND_URL')) {
    define('ODVIEW_SYNC_BACKEND_URL', 'https://api.odview.ir');
}

// Auto Load Classes
// File naming convention: class-odviewsync-{name}.php  (e.g. ODviewSync_Auth -> class-odviewsync-auth.php)
spl_autoload_register(function ($class) {
    if (strpos($class, 'ODviewSync_') !== 0) {
        return;
    }
    $suffix = strtolower(str_replace('_', '-', substr($class, strlen('ODviewSync'))));
    $path = plugin_dir_path(__FILE__) . 'includes/class-odviewsync' . $suffix . '.php';
    if (file_exists($path)) {
        require_once $path;
    }
});

// Init
add_action('plugins_loaded', function () {
    new ODviewSync_Auth();
    new ODviewSync_API();
});
