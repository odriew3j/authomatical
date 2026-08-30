<?php

if (!defined('ABSPATH')) exit;

class ODviewSync_Product {

    public static function categories() {
        if (!class_exists('WooCommerce')) {
            return new WP_Error('no_wc', 'WooCommerce not installed', ['status' => 400]);
        }

        $terms = get_terms([
            'taxonomy'   => 'product_cat',
            'hide_empty' => false,
        ]);

        if (is_wp_error($terms)) {
            return $terms;
        }

        $out = [];
        foreach ($terms as $term) {
            $out[] = [
                'id'   => $term->term_id,
                'name' => $term->name,
                'slug' => $term->slug,
            ];
        }
        return $out;
    }

    public static function create($data) {

        if (!class_exists('WC_Product_Simple')) {
            return new WP_Error('no_wc', 'WooCommerce not installed', ['status' => 400]);
        }
        if (empty($data['title'])) {
            return new WP_Error('missing_title', 'title is required', ['status' => 400]);
        }

        $product = new WC_Product_Simple();

        $product->set_name(sanitize_text_field($data['title']));
        $product->set_description(wp_kses_post(isset($data['description']) ? $data['description'] : ''));
        if (!empty($data['description'])) {
            $product->set_short_description(wp_trim_words(wp_strip_all_tags($data['description']), 30));
        }
        $product->set_regular_price((string) (isset($data['price']) ? $data['price'] : 0));

        if (!empty($data['sale_price'])) {
            $product->set_sale_price((string) $data['sale_price']);
        }

        // Stock
        if (isset($data['stock_quantity']) && $data['stock_quantity'] !== '' && $data['stock_quantity'] !== null) {
            $qty = (int) $data['stock_quantity'];
            $product->set_manage_stock(true);
            $product->set_stock_quantity($qty);
            $product->set_stock_status($qty > 0 ? 'instock' : 'outofstock');
        }

        $product->set_status('publish');

        // Force an ASCII/English slug. WordPress accepts Unicode (and can
        // percent-encode non-Latin) permalinks, but product links generated
        // through this connector must never become Persian URLs. Python sends
        // an English, random-suffixed slug first; validate it here as a
        // second, server-side boundary in case another client calls this REST
        // endpoint directly.
        $slug = !empty($data['slug']) ? strtolower(sanitize_title($data['slug'])) : '';
        if (!preg_match('/^[a-z0-9]+(?:-[a-z0-9]+)*$/', $slug)) {
            $slug = 'product-' . substr(str_replace('-', '', wp_generate_uuid4()), 0, 8);
        }

        // WC_Product::save() also protects uniqueness, but resolving it here
        // makes the intended behaviour explicit for simultaneous requests.
        $slug = wp_unique_post_slug($slug, 0, 'publish', 'product', 0);
        $product->set_slug($slug);

        // Save first so we have a product ID (required before setting terms/meta)
        $product_id = $product->save();

        if (!$product_id) {
            return new WP_Error('save_failed', 'Failed to create product', ['status' => 500]);
        }

        // Category (accepts slug or numeric id)
        if (!empty($data['category'])) {
            $cat = $data['category'];
            $term_field = is_numeric($cat) ? 'term_id' : 'slug';
            $result = wp_set_object_terms($product_id, [is_numeric($cat) ? (int) $cat : $cat], 'product_cat');
            if (is_wp_error($result)) {
                // non-fatal: product still gets created, just uncategorized
            }
        }

        // Tags
        if (!empty($data['tags']) && is_array($data['tags'])) {
            $tags = array_filter(array_map('trim', $data['tags']));
            if ($tags) {
                wp_set_object_terms($product_id, $tags, 'product_tag');
            }
        }

        // SEO / brand meta (compatible with Yoast SEO field keys)
        if (!empty($data['brand'])) {
            update_post_meta($product_id, 'brand', sanitize_text_field($data['brand']));
        }
        if (!empty($data['meta_title'])) {
            update_post_meta($product_id, '_yoast_wpseo_title', sanitize_text_field($data['meta_title']));
        }
        if (!empty($data['meta_description'])) {
            update_post_meta($product_id, '_yoast_wpseo_metadesc', sanitize_text_field($data['meta_description']));
        }
        if (!empty($data['keywords'])) {
            update_post_meta($product_id, '_yoast_wpseo_focuskw', sanitize_text_field($data['keywords']));
        }

        // Images: first = featured image, rest = gallery.
        // Expects URLs already on THIS site's media library (e.g. returned
        // by /upload-media), not arbitrary external URLs.
        if (!empty($data['images']) && is_array($data['images'])) {
            $image_ids = [];
            foreach ($data['images'] as $img_url) {
                $attachment_id = attachment_url_to_postid($img_url);
                if ($attachment_id) {
                    $image_ids[] = $attachment_id;
                }
            }
            if ($image_ids) {
                $product = wc_get_product($product_id);
                $product->set_image_id(array_shift($image_ids));
                if ($image_ids) {
                    $product->set_gallery_image_ids($image_ids);
                }
                $product->save();
            }
        }

        return [
            'success'    => true,
            'product_id' => $product_id,
            'url'        => get_permalink($product_id),
            'edit_url'   => admin_url('post.php?post=' . $product_id . '&action=edit'),
        ];
    }

    public static function upload_media($req) {

        if (empty($_FILES['file'])) {
            return new WP_Error('no_file', 'File not provided', ['status' => 400]);
        }

        require_once ABSPATH . 'wp-admin/includes/file.php';
        require_once ABSPATH . 'wp-admin/includes/media.php';
        require_once ABSPATH . 'wp-admin/includes/image.php';

        $file = wp_handle_upload($_FILES['file'], ['test_form' => false]);

        if (isset($file['error'])) {
            return new WP_Error('upload_error', $file['error'], ['status' => 400]);
        }

        $attachment_id = wp_insert_attachment([
            'post_title'     => sanitize_file_name(basename($file['file'])),
            'post_type'      => 'attachment',
            'post_mime_type' => $file['type'],
            'guid'           => $file['url'],
            'post_status'    => 'inherit',
        ], $file['file']);

        if (is_wp_error($attachment_id) || !$attachment_id) {
            return new WP_Error('attach_failed', 'Failed to register attachment', ['status' => 500]);
        }

        wp_update_attachment_metadata(
            $attachment_id,
            wp_generate_attachment_metadata($attachment_id, $file['file'])
        );

        return [
            'success' => true,
            'url'     => $file['url'],
            'id'      => $attachment_id,
        ];
    }
}