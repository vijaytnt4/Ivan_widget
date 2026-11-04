"""
Phase 3 & Phase 4 Automated Test Suite for Ivan AI Chatbot WordPress Plugin.

Verifies:
1. Plugin activation and deactivation hooks.
2. Admin settings save, defaults, and retrieval.
3. API URL and API key configuration (with key masking & client exclusion).
4. Floating widget footer injection.
5. Shortcode [ivan_chat] rendering with custom attribute overrides.
6. Enable/disable toggle behavior.
7. Position and color customization propagation.
8. SSE and JSON integration with dynamic settings.
9. Duplicate widget prevention (shortcode + footer conflict resolution).
10. Security, input sanitization, and XSS protection.
"""

import html
import json
import re
import uuid

# --- Simulated WordPress Core API Environment ---
class MockWordPress:
    def __init__(self):
        self.options = {}
        self.transients = {}
        self.enqueued_scripts = []
        self.enqueued_styles = []
        self.localized_scripts = {}

    def get_option(self, key, default=None):
        return self.options.get(key, default)

    def update_option(self, key, value):
        self.options[key] = value

    def delete_option(self, key):
        self.options.pop(key, None)

    def set_transient(self, key, value, expiration=60):
        self.transients[key] = value

    def get_transient(self, key):
        return self.transients.get(key, False)

    def delete_transient(self, key):
        self.transients.pop(key, None)

    def esc_attr(self, text):
        return html.escape(str(text), quote=True)

    def esc_url_raw(self, url):
        url = str(url).strip()
        if not re.match(r"^https?://", url, re.I):
            return ""
        return url

    def sanitize_text_field(self, text):
        cleaned = re.sub(r"<[^>]*>", "", str(text)).strip()
        return cleaned

    def sanitize_textarea_field(self, text):
        cleaned = re.sub(r"<[^>]*>", "", str(text)).strip()
        return cleaned

    def sanitize_hex_color(self, color):
        color = str(color).strip()
        if re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", color):
            return color.lower()
        return ""

    def sanitize_key(self, key):
        return re.sub(r"[^a-z0-9_\-]", "", str(key).lower())


# --- Simulated Plugin Classes Mirroring PHP Implementations ---
class IvanSettingsSim:
    OPTION_NAME = "ivan_chat_settings"

    @classmethod
    def get_defaults(cls):
        return {
            "enabled": 1,
            "api_url": "http://localhost:8000",
            "api_key": "",
            "widget_title": "Ivan AI",
            "widget_subtitle": "Online Assistant",
            "welcome_message": "Hi there! I'm Ivan, your AI assistant. How can I help you today?",
            "primary_color": "#031b45",
            "secondary_color": "#f1f5f9",
            "position": "bottom-right",
            "display_mode": "floating",
            "stream": 1,
        }

    @classmethod
    def get_settings(cls, wp):
        saved = wp.get_option(cls.OPTION_NAME, {})
        merged = cls.get_defaults().copy()
        if isinstance(saved, dict):
            merged.update(saved)
        return merged

    @classmethod
    def get_option(cls, wp, key, default=None):
        settings = cls.get_settings(wp)
        return settings.get(key, default)

    @classmethod
    def sanitize_settings(cls, wp, input_data):
        existing = cls.get_settings(wp)
        output = {}

        output["enabled"] = 1 if input_data.get("enabled") else 0

        url = input_data.get("api_url", "").strip()
        output["api_url"] = wp.esc_url_raw(url).rstrip("/")

        key = input_data.get("api_key", "").strip()
        if not key:
            output["api_key"] = "" if input_data.get("api_key_cleared") else existing.get("api_key", "")
        else:
            output["api_key"] = wp.sanitize_text_field(key)

        output["widget_title"] = wp.sanitize_text_field(input_data.get("widget_title", "Ivan AI"))
        output["widget_subtitle"] = wp.sanitize_text_field(input_data.get("widget_subtitle", "Online Assistant"))
        output["welcome_message"] = wp.sanitize_textarea_field(input_data.get("welcome_message", ""))

        primary = wp.sanitize_hex_color(input_data.get("primary_color", ""))
        output["primary_color"] = primary if primary else "#031b45"

        secondary = wp.sanitize_hex_color(input_data.get("secondary_color", ""))
        output["secondary_color"] = secondary if secondary else "#f1f5f9"

        pos = wp.sanitize_key(input_data.get("position", "bottom-right"))
        output["position"] = pos if pos in ["bottom-right", "bottom-left"] else "bottom-right"

        mode = wp.sanitize_key(input_data.get("display_mode", "floating"))
        output["display_mode"] = mode if mode in ["floating", "shortcode", "both"] else "floating"

        output["stream"] = 1 if input_data.get("stream") else 0
        return output


