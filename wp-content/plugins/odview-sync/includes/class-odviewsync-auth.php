<?php

if (!defined('ABSPATH')) exit;

class ODviewSync_Auth {

    private $option_key = 'odview_sync_secret';

    public function __construct() {
        add_action('admin_menu', [$this, 'add_menu']);
        add_action('admin_init', [$this, 'generate_secret']);
    }

    // Generate on first install
    public function generate_secret() {
        if (!get_option($this->option_key)) {
            $secret = wp_generate_password(32, false);
            update_option($this->option_key, $secret);
        }
    }

    public static function validate($request) {
        $secret = get_option('odview_sync_secret');
        $header = $request->get_header('x-odview-secret');

        if (!$header || $header !== $secret) {
            return new WP_Error('forbidden', 'Invalid Secret Key', ['status' => 403]);
        }

        return true;
    }

    // Admin page showing secret
    public function add_menu() {
        add_menu_page('ODview Sync', 'ODview Sync', 'manage_options', 'odview-sync', function () {
            $secret = get_option('odview_sync_secret');
            echo "<h2>ODview Sync Config</h2>";
            echo "<p><strong>Secret Key:</strong></p>";
            echo "<input type='text' value='$secret' style='width:400px' readonly>";
        });
    }
}
