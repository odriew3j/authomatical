<?php

if (!defined('ABSPATH')) exit;

class ODviewSync_API {

    public function __construct() {
        add_action('rest_api_init', [$this, 'routes']);
    }

    public function routes() {

        register_rest_route('odview/v1', '/ping', [
            'methods'  => 'GET',
            'callback' => [$this, 'ping'],
            'permission_callback' => ['ODviewSync_Auth', 'validate'],
        ]);

        register_rest_route('odview/v1', '/categories', [
            'methods'  => 'GET',
            'callback' => [$this, 'categories'],
            'permission_callback' => ['ODviewSync_Auth', 'validate'],
        ]);

        register_rest_route('odview/v1', '/create-product', [
            'methods'  => 'POST',
            'callback' => [$this, 'create_product'],
            'permission_callback' => ['ODviewSync_Auth', 'validate'],
        ]);

        register_rest_route('odview/v1', '/upload-media', [
            'methods'  => 'POST',
            'callback' => [$this, 'upload_media'],
            'permission_callback' => ['ODviewSync_Auth', 'validate'],
        ]);

        register_rest_route('odview/v1', '/create-post', [
            'methods'  => 'POST',
            'callback' => [$this, 'create_post'],
            'permission_callback' => ['ODviewSync_Auth', 'validate'],
        ]);
    }

    public function create_post(WP_REST_Request $req) {
        return ODviewSync_Article::create($req->get_json_params());
    }

    public function ping(WP_REST_Request $req) {
        return [
            'success'     => true,
            'site_url'    => get_site_url(),
            'site_name'   => get_bloginfo('name'),
            'wc_active'   => class_exists('WooCommerce'),
            'plugin_version' => defined('ODVIEW_SYNC_VERSION') ? ODVIEW_SYNC_VERSION : null,
        ];
    }

    public function categories(WP_REST_Request $req) {
        return ODviewSync_Product::categories();
    }

    public function create_product(WP_REST_Request $req) {
        return ODviewSync_Product::create($req->get_json_params());
    }

    public function upload_media(WP_REST_Request $req) {
        return ODviewSync_Product::upload_media($req);
    }
}