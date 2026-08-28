<?php

class ODviewSync_Product {

    public static function create($data) {

        if (!class_exists('WC_Product')) {
            return new WP_Error('no_wc', 'WooCommerce not installed');
        }

        $product = new WC_Product();

        $product->set_name($data['title']);
        $product->set_description($data['description']);
        $product->set_regular_price($data['price']);
        $product->set_sale_price($data['sale_price']);
        $product->set_stock_quantity($data['stock_quantity']);

        // Category
        if (!empty($data['category'])) {
            wp_set_object_terms($product->get_id(), $data['category'], 'product_cat');
        }

        $product_id = $product->save();

        // Attach Images
        if (!empty($data['images'])) {
            $image_ids = [];
            foreach ($data['images'] as $img) {
                $id = attachment_url_to_postid($img);
                if ($id) $image_ids[] = $id;
            }
            $product->set_gallery_image_ids($image_ids);
            $product->save();
        }

        return [
            "success" => true,
            "product_id" => $product_id
        ];
    }

    public static function upload_media($req) {

        if (!isset($_FILES['file'])) {
            return new WP_Error('no_file', 'File not provided');
        }

        $file = wp_handle_upload($_FILES['file'], ['test_form' => false]);

        if (isset($file['error'])) return new WP_Error('upload_error', $file['error']);

        $attachment_id = wp_insert_attachment([
            'post_title' => basename($file['file']),
            'post_type'  => 'attachment',
            'post_mime_type' => $file['type'],
            'guid' => $file['url']
        ], $file['file']);

        require_once ABSPATH . 'wp-admin/includes/image.php';
        wp_update_attachment_metadata(
            $attachment_id,
            wp_generate_attachment_metadata($attachment_id, $file['file'])
        );

        return [
            "success" => true,
            "url" => $file['url'],
            "id" => $attachment_id
        ];
    }
}
