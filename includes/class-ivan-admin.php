<?php
/**
 * Ivan AI Chatbot Administration Page
 *
 * Manages WordPress admin menu, settings UI, color pickers, and documentation cards.
 *
 * @package Ivan_AI_Chatbot
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class Ivan_Admin {

    /**
     * Settings instance.
     *
     * @var Ivan_Settings
     */
    protected $settings;

    /**
     * Menu slug.
     */
    const MENU_SLUG = 'ivan-ai-settings';

    /**
     * Constructor.
     *
     * @param Ivan_Settings $settings Settings instance.
     */
    public function __construct( Ivan_Settings $settings ) {
        $this->settings = $settings;
    }

    /**
     * Initialize admin hooks.
     */
    public function init() {
        add_action( 'admin_menu', array( $this, 'add_admin_menu' ) );
        add_action( 'admin_init', array( $this->settings, 'register_settings' ) );
        add_action( 'admin_enqueue_scripts', array( $this, 'enqueue_admin_assets' ) );
    }

    /**
     * Add admin menu item.
     */
    public function add_admin_menu() {
        add_menu_page(
            __( 'Ivan AI Settings', 'ivan-ai-chatbot' ),
            __( 'Ivan AI', 'ivan-ai-chatbot' ),
            'manage_options',
            self::MENU_SLUG,
            array( $this, 'render_settings_page' ),
            'dashicons-format-chat',
            75
        );
    }

    /**
     * Enqueue color picker and admin styling.
     *
     * @param string $hook Current admin page hook.
     */
    public function enqueue_admin_assets( $hook ) {
        if ( strpos( $hook, self::MENU_SLUG ) === false ) {
            return;
        }

        wp_enqueue_media();
        wp_enqueue_style( 'wp-color-picker' );
        wp_enqueue_script( 'wp-color-picker' );

        // Admin enhancement script
        $inline_js = "
            jQuery(document).ready(function($) {
                $('.ivan-color-picker').wpColorPicker();

                // Toggle API Key visibility
                $('#toggleApiKeyBtn').on('click', function(e) {
                    e.preventDefault();
                    var input = $('#ivan_api_key');
                    var type = input.attr('type') === 'password' ? 'text' : 'password';
                    input.attr('type', type);
                    $(this).text(type === 'password' ? 'Show' : 'Hide');
                });

                // Media Library Uploader for Chatbot Avatar
                var avatarFrame;
                $('#ivan_upload_avatar_btn').on('click', function(e) {
                    e.preventDefault();

                    if (avatarFrame) {
                        avatarFrame.open();
                        return;
                    }

                    avatarFrame = wp.media({
                        title: '" . esc_js( __( 'Select or Upload Chatbot Avatar', 'ivan-ai-chatbot' ) ) . "',
                        button: {
                            text: '" . esc_js( __( 'Use this image', 'ivan-ai-chatbot' ) ) . "'
                        },
                        library: {
                            type: 'image'
                        },
                        multiple: false
                    });

                    avatarFrame.on('select', function() {
                        var attachment = avatarFrame.state().get('selection').first().toJSON();
                        var fullUrl = attachment.url;
                        $('#ivan_avatar_url').val(fullUrl);
                        $('#ivan_avatar_id').val(attachment.id);
                        $('#ivan_avatar_preview').html('<img src=\"' + fullUrl + '\" style=\"width:100%;height:100%;object-fit:cover;object-position:center top;\" alt=\"Avatar Preview\" />');
                        $('#ivan_remove_avatar_btn').show();
                    });

                    avatarFrame.open();
                });

                // Remove Avatar
                $('#ivan_remove_avatar_btn').on('click', function(e) {
                    e.preventDefault();
                    $('#ivan_avatar_url').val('');
                    $('#ivan_avatar_id').val('0');
                    $('#ivan_avatar_preview').html('<span class=\"dashicons dashicons-admin-users\" style=\"font-size:32px;width:32px;height:32px;color:#64748b;\"></span>');
                    $(this).hide();
                });
            });
        ";
        wp_add_inline_script( 'wp-color-picker', $inline_js );
    }

    /**
     * Render the admin settings page.
     */
    public function render_settings_page() {
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_die( esc_html__( 'You do not have sufficient permissions to access this page.', 'ivan-ai-chatbot' ) );
        }

        $settings = Ivan_Settings::get_settings();
        ?>
        <div class="wrap ivan-admin-wrap">
            <h1><?php echo esc_html__( 'Ivan AI Chatbot Settings', 'ivan-ai-chatbot' ); ?></h1>
            <p class="description">
                <?php echo esc_html__( 'Configure your AI assistant, connect your Python/FastAPI backend, and customize the widget appearance.', 'ivan-ai-chatbot' ); ?>
            </p>

            <?php settings_errors(); ?>

            <div style="display: flex; gap: 24px; flex-wrap: wrap; margin-top: 20px;">
                <!-- Main Form Column -->
                <div style="flex: 2; min-width: 320px;">
                    <form method="post" action="options.php" style="background: #fff; padding: 24px; border: 1px solid #ccd0d4; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                        <?php
                        settings_fields( Ivan_Settings::SETTINGS_GROUP );
                        ?>

                        <!-- Section: Status & Display -->
                        <h2><?php echo esc_html__( 'General & Display', 'ivan-ai-chatbot' ); ?></h2>
                        <table class="form-table" role="presentation">
                            <tr>
                                <th scope="row"><?php echo esc_html__( 'Enable Chatbot', 'ivan-ai-chatbot' ); ?></th>
                                <td>
                                    <label for="ivan_enabled">
                                        <input name="<?php echo esc_attr( Ivan_Settings::OPTION_NAME ); ?>[enabled]" type="checkbox" id="ivan_enabled" value="1" <?php checked( 1, $settings['enabled'] ); ?> />
                                        <?php echo esc_html__( 'Enable Ivan AI Chatbot on this website', 'ivan-ai-chatbot' ); ?>
                                    </label>
                                </td>
                            </tr>
                            <tr>
                                <th scope="row"><label for="ivan_display_mode"><?php echo esc_html__( 'Display Mode', 'ivan-ai-chatbot' ); ?></label></th>
                                <td>
                                    <select name="<?php echo esc_attr( Ivan_Settings::OPTION_NAME ); ?>[display_mode]" id="ivan_display_mode" class="regular-text">
                                        <option value="floating" <?php selected( 'floating', $settings['display_mode'] ); ?>><?php echo esc_html__( 'Floating Widget (Automatic on all site pages)', 'ivan-ai-chatbot' ); ?></option>
                                        <option value="shortcode" <?php selected( 'shortcode', $settings['display_mode'] ); ?>><?php echo esc_html__( 'Shortcode Only (Manual via [ivan_chat])', 'ivan-ai-chatbot' ); ?></option>
                                        <option value="both" <?php selected( 'both', $settings['display_mode'] ); ?>><?php echo esc_html__( 'Both (Floating Launcher + Shortcode Embeds)', 'ivan-ai-chatbot' ); ?></option>
                                    </select>
                                    <p class="description"><?php echo esc_html__( 'Choose how Ivan appears to site visitors.', 'ivan-ai-chatbot' ); ?></p>
                                </td>
                            </tr>
                            <tr>
                                <th scope="row"><label for="ivan_position"><?php echo esc_html__( 'Widget Position', 'ivan-ai-chatbot' ); ?></label></th>
                                <td>
                                    <select name="<?php echo esc_attr( Ivan_Settings::OPTION_NAME ); ?>[position]" id="ivan_position" class="regular-text">
                                        <option value="bottom-right" <?php selected( 'bottom-right', $settings['position'] ); ?>><?php echo esc_html__( 'Bottom Right (Default)', 'ivan-ai-chatbot' ); ?></option>
                                        <option value="bottom-left" <?php selected( 'bottom-left', $settings['position'] ); ?>><?php echo esc_html__( 'Bottom Left', 'ivan-ai-chatbot' ); ?></option>
                                    </select>
                                </td>
                            </tr>
                        </table>

                        <hr style="margin: 24px 0; border: 0; border-top: 1px solid #e2e8f0;" />

                        <!-- Section: Backend Connection -->
                        <h2><?php echo esc_html__( 'Backend Integration', 'ivan-ai-chatbot' ); ?></h2>
                        <table class="form-table" role="presentation">
                            <tr>
                                <th scope="row"><label for="ivan_api_url"><?php echo esc_html__( 'Backend API URL', 'ivan-ai-chatbot' ); ?> <span class="required" style="color:red;">*</span></label></th>
                                <td>
                                    <input name="<?php echo esc_attr( Ivan_Settings::OPTION_NAME ); ?>[api_url]" type="url" id="ivan_api_url" value="<?php echo esc_attr( $settings['api_url'] ); ?>" class="regular-text" placeholder="http://localhost:8000" required />
                                    <p class="description"><?php echo esc_html__( 'Base URL of your Ivan Python/FastAPI service (e.g. http://localhost:8000 or https://api.yourdomain.com).', 'ivan-ai-chatbot' ); ?></p>
                                </td>
                            </tr>
                            <tr>
                                <th scope="row"><label for="ivan_api_key"><?php echo esc_html__( 'Backend API Key', 'ivan-ai-chatbot' ); ?></label></th>
                                <td>
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <input name="<?php echo esc_attr( Ivan_Settings::OPTION_NAME ); ?>[api_key]" type="password" id="ivan_api_key" value="<?php echo esc_attr( $settings['api_key'] ); ?>" class="regular-text" autocomplete="new-password" placeholder="<?php echo ! empty( $settings['api_key'] ) ? '••••••••••••••••' : 'Enter API Key'; ?>" />
                                        <button type="button" class="button" id="toggleApiKeyBtn"><?php echo esc_html__( 'Show', 'ivan-ai-chatbot' ); ?></button>
                                    </div>
                                    <p class="description"><?php echo esc_html__( 'Passed server-to-server as X-Ivan-API-Key. Kept strictly on the WordPress server; never exposed to browser clients.', 'ivan-ai-chatbot' ); ?></p>
                                </td>
                            </tr>
                            <tr>
                                <th scope="row"><?php echo esc_html__( 'Streaming Responses', 'ivan-ai-chatbot' ); ?></th>
                                <td>
                                    <label for="ivan_stream">
                                        <input name="<?php echo esc_attr( Ivan_Settings::OPTION_NAME ); ?>[stream]" type="checkbox" id="ivan_stream" value="1" <?php checked( 1, $settings['stream'] ); ?> />
                                        <?php echo esc_html__( 'Enable real-time token streaming via Server-Sent Events (SSE)', 'ivan-ai-chatbot' ); ?>
                                    </label>
                                    <p class="description"><?php echo esc_html__( 'Displays responses chunk-by-chunk in real time. If disabled, uses unary JSON.', 'ivan-ai-chatbot' ); ?></p>
                                </td>
                            </tr>
                        </table>

                        <hr style="margin: 24px 0; border: 0; border-top: 1px solid #e2e8f0;" />

                        <!-- Section: Appearance & Branding -->
                        <h2><?php echo esc_html__( 'Customization & Branding', 'ivan-ai-chatbot' ); ?></h2>
                        <table class="form-table" role="presentation">
                            <tr>
                                <th scope="row"><label><?php echo esc_html__( 'Avatar / Logo Image', 'ivan-ai-chatbot' ); ?></label></th>
                                <td>
                                    <div class="ivan-avatar-uploader-wrap" style="display: flex; align-items: center; gap: 16px;">
                                        <div id="ivan_avatar_preview" style="width: 60px; height: 60px; border-radius: 50%; overflow: hidden; background: #e2e8f0; display: flex; align-items: center; justify-content: center; border: 2px solid #cbd5e1; box-shadow: 0 1px 3px rgba(0,0,0,0.1); flex-shrink: 0;">
                                            <?php if ( ! empty( $settings['avatar_url'] ) ) : ?>
                                                <img src="<?php echo esc_url( $settings['avatar_url'] ); ?>" style="width: 100%; height: 100%; object-fit: cover; object-position: center top;" alt="<?php echo esc_attr__( 'Avatar Preview', 'ivan-ai-chatbot' ); ?>" />
                                            <?php else : ?>
                                                <span class="dashicons dashicons-admin-users" style="font-size: 32px; width: 32px; height: 32px; color: #64748b;"></span>
                                            <?php endif; ?>
                                        </div>
                                        <div>
                                            <input type="hidden" name="<?php echo esc_attr( Ivan_Settings::OPTION_NAME ); ?>[avatar_url]" id="ivan_avatar_url" value="<?php echo esc_attr( $settings['avatar_url'] ); ?>" />
                                            <input type="hidden" name="<?php echo esc_attr( Ivan_Settings::OPTION_NAME ); ?>[avatar_id]" id="ivan_avatar_id" value="<?php echo esc_attr( isset( $settings['avatar_id'] ) ? $settings['avatar_id'] : 0 ); ?>" />
                                            <button type="button" class="button button-secondary" id="ivan_upload_avatar_btn">
                                                <?php echo esc_html__( 'Upload / Select Image', 'ivan-ai-chatbot' ); ?>
                                            </button>
                                            <button type="button" class="button button-link-delete" id="ivan_remove_avatar_btn" style="<?php echo empty( $settings['avatar_url'] ) ? 'display: none;' : ''; ?> margin-left: 8px;">
                                                <?php echo esc_html__( 'Remove Avatar', 'ivan-ai-chatbot' ); ?>
                                            </button>
                                            <p class="description" style="margin-top: 6px;">
                                                <?php echo esc_html__( 'Select an image from the WordPress Media Library to use as Ivan\'s human avatar across the launcher, header, and assistant messages.', 'ivan-ai-chatbot' ); ?>
                                            </p>
                                        </div>
                                    </div>
                                </td>
                            </tr>
                            <tr>
                                <th scope="row"><label for="ivan_widget_title"><?php echo esc_html__( 'Widget Title', 'ivan-ai-chatbot' ); ?></label></th>
                                <td>
                                    <input name="<?php echo esc_attr( Ivan_Settings::OPTION_NAME ); ?>[widget_title]" type="text" id="ivan_widget_title" value="<?php echo esc_attr( $settings['widget_title'] ); ?>" class="regular-text" />
                                </td>
                            </tr>
                            <tr>
                                <th scope="row"><label for="ivan_widget_subtitle"><?php echo esc_html__( 'Widget Subtitle', 'ivan-ai-chatbot' ); ?></label></th>
                                <td>
                                    <input name="<?php echo esc_attr( Ivan_Settings::OPTION_NAME ); ?>[widget_subtitle]" type="text" id="ivan_widget_subtitle" value="<?php echo esc_attr( $settings['widget_subtitle'] ); ?>" class="regular-text" />
                                </td>
                            </tr>
                            <tr>
                                <th scope="row"><label for="ivan_welcome_message"><?php echo esc_html__( 'Welcome Message', 'ivan-ai-chatbot' ); ?></label></th>
                                <td>
                                    <textarea name="<?php echo esc_attr( Ivan_Settings::OPTION_NAME ); ?>[welcome_message]" id="ivan_welcome_message" rows="3" class="large-text"><?php echo esc_textarea( $settings['welcome_message'] ); ?></textarea>
                                </td>
                            </tr>
                            <tr>
                                <th scope="row"><label for="ivan_primary_color"><?php echo esc_html__( 'Primary Brand Color', 'ivan-ai-chatbot' ); ?></label></th>
                                <td>
                                    <input name="<?php echo esc_attr( Ivan_Settings::OPTION_NAME ); ?>[primary_color]" type="text" id="ivan_primary_color" value="<?php echo esc_attr( $settings['primary_color'] ); ?>" class="ivan-color-picker" data-default-color="#031b45" />
                                </td>
                            </tr>
                            <tr>
                                <th scope="row"><label for="ivan_secondary_color"><?php echo esc_html__( 'Assistant Bubble Color', 'ivan-ai-chatbot' ); ?></label></th>
                                <td>
                                    <input name="<?php echo esc_attr( Ivan_Settings::OPTION_NAME ); ?>[secondary_color]" type="text" id="ivan_secondary_color" value="<?php echo esc_attr( $settings['secondary_color'] ); ?>" class="ivan-color-picker" data-default-color="#f1f5f9" />
                                </td>
                            </tr>
                        </table>

                        <?php submit_button( __( 'Save Ivan Settings', 'ivan-ai-chatbot' ) ); ?>
                    </form>
                </div>

                <!-- Sidebar Documentation Column -->
                <div style="flex: 1; min-width: 260px; max-width: 380px;">
                    <div style="background: #fff; padding: 20px; border: 1px solid #ccd0d4; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                        <h3 style="margin-top: 0;"><?php echo esc_html__( 'Shortcode Usage', 'ivan-ai-chatbot' ); ?></h3>
                        <p><?php echo esc_html__( 'Embed Ivan on specific pages, posts, or landing pages using:', 'ivan-ai-chatbot' ); ?></p>
                        <code>[ivan_chat]</code>
                        <p style="margin-top: 12px; font-size: 13px; color: #555;">
                            <?php echo esc_html__( 'Optional attributes override:', 'ivan-ai-chatbot' ); ?>
                        </p>
                        <code style="font-size: 11px; display: block; word-break: break-all;">[ivan_chat title="Custom Support" position="bottom-left" color="#10b981"]</code>
                    </div>

                    <div style="background: #fff; padding: 20px; border: 1px solid #ccd0d4; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                        <h3 style="margin-top: 0;"><?php echo esc_html__( 'Integration Diagnostics', 'ivan-ai-chatbot' ); ?></h3>
                        <ul style="list-style: disc; padding-left: 18px; font-size: 13px;">
                            <li><strong><?php echo esc_html__( 'REST Endpoint:', 'ivan-ai-chatbot' ); ?></strong> <code>/wp-json/ivan/v1/chat</code></li>
                            <li><strong><?php echo esc_html__( 'cURL Extension:', 'ivan-ai-chatbot' ); ?></strong> <?php echo function_exists( 'curl_init' ) ? '<span style="color:green;">✓ Enabled</span>' : '<span style="color:red;">✗ Missing</span>'; ?></li>
                            <li><strong><?php echo esc_html__( 'Active Status:', 'ivan-ai-chatbot' ); ?></strong> <?php echo ! empty( $settings['enabled'] ) ? '<span style="color:green;">Active</span>' : '<span style="color:#d97706;">Disabled</span>'; ?></li>
                            <li><strong><?php echo esc_html__( 'API Key Stored:', 'ivan-ai-chatbot' ); ?></strong> <?php echo ! empty( $settings['api_key'] ) ? '<span style="color:green;">Yes (Secure)</span>' : '<span style="color:#6b7280;">None</span>'; ?></li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
        <?php
    }
}

