<?php
/**
 * Plugin Name: ODview Auto Product Sync
 * Description: اتصال وردپرس / ووکامرس با سرور اختصاصی و ربات تلگرام برای ساخت محصول و مقاله.
 * Version: 1.0.0
 * Author: Mohammad Mousavi
 */

if (!defined('ABSPATH')) exit;

// Auto Load Classes
spl_autoload_register(function ($class) {
    if (strpos($class, 'ODviewSync') !== false) {
        $path = plugin_dir_path(__FILE__) . 'includes/' . strtolower(str_replace('_', '-', $class)) . '.php';
        if (file_exists($path)) require_once $path;
    }
});

// Init
add_action('plugins_loaded', function () {
    new ODviewSync_Auth();
    new ODviewSync_API();
    new ODviewSync_Product();
});
