<?php
/**
 * Plugin Name:       Ivan AI Chatbot
 * Plugin URI:        https://example.com/ivan-ai
 * Description:       Standalone Vanilla JavaScript chat widget with Shadow DOM, secure WordPress REST API adapter, and direct integration to Ivan AI FastAPI backend.
 * Version:           1.0.0
 * Requires at least: 5.6
 * Requires PHP:      7.4
 * Author:            Ivan AI Team
 * Author URI:        https://example.com
 * License:           GPL v2 or later
 * License URI:       https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain:       ivan-ai-chatbot
 * Domain Path:       /languages
 *
 * @package Ivan_AI_Chatbot
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

// Define plugin constants
define( 'IVAN_VERSION', '1.0.0' );
define( 'IVAN_PLUGIN_FILE', __FILE__ );
define( 'IVAN_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'IVAN_PLUGIN_URL', plugin_dir_url( __FILE__ ) );
define( 'IVAN_PLUGIN_BASENAME', plugin_basename( __FILE__ ) );

// Load plugin classes
require_once IVAN_PLUGIN_DIR . 'includes/class-ivan-settings.php';
require_once IVAN_PLUGIN_DIR . 'includes/class-ivan-api.php';
require_once IVAN_PLUGIN_DIR . 'includes/class-ivan-admin.php';

/**
 * Main Ivan Chatbot Plugin Class
 */
class Ivan_Chatbot {

    /**
     * Singleton instance.
     *
     * @var Ivan_Chatbot
     */
    protected static $instance = null;

    /**
     * Settings instance.
     *
     * @var Ivan_Settings
     */
    public $settings;

    /**
     * API Adapter instance.
     *
     * @var Ivan_API
     */
    public $api;

    /**
     * Admin instance.
     *
     * @var Ivan_Admin
     */
    public $admin;

    /**
     * Flag to track if the widget has already been rendered on the current request.
     * Prevents duplicate widget initialization when both shortcode and automatic injection are active.
     *
     * @var bool
     */
    protected static $widget_rendered = false;

    /**
     * Get singleton instance.
     *
     * @return Ivan_Chatbot
     */
    public static function get_instance() {
        if ( null === self::$instance ) {
            self::$instance = new self();
        }
        return self::$instance;
    }

    /**
     * Constructor.
     */
    public function __construct() {
        $this->settings = new Ivan_Settings();
        $this->api      = new Ivan_API();
        $this->admin    = new Ivan_Admin( $this->settings );

        $this->init_hooks();
    }

    /**
     * Initialize WordPress hooks.
     */
    protected function init_hooks() {
        // Activation & Deactivation
        register_activation_hook( IVAN_PLUGIN_FILE, array( __CLASS__, 'activate' ) );
        register_deactivation_hook( IVAN_PLUGIN_FILE, array( __CLASS__, 'deactivate' ) );

        // Admin & Settings
        if ( is_admin() ) {
            $this->admin->init();
            add_filter( 'plugin_action_links_' . IVAN_PLUGIN_BASENAME, array( $this, 'add_action_links' ) );
        }

        // REST API
        add_action( 'rest_api_init', array( $this->api, 'register_routes' ) );

        // Frontend Assets & Widget Injection
        add_action( 'wp_enqueue_scripts', array( $this, 'enqueue_frontend_assets' ) );
        add_action( 'wp_footer', array( $this, 'render_footer_widget' ) );

        // Shortcode Support
        add_shortcode( 'ivan_chat', array( $this, 'render_shortcode' ) );
    }

    /**
     * Plugin activation handler.
     */
    public static function activate() {
        // Set default settings if not already present
        if ( false === get_option( Ivan_Settings::OPTION_NAME ) ) {
            update_option( Ivan_Settings::OPTION_NAME, Ivan_Settings::get_defaults() );
        }
    }

    /**
     * Plugin deactivation handler.
     */
    public static function deactivate() {
        // Clear any rate-limit transients
        global $wpdb;
        $wpdb->query( "DELETE FROM {$wpdb->options} WHERE option_name LIKE '_transient_ivan_rl_%' OR option_name LIKE '_transient_timeout_ivan_rl_%'" );
    }

    /**
     * Add settings link to the Plugins page entry.
     *
     * @param array $links Existing action links.
     * @return array
     */
    public function add_action_links( $links ) {
        $settings_url = admin_url( 'admin.php?page=ivan-ai-settings' );
        $settings_link = '<a href="' . esc_url( $settings_url ) . '">' . esc_html__( 'Settings', 'ivan-ai-chatbot' ) . '</a>';
        array_unshift( $links, $settings_link );
        return $links;
    }

