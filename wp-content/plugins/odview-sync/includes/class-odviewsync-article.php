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

        // Slug: force an ASCII/English one when supplied, same reasoning
        // as products — a Persian post_title should not automatically
        // become a Persian permalink slug.
        if (!empty($data['slug'])) {
            $slug = sanitize_title($data['slug']);
            if ($slug !== '') {
                $post_args['post_name'] = $slug;
            }
        }

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