<?php
/**
 * Ivan AI Chatbot Uninstall Script
 *
 * Runs automatically when the plugin is deleted via the WordPress Admin Plugins screen.
 * Cleans up options, transients, and metadata to maintain a clean database.
 *
 * @package Ivan_AI_Chatbot
 */

if ( ! defined( 'WP_UNINSTALL_PLUGIN' ) ) {
    exit;
}

// Delete plugin options
delete_option( 'ivan_chat_settings' );
delete_option( 'ivan_api_url' );
delete_option( 'ivan_api_key' );

// Delete all rate-limiting transients
global $wpdb;
$wpdb->query( "DELETE FROM {$wpdb->options} WHERE option_name LIKE '_transient_ivan_rl_%' OR option_name LIKE '_transient_timeout_ivan_rl_%'" );