    /**
     * Enqueue frontend scripts and styles.
     */
    public function enqueue_frontend_assets() {
        // Do not load assets if the chatbot is disabled
        if ( ! Ivan_Settings::get_option( 'enabled', 1 ) ) {
            return;
        }

        wp_enqueue_style(
            'ivan-widget-style',
            IVAN_PLUGIN_URL . 'assets/css/ivan-widget.css',
            array(),
            IVAN_VERSION
        );

        wp_enqueue_script(
            'ivan-widget-script',
            IVAN_PLUGIN_URL . 'assets/js/ivan-widget.js',
            array(),
            IVAN_VERSION,
            true // Load in footer
        );

        // Localize safe settings for frontend web component
        $safe_settings = array(
            'apiUrl'          => esc_url_raw( rest_url( Ivan_API::REST_NAMESPACE . Ivan_API::REST_ROUTE ) ),
            'nonce'           => wp_create_nonce( 'wp_rest' ),
            'primaryColor'    => sanitize_hex_color( Ivan_Settings::get_option( 'primary_color', '#031b45' ) ),
            'secondaryColor'  => sanitize_hex_color( Ivan_Settings::get_option( 'secondary_color', '#f1f5f9' ) ),
            'widgetTitle'     => sanitize_text_field( Ivan_Settings::get_option( 'widget_title', 'Ivan AI' ) ),
            'widgetSubtitle'  => sanitize_text_field( Ivan_Settings::get_option( 'widget_subtitle', 'Online Assistant' ) ),
            'welcomeMessage'  => sanitize_textarea_field( Ivan_Settings::get_option( 'welcome_message', "Hi there! I'm Ivan, your AI assistant. How can I help you today?" ) ),
            'position'        => sanitize_key( Ivan_Settings::get_option( 'position', 'bottom-right' ) ),
            'stream'          => (bool) Ivan_Settings::get_option( 'stream', 1 ),
            'botAvatar'       => esc_url_raw( Ivan_Settings::get_option( 'avatar_url', '' ) ),
        );

        wp_localize_script( 'ivan-widget-script', 'ivanChatSettings', $safe_settings );
    }

    /**
     * Automatically inject the floating widget into wp_footer.
     */
    public function render_footer_widget() {
        // Verify enabled
        if ( ! Ivan_Settings::get_option( 'enabled', 1 ) ) {
            return;
        }

        // Verify display mode allows automatic floating injection
        $display_mode = Ivan_Settings::get_option( 'display_mode', 'floating' );
        if ( 'shortcode' === $display_mode ) {
            return; // Shortcode only mode
        }

        // Prevent duplicate injection if widget was already rendered by shortcode
        if ( self::$widget_rendered ) {
            return;
        }

        self::$widget_rendered = true;

        $title    = esc_attr( Ivan_Settings::get_option( 'widget_title', 'Ivan AI' ) );
        $subtitle = esc_attr( Ivan_Settings::get_option( 'widget_subtitle', 'Online Assistant' ) );
        $color    = esc_attr( Ivan_Settings::get_option( 'primary_color', '#031b45' ) );
        $welcome  = esc_attr( Ivan_Settings::get_option( 'welcome_message', "Hi there! I'm Ivan, your AI assistant. How can I help you today?" ) );
        $position = esc_attr( Ivan_Settings::get_option( 'position', 'bottom-right' ) );
        $stream   = Ivan_Settings::get_option( 'stream', 1 ) ? 'true' : 'false';
        $avatar   = esc_url( Ivan_Settings::get_option( 'avatar_url', '' ) );

        echo sprintf(
            '<ivan-chat-widget widget-title="%s" widget-subtitle="%s" primary-color="%s" welcome-message="%s" position="%s" stream="%s" bot-avatar="%s"></ivan-chat-widget>',
            $title,
            $subtitle,
            $color,
            $welcome,
            $position,
            $stream,
            $avatar
        );
    }

    /**
     * Render shortcode [ivan_chat].
     *
     * @param array $atts Shortcode attributes.
     * @return string
     */
    public function render_shortcode( $atts ) {
        // If disabled, return nothing
        if ( ! Ivan_Settings::get_option( 'enabled', 1 ) ) {
            return '';
        }

        // Prevent duplicate rendering
        if ( self::$widget_rendered ) {
            return '<!-- Ivan AI Chatbot already initialized on this page -->';
        }

        $parsed_atts = shortcode_atts(
            array(
                'title'    => Ivan_Settings::get_option( 'widget_title', 'Ivan AI' ),
                'subtitle' => Ivan_Settings::get_option( 'widget_subtitle', 'Online Assistant' ),
                'color'    => Ivan_Settings::get_option( 'primary_color', '#031b45' ),
                'position' => Ivan_Settings::get_option( 'position', 'bottom-right' ),
                'welcome'  => Ivan_Settings::get_option( 'welcome_message', "Hi there! I'm Ivan, your AI assistant. How can I help you today?" ),
                'stream'   => Ivan_Settings::get_option( 'stream', 1 ) ? 'true' : 'false',
                'avatar'   => Ivan_Settings::get_option( 'avatar_url', '' ),
                'open'     => false,
            ),
            $atts,
            'ivan_chat'
        );

        self::$widget_rendered = true;

        $open_attr = ( ! empty( $parsed_atts['open'] ) && 'false' !== $parsed_atts['open'] ) ? ' open' : '';

        return sprintf(
            '<ivan-chat-widget widget-title="%s" widget-subtitle="%s" primary-color="%s" welcome-message="%s" position="%s" stream="%s" bot-avatar="%s"%s></ivan-chat-widget>',
            esc_attr( $parsed_atts['title'] ),
            esc_attr( $parsed_atts['subtitle'] ),
            esc_attr( $parsed_atts['color'] ),
            esc_attr( $parsed_atts['welcome'] ),
            esc_attr( $parsed_atts['position'] ),
            esc_attr( $parsed_atts['stream'] ),
            esc_url( $parsed_atts['avatar'] ),
            $open_attr
        );
    }
}

// Bootstrap plugin
function ivan_chatbot_init() {
    return Ivan_Chatbot::get_instance();
}
add_action( 'plugins_loaded', 'ivan_chatbot_init' );

