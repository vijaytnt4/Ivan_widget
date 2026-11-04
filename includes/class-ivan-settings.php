<?php
/**
 * Ivan AI Chatbot Settings Manager
 *
 * Handles options definition, defaults, retrieval, and sanitization using the WordPress Settings API.
 *
 * @package Ivan_AI_Chatbot
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class Ivan_Settings {

    /**
     * Option name in wp_options table.
     */
    const OPTION_NAME = 'ivan_chat_settings';

    /**
     * Settings group for register_setting.
     */
    const SETTINGS_GROUP = 'ivan_chat_settings_group';

    /**
     * Default configuration options.
     *
     * @return array
     */
    public static function get_defaults() {
        return array(
            'enabled'         => 1,
            'api_url'         => 'http://localhost:8000',
            'api_key'         => '',
            'widget_title'    => 'Ivan AI',
            'widget_subtitle' => 'Online Assistant',
            'welcome_message' => "Hi there! I'm Ivan, your AI assistant. How can I help you today?",
            'primary_color'   => '#031b45',
            'secondary_color' => '#f1f5f9',
            'position'        => 'bottom-right',
            'display_mode'    => 'floating', // 'floating', 'shortcode', 'both'
            'stream'          => 1,
            'avatar_url'      => '',
            'avatar_id'       => 0,
        );
    }

    /**
     * Get all settings merged with defaults.
     *
     * @return array
     */
    public static function get_settings() {
        $saved = get_option( self::OPTION_NAME, array() );
        if ( ! is_array( $saved ) ) {
            $saved = array();
        }
        return wp_parse_args( $saved, self::get_defaults() );
    }

    /**
     * Get a single setting value.
     *
     * @param string $key Setting key.
     * @param mixed  $default Optional fallback default.
     * @return mixed
     */
    public static function get_option( $key, $default = null ) {
        $settings = self::get_settings();
        if ( array_key_exists( $key, $settings ) ) {
            return $settings[ $key ];
        }
        return $default;
    }

    /**
     * Register settings with the WordPress Settings API.
     */
    public function register_settings() {
        register_setting(
            self::SETTINGS_GROUP,
            self::OPTION_NAME,
            array(
                'type'              => 'array',
                'description'       => __( 'Ivan AI Chatbot Settings', 'ivan-ai-chatbot' ),
                'sanitize_callback' => array( $this, 'sanitize_settings' ),
                'show_in_rest'      => false, // Kept strictly private, never exposed to public REST schema
                'default'           => self::get_defaults(),
            )
        );
    }

    /**
     * Sanitize and validate all settings before saving to the database.
     *
     * @param array $input Raw user input.
     * @return array Sanitized array.
     */
    public function sanitize_settings( $input ) {
        $existing = self::get_settings();
        $output   = array();

        // 1. Enable / Disable
        $output['enabled'] = ! empty( $input['enabled'] ) ? 1 : 0;

        // 2. Backend API URL
        if ( ! empty( $input['api_url'] ) ) {
            $url = trim( $input['api_url'] );
            $sanitized_url = esc_url_raw( $url );
            $output['api_url'] = rtrim( $sanitized_url, '/' );
        } else {
            $output['api_url'] = '';
        }

        // 3. Backend API Key - Never wipe existing key if user leaves field empty on save
        if ( isset( $input['api_key'] ) ) {
            $key = trim( $input['api_key'] );
            if ( '' === $key ) {
                // If user submitted empty string, check if it was intentionally cleared
                // or if it was masked/placeholder
                $output['api_key'] = ( isset( $input['api_key_cleared'] ) && '1' === $input['api_key_cleared'] )
                    ? ''
                    : ( isset( $existing['api_key'] ) ? $existing['api_key'] : '' );
            } else {
                $output['api_key'] = sanitize_text_field( $key );
            }
        } else {
            $output['api_key'] = isset( $existing['api_key'] ) ? $existing['api_key'] : '';
        }

        // 4. Widget Title & Subtitle
        $output['widget_title'] = ! empty( $input['widget_title'] )
            ? sanitize_text_field( $input['widget_title'] )
            : 'Ivan AI';

        $output['widget_subtitle'] = ! empty( $input['widget_subtitle'] )
            ? sanitize_text_field( $input['widget_subtitle'] )
            : 'Online Assistant';

        // 5. Welcome Message
        $output['welcome_message'] = ! empty( $input['welcome_message'] )
            ? sanitize_textarea_field( $input['welcome_message'] )
            : "Hi there! I'm Ivan, your AI assistant. How can I help you today?";

        // 6. Colors (Hex format validation)
        $primary = ! empty( $input['primary_color'] ) ? sanitize_hex_color( $input['primary_color'] ) : '';
        $output['primary_color'] = $primary ? $primary : '#031b45';

        $secondary = ! empty( $input['secondary_color'] ) ? sanitize_hex_color( $input['secondary_color'] ) : '';
        $output['secondary_color'] = $secondary ? $secondary : '#f1f5f9';

        // 7. Position ('bottom-right' or 'bottom-left')
        $position = ! empty( $input['position'] ) ? sanitize_key( $input['position'] ) : 'bottom-right';
        $output['position'] = in_array( $position, array( 'bottom-right', 'bottom-left' ), true ) ? $position : 'bottom-right';

        // 8. Display Mode ('floating', 'shortcode', 'both')
        $mode = ! empty( $input['display_mode'] ) ? sanitize_key( $input['display_mode'] ) : 'floating';
        $output['display_mode'] = in_array( $mode, array( 'floating', 'shortcode', 'both' ), true ) ? $mode : 'floating';

        // 9. Streaming Enabled
        $output['stream'] = ! empty( $input['stream'] ) ? 1 : 0;

        // 10. Avatar / Logo Image
        $output['avatar_id'] = ! empty( $input['avatar_id'] ) ? absint( $input['avatar_id'] ) : 0;

        if ( ! empty( $input['avatar_url'] ) ) {
            $raw_url = trim( $input['avatar_url'] );
            $clean_url = esc_url_raw( $raw_url );
            if ( filter_var( $clean_url, FILTER_VALIDATE_URL ) ) {
                $output['avatar_url'] = $clean_url;
            } else {
                $output['avatar_url'] = '';
                $output['avatar_id']  = 0;
            }
        } elseif ( $output['avatar_id'] > 0 && function_exists( 'wp_get_attachment_image_url' ) ) {
            $attachment_url = wp_get_attachment_image_url( $output['avatar_id'], 'full' );
            $output['avatar_url'] = $attachment_url ? esc_url_raw( $attachment_url ) : '';
        } else {
            $output['avatar_url'] = '';
            $output['avatar_id']  = 0;
        }

        return $output;
    }
}

