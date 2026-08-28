<?php

class ODviewSync_API {

    public function __construct() {
        add_action('rest_api_init', [$this, 'routes']);
    }

    public function routes() {

        register_rest_route('odview/v1', '/create-product', [
            'methods'  => 'POST',
            'callback' => [$this, 'create_product'],
            'permission_callback' => ['ArmanSync_Auth', 'validate']
        ]);

        register_rest_route('odview/v1', '/upload-media', [
            'methods'  => 'POST',
            'callback' => [$this, 'upload_media'],
            'permission_callback' => ['ArmanSync_Auth', 'validate']
        ]);
    }

    public function create_product(WP_REST_Request $req) {
        return ArmanSync_Product::create($req->get_json_params());
    }

    public function upload_media(WP_REST_Request $req) {
        return ArmanSync_Product::upload_media($req);
    }
}
