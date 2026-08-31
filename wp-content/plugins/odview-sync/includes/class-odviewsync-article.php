<?php

if (!defined('ABSPATH')) exit;

class ODviewSync_Article {

    public static function create($data) {

        if (empty($data['title'])) {
            return new WP_Error('missing_title', 'title is required', ['status' => 400]);
        }
        if (empty($data['content'])) {
            return new WP_Error('missing_content', 'content is required', ['status' => 400]);
        }

        $post_args = [
            'post_title'   => sanitize_text_field($data['title']),
            'post_content' => wp_kses_post($data['content']),
            'post_status'  => !empty($data['status']) ? sanitize_key($data['status']) : 'publish',
            'post_type'    => 'post',
        ];

        // Force an ASCII/English slug — identical reasoning and logic to
        // products (see class-odviewsync-product.php): a Persian
        // post_title must never automatically become a Persian permalink.
        // Python sends an English, random-suffixed slug first; this is
        // the server-side boundary in case another client calls this REST
        // endpoint directly, or the AI slug wasn't actually ASCII.
        $slug = !empty($data['slug']) ? strtolower(sanitize_title($data['slug'])) : '';
        if (!preg_match('/^[a-z0-9]+(?:-[a-z0-9]+)*$/', $slug)) {
            $slug = 'article-' . substr(str_replace('-', '', wp_generate_uuid4()), 0, 8);
        }
        $post_args['post_name'] = wp_unique_post_slug($slug, 0, $post_args['post_status'], 'post', 0);

        $post_id = wp_insert_post($post_args, true);

        if (is_wp_error($post_id)) {
            return $post_id;
        }

        // Category (accepts slug or numeric id) — standard post categories
        if (!empty($data['category'])) {
            $cat = $data['category'];
            if (is_numeric($cat)) {
                wp_set_post_categories($post_id, [(int) $cat]);
            } else {
                $term = get_term_by('slug', $cat, 'category');
                if ($term) {
                    wp_set_post_categories($post_id, [$term->term_id]);
                }
            }
        }

        // Tags
        if (!empty($data['tags']) && is_array($data['tags'])) {
            $tags = array_filter(array_map('trim', $data['tags']));
            if ($tags) {
                wp_set_post_tags($post_id, $tags);
            }
        }

        // SEO meta (Yoast-compatible keys, same as products)
        if (!empty($data['meta_title'])) {
            update_post_meta($post_id, '_yoast_wpseo_title', sanitize_text_field($data['meta_title']));
        }
        if (!empty($data['meta_description'])) {
            update_post_meta($post_id, '_yoast_wpseo_metadesc', sanitize_text_field($data['meta_description']));
        }

        // Featured image: expects a URL already on THIS site's media
        // library (e.g. returned by /upload-media).
        if (!empty($data['featured_image'])) {
            $attachment_id = attachment_url_to_postid($data['featured_image']);
            if ($attachment_id) {
                set_post_thumbnail($post_id, $attachment_id);
            }
        }

        return [
            'success'  => true,
            'post_id'  => $post_id,
            'url'      => get_permalink($post_id),
            'edit_url' => admin_url('post.php?post=' . $post_id . '&action=edit'),
        ];
    }
}