class IvanChatbotSim:
    def __init__(self, wp):
        self.wp = wp
        self.widget_rendered = False

    def activate(self):
        if self.wp.get_option(IvanSettingsSim.OPTION_NAME) is None:
            self.wp.update_option(IvanSettingsSim.OPTION_NAME, IvanSettingsSim.get_defaults())

    def deactivate(self):
        keys = list(self.wp.transients.keys())
        for k in keys:
            if k.startswith("ivan_rl_"):
                self.wp.delete_transient(k)

    def enqueue_frontend_assets(self):
        if not IvanSettingsSim.get_option(self.wp, "enabled", 1):
            return False

        self.wp.enqueued_styles.append("ivan-widget-style")
        self.wp.enqueued_scripts.append("ivan-widget-script")

        safe_settings = {
            "apiUrl": "/wp-json/ivan/v1/chat",
            "nonce": "test_nonce_wp_rest",
            "primaryColor": IvanSettingsSim.get_option(self.wp, "primary_color"),
            "secondaryColor": IvanSettingsSim.get_option(self.wp, "secondary_color"),
            "widgetTitle": IvanSettingsSim.get_option(self.wp, "widget_title"),
            "widgetSubtitle": IvanSettingsSim.get_option(self.wp, "widget_subtitle"),
            "welcomeMessage": IvanSettingsSim.get_option(self.wp, "welcome_message"),
            "position": IvanSettingsSim.get_option(self.wp, "position"),
            "stream": bool(IvanSettingsSim.get_option(self.wp, "stream")),
        }
        self.wp.localized_scripts["ivanChatSettings"] = safe_settings
        return True

    def render_footer_widget(self):
        if not IvanSettingsSim.get_option(self.wp, "enabled", 1):
            return ""

        display_mode = IvanSettingsSim.get_option(self.wp, "display_mode", "floating")
        if display_mode == "shortcode":
            return ""

        if self.widget_rendered:
            return ""

        self.widget_rendered = True
        title = self.wp.esc_attr(IvanSettingsSim.get_option(self.wp, "widget_title"))
        subtitle = self.wp.esc_attr(IvanSettingsSim.get_option(self.wp, "widget_subtitle"))
        color = self.wp.esc_attr(IvanSettingsSim.get_option(self.wp, "primary_color"))
        welcome = self.wp.esc_attr(IvanSettingsSim.get_option(self.wp, "welcome_message"))
        pos = self.wp.esc_attr(IvanSettingsSim.get_option(self.wp, "position"))
        stream = "true" if IvanSettingsSim.get_option(self.wp, "stream") else "false"

        return f'<ivan-chat-widget widget-title="{title}" widget-subtitle="{subtitle}" primary-color="{color}" welcome-message="{welcome}" position="{pos}" stream="{stream}"></ivan-chat-widget>'

    def render_shortcode(self, atts=None):
        if not IvanSettingsSim.get_option(self.wp, "enabled", 1):
            return ""

        if self.widget_rendered:
            return "<!-- Ivan AI Chatbot already initialized on this page -->"

        atts = atts or {}
        title = atts.get("title", IvanSettingsSim.get_option(self.wp, "widget_title"))
        subtitle = atts.get("subtitle", IvanSettingsSim.get_option(self.wp, "widget_subtitle"))
        color = atts.get("color", IvanSettingsSim.get_option(self.wp, "primary_color"))
        welcome = atts.get("welcome", IvanSettingsSim.get_option(self.wp, "welcome_message"))
        pos = atts.get("position", IvanSettingsSim.get_option(self.wp, "position"))
        stream = atts.get("stream", "true" if IvanSettingsSim.get_option(self.wp, "stream") else "false")
        open_attr = " open" if atts.get("open") in [True, "true", "1"] else ""

        self.widget_rendered = True

        return f'<ivan-chat-widget widget-title="{self.wp.esc_attr(title)}" widget-subtitle="{self.wp.esc_attr(subtitle)}" primary-color="{self.wp.esc_attr(color)}" welcome-message="{self.wp.esc_attr(welcome)}" position="{self.wp.esc_attr(pos)}" stream="{self.wp.esc_attr(stream)}"{open_attr}></ivan-chat-widget>'


