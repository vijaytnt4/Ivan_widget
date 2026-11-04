=== Ivan AI Chatbot ===
Contributors: ivanaiteam
Tags: chat, chatbot, ai, assistant, fast-api, customer-support
Requires at least: 5.6
Tested up to: 6.7
Requires PHP: 7.4
Stable tag: 1.0.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Standalone Vanilla JavaScript chat widget with Shadow DOM, secure WordPress REST API adapter, and real-time streaming integration with the Ivan AI backend.

== Description ==

Ivan AI Chatbot brings the intelligent AI digital twin of Nav Thethi directly to your WordPress website.

= Key Features =
* **Standalone Vanilla JS Web Component**: Zero framework dependencies (no React or Vue required).
* **Shadow DOM Encapsulation**: Complete isolation from theme CSS conflicts.
* **Server-to-Server Security**: Private backend API keys stay safe in WordPress options; never exposed to browser dev tools or page sources.
* **Real-Time Streaming**: Live token-by-token generation via Server-Sent Events (SSE).
* **Unary JSON Fallback**: Automatic fallback when streaming is disabled or not supported.
* **Multi-Turn Context**: Preserves `conversation_id` and `session_id` across turns.
* **Shortcode Support**: Embed Ivan anywhere with `[ivan_chat]`.
* **Customizable Branding**: Adjust title, colors, greeting message, and position from the WordPress dashboard.

== Installation ==

1. Upload `ivan-wordpress.zip` through **Plugins -> Add New -> Upload Plugin**.
2. Activate the plugin through the **Plugins** menu in WordPress.
3. Go to **Ivan AI** in the WordPress admin menu.
4. Enter your Ivan Backend API URL (e.g. `http://localhost:8000` or production URL) and your Backend API Key.
5. Save settings. The floating widget will appear automatically on your website!

== Frequently Asked Questions ==

= How do I use the shortcode? =
Simply insert `[ivan_chat]` in any post, page, or block. You can also customize attributes:
`[ivan_chat title="Helpdesk" position="bottom-left" color="#10b981"]`

= Does the plugin expose my API key? =
No. The plugin acts as a secure server-side proxy. The client-side widget only communicates with `/wp-json/ivan/v1/chat`, where WordPress validates requests and adds the API key server-side.

== Changelog ==

= 1.0.0 =
* Initial release of Ivan AI Chatbot with Shadow DOM Web Component and WordPress REST API adapter.