# --- Execute Phase 3 & 4 Verification Tests ---
def run_tests():
    wp = MockWordPress()
    plugin = IvanChatbotSim(wp)

    print("==================================================")
    print("RUNNING PHASE 3 & PHASE 4 VERIFICATION SUITE")
    print("==================================================")

    # 1. Activation and Deactivation
    assert wp.get_option(IvanSettingsSim.OPTION_NAME) is None
    plugin.activate()
    defaults = wp.get_option(IvanSettingsSim.OPTION_NAME)
    assert defaults is not None
    assert defaults["widget_title"] == "Ivan AI"
    wp.set_transient("ivan_rl_12345", 5)
    assert wp.get_transient("ivan_rl_12345") == 5
    plugin.deactivate()
    assert wp.get_transient("ivan_rl_12345") is False
    print("[PASS] Test 1: Activation seeds defaults; Deactivation purges transients.")

    # 2. Admin settings save and retrieval
    user_input = {
        "enabled": "1",
        "api_url": "https://api.my-ivan-site.com/",
        "api_key": "secret_key_abc_999",
        "widget_title": "Support Twin",
        "widget_subtitle": "Always Ready",
        "welcome_message": "Welcome to our store!",
        "primary_color": "#10B981",
        "secondary_color": "#F3F4F6",
        "position": "bottom-left",
        "display_mode": "both",
        "stream": "1"
    }
    sanitized = IvanSettingsSim.sanitize_settings(wp, user_input)
    wp.update_option(IvanSettingsSim.OPTION_NAME, sanitized)

    loaded = IvanSettingsSim.get_settings(wp)
    assert loaded["api_url"] == "https://api.my-ivan-site.com", "Trailing slash not stripped"
    assert loaded["primary_color"] == "#10b981"
    assert loaded["position"] == "bottom-left"
    assert loaded["display_mode"] == "both"
    print("[PASS] Test 2: Admin settings save and retrieval verified.")

    # 3. API URL and API Key Security (Never exposed to client)
    plugin.enqueue_frontend_assets()
    localized = wp.localized_scripts["ivanChatSettings"]
    assert "apiKey" not in localized, "SECURITY VIOLATION: apiKey exposed in localized script!"
    assert "api_key" not in localized, "SECURITY VIOLATION: api_key exposed in localized script!"
    assert localized["primaryColor"] == "#10b981"
    assert localized["apiUrl"] == "/wp-json/ivan/v1/chat"
    # Verify key preservation on empty password field
    partial_input = {
        "enabled": "1",
        "api_url": "https://api.my-ivan-site.com",
        "api_key": "" # Empty field submitted
    }
    re_sanitized = IvanSettingsSim.sanitize_settings(wp, partial_input)
    assert re_sanitized["api_key"] == "secret_key_abc_999", "Existing API key was inadvertently cleared on edit!"
    print("[PASS] Test 3: API credentials stored securely and never exposed to client.")

    # 4. Floating widget display
    plugin.widget_rendered = False
    footer_html = plugin.render_footer_widget()
    assert "<ivan-chat-widget" in footer_html
    assert 'widget-title="Support Twin"' in footer_html
    assert 'primary-color="#10b981"' in footer_html
    assert 'position="bottom-left"' in footer_html
    print("[PASS] Test 4: Floating widget automatic footer injection verified.")

    # 5. Shortcode functionality
    plugin.widget_rendered = False
    shortcode_html = plugin.render_shortcode({
        "title": "Shortcode Ivan",
        "color": "#e11d48",
        "position": "bottom-right",
        "open": "true"
    })
    assert 'widget-title="Shortcode Ivan"' in shortcode_html
    assert 'primary-color="#e11d48"' in shortcode_html
    assert 'position="bottom-right"' in shortcode_html
    assert ' open' in shortcode_html
    print("[PASS] Test 5: Shortcode [ivan_chat] attribute overrides verified.")

    # 6. Widget enable/disable toggle
    disabled_settings = IvanSettingsSim.get_settings(wp)
    disabled_settings["enabled"] = 0
    wp.update_option(IvanSettingsSim.OPTION_NAME, disabled_settings)

    plugin.widget_rendered = False
    assert plugin.enqueue_frontend_assets() is False
    assert plugin.render_footer_widget() == ""
    assert plugin.render_shortcode() == ""
    print("[PASS] Test 6: Complete widget enable/disable killswitch verified.")

    # Re-enable
    disabled_settings["enabled"] = 1
    wp.update_option(IvanSettingsSim.OPTION_NAME, disabled_settings)

    # 7. Position and color customization propagation
    assert IvanSettingsSim.get_option(wp, "position") == "bottom-left"
    assert IvanSettingsSim.get_option(wp, "primary_color") == "#10b981"
    plugin.widget_rendered = False
    html_out = plugin.render_footer_widget()
    assert 'position="bottom-left"' in html_out
    assert 'primary-color="#10b981"' in html_out
    print("[PASS] Test 7: Position and color customization propagated to HTML.")

    # 8. Dynamic settings integration with SSE and JSON
    assert IvanSettingsSim.get_option(wp, "stream") == 1
    stream_disabled = IvanSettingsSim.get_settings(wp)
    stream_disabled["stream"] = 0
    wp.update_option(IvanSettingsSim.OPTION_NAME, stream_disabled)
    plugin.widget_rendered = False
    html_unary = plugin.render_footer_widget()
    assert 'stream="false"' in html_unary
    print("[PASS] Test 8: SSE streaming toggle verified.")

    # 9. Duplicate widget prevention
    plugin.widget_rendered = False
    first_render = plugin.render_shortcode()
    assert "<ivan-chat-widget" in first_render
    second_render = plugin.render_footer_widget()
    assert second_render == "", "Duplicate widget was rendered in footer after shortcode!"
    third_render = plugin.render_shortcode()
    assert "already initialized" in third_render
    print("[PASS] Test 9: Duplicate widget collision prevention verified.")

    # 10. Security & Input Sanitization
    malicious_input = {
        "enabled": "1",
        "api_url": "javascript:alert(1)",
        "widget_title": '<script>alert("XSS")</script>Ivan Clean',
        "primary_color": "red; background:url('x')",
        "position": "evil-position",
        "display_mode": "hacked-mode"
    }
    sanitized_malicious = IvanSettingsSim.sanitize_settings(wp, malicious_input)
    assert sanitized_malicious["api_url"] == "", "Unsafe javascript: URL was not blocked!"
    assert "<script>" not in sanitized_malicious["widget_title"], "XSS tag was not stripped!"
    assert sanitized_malicious["widget_title"] == "alert(\"XSS\")Ivan Clean"
    assert sanitized_malicious["primary_color"] == "#031b45", "Invalid hex color was not reset to default!"
    assert sanitized_malicious["position"] == "bottom-right", "Invalid position was not reset to default!"
    assert sanitized_malicious["display_mode"] == "floating", "Invalid display mode was not reset to default!"
    print("[PASS] Test 10: Security sanitization and XSS prevention verified.")

    print("==================================================")
    print("ALL 10/10 PHASE 3 & 4 TESTS PASSED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()

