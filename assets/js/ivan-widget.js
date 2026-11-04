/**
 * Ivan AI Chatbot Web Component
 * Standalone Vanilla JavaScript Chat Widget with Shadow DOM encapsulation.
 *
 * Communicates with the WordPress REST API adapter (/wp-json/ivan/v1/chat)
 * or standalone backend endpoints. Supports unary JSON and SSE streaming,
 * maintaining conversation_id and session_id across multi-turn turns.
 */

(function () {
  'use strict';

  // SVG Icons
  const ICONS = {
    chat: `<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.2L4 17.2V4h16v12z"/></svg>`,
    close: `<svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>`,
    send: `<svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>`,
    reset: `<svg viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>`,
    expand: `<svg viewBox="0 0 24 24"><path fill="currentColor" d="M15 3h6v6l-2.25-2.25-3.5 3.5-1.5-1.5 3.5-3.5L15 3zm-6 18H3v-6l2.25 2.25 3.5-3.5 1.5 1.5-3.5 3.5L9 21z"/></svg>`,
    compress: `<svg viewBox="0 0 24 24"><path fill="currentColor" d="M4 10V4h6l-2.25 2.25 3.5 3.5-1.5 1.5-3.5-3.5L4 10zm16 4v6h-6l2.25-2.25-3.5-3.5 1.5-1.5 3.5 3.5L20 14z"/></svg>`,
    bot: `<svg viewBox="0 0 24 24"><path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2M7.5 13A2.5 2.5 0 0 0 5 15.5 2.5 2.5 0 0 0 7.5 18a2.5 2.5 0 0 0 2.5-2.5A2.5 2.5 0 0 0 7.5 13m9 0a2.5 2.5 0 0 0-2.5 2.5 2.5 2.5 0 0 0 2.5 2.5 2.5 2.5 0 0 0 2.5-2.5 2.5 2.5 0 0 0-2.5-2.5z"/></svg>`,
    retry: `<svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0020 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 004 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>`
  };

  /**
   * Helper: Escape HTML to prevent XSS
   */
  function escapeHtml(text) {
    if (!text) return '';
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  /**
   * Helper: Safe Minimal Markdown Parser
   * Helper: Validate and sanitize URL (allow only safe http and https protocols)
   */
  function sanitizeUrl(url) {
    if (!url) return null;
    const trimmed = String(url).trim();
    // Decode HTML entities (e.g. &amp; -> &) before parsing
    const decoded = trimmed
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#039;/g, "'");

    try {
      const parsed = new URL(decoded);
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        return parsed.href;
      }
    } catch (e) {
      if (/^https?:\/\/[^\s"'<>]+$/i.test(decoded)) {
        return decoded;
      }
    }
    return null;
  }

  /**
   * Helper: Safe Minimal Markdown Parser with Link Extraction and XSS Protection
   */
  function renderMarkdown(rawText) {
    if (!rawText) return '';

    let text = escapeHtml(rawText);
    const tokens = [];

    // 1. Protect fenced code blocks ```lang\ncode\n```
    text = text.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
      const token = `@@@IVAN_TOKEN_${tokens.length}@@@`;
      tokens.push(`<pre><code>${code.trim()}</code></pre>`);
      return token;
    });

    // 2. Protect inline code spans `code`
    text = text.replace(/`([^`\n]+)`/g, (match, code) => {
      const token = `@@@IVAN_TOKEN_${tokens.length}@@@`;
      tokens.push(`<code>${code}</code>`);
      return token;
    });

    // 3. Convert markdown links: [label](url)
    text = text.replace(/\[([^\]]+)\]\s*\(\s*([^\s\)]+)\s*\)/g, (match, label, rawUrl) => {
      const safeUrl = sanitizeUrl(rawUrl);
      if (safeUrl) {
        const token = `@@@IVAN_TOKEN_${tokens.length}@@@`;
        tokens.push(`<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">${label}</a>`);
        return token;
      }
      return match;
    });

    // 4. Convert markdown autolinks: <https://url> (which became &lt;https://url&gt;)
    text = text.replace(/&lt;(https?:\/\/[^\s&<>"']+)&gt;/g, (match, rawUrl) => {
      const safeUrl = sanitizeUrl(rawUrl);
      if (safeUrl) {
        const token = `@@@IVAN_TOKEN_${tokens.length}@@@`;
        tokens.push(`<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(safeUrl)}</a>`);
        return token;
      }
      return match;
    });

    // 5. Convert standalone raw URLs: https://...
    text = text.replace(/(^|[\s(>])(https?:\/\/[^\s)<>"']+)/g, (match, prefix, rawUrl) => {
      // Strip trailing punctuation (periods, commas, colons, etc.)
      const punctMatch = rawUrl.match(/([.,;:!?]+)$/);
      let trailingPunct = '';
      let cleanUrl = rawUrl;
      if (punctMatch) {
        trailingPunct = punctMatch[1];
        cleanUrl = rawUrl.slice(0, -trailingPunct.length);
      }
      if (prefix === '(' && cleanUrl.endsWith(')')) {
        trailingPunct = ')' + trailingPunct;
        cleanUrl = cleanUrl.slice(0, -1);
      }
      const safeUrl = sanitizeUrl(cleanUrl);
      if (safeUrl) {
        const token = `@@@IVAN_TOKEN_${tokens.length}@@@`;
        tokens.push(`<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(safeUrl)}</a>`);
        return `${prefix}${token}${trailingPunct}`;
      }
      return match;
    });

    // 6. Convert Bold & Italic
    text = text.replace(/\*\*\*([^*\s](?:[\s\S]*?[^*\s])?)\*\*\*/g, '<strong><em>$1</em></strong>');
    text = text.replace(/\*\*([^*\s](?:[\s\S]*?[^*\s])?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/__([^_\s](?:[\s\S]*?[^_\s])?)__/g, '<strong>$1</strong>');
    text = text.replace(/(^|[^\w*])\*([^*\s](?:[\s\S]*?[^*\s])?)\*([^\w*]|$)/g, '$1<em>$2</em>$3');
    text = text.replace(/(^|[^\w_])_([^_\s](?:[\s\S]*?[^_\s])?)_([^\w_]|$)/g, '$1<em>$2</em>$3');

    // 7. Format block structures (lists, paragraphs)
    const lines = text.split('\n');
    let inList = false;
    let formattedLines = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const listMatch = line.match(/^\s*[-*]\s+(.*)$/);

      if (listMatch) {
        if (!inList) {
          formattedLines.push('<ul>');
          inList = true;
        }
        formattedLines.push(`<li>${listMatch[1]}</li>`);
      } else {
        if (inList) {
          formattedLines.push('</ul>');
          inList = false;
        }
        if (line.trim().length > 0) {
          if (line.startsWith('@@@IVAN_TOKEN_') || line.startsWith('<ul>') || line.startsWith('</ul>')) {
            formattedLines.push(line);
          } else {
            formattedLines.push(`<p>${line}</p>`);
          }
        }
      }
    }
    if (inList) {
      formattedLines.push('</ul>');
    }

    let result = formattedLines.join('');

    // 8. Restore protected tokens
    for (let i = 0; i < tokens.length; i++) {
      result = result.replace(`@@@IVAN_TOKEN_${i}@@@`, tokens[i]);
    }

    return result;
  }

  /**
   * Helper: Generate UUID v4 for sessions
   */
  function generateUUID() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  /**
   * Main Web Component Class
   */
  class IvanChatWidget extends HTMLElement {
    static get observedAttributes() {
      return [
        'api-url',
        'primary-color',
        'widget-title',
        'widget-subtitle',
        'welcome-message',
        'placeholder',
        'position',
        'bot-avatar',
        'channel',
        'stream',
        'open',
        'expanded'
      ];
    }

    constructor() {
      super();
      this.attachShadow({ mode: 'open' });

      // State
      this.isOpen = false;
      this.isExpanded = false;
      this.isLoading = false;
      this.messages = [];
      this.sessionId = null;
      this.conversationId = null;
      this.abortController = null;
      this.lastFailedMessage = null;

      // Bound listeners
      this._handleToggle = this.toggle.bind(this);
      this._handleKeyDown = this._onKeyDown.bind(this);
      this._handleInput = this._onInput.bind(this);
      this._handleSend = () => this.sendMessage();
      this._handleReset = this.resetConversation.bind(this);
    }

    connectedCallback() {
      this.sessionId = this._getOrInitSessionId();
      this.conversationId = this._getOrInitConversationId();
      this._loadHistory();
      this._render();
      this._applyConfig();

      if (this.hasAttribute('open')) {
        this.open();
      }
      if (this.hasAttribute('expanded')) {
        this.expand();
      }
    }

    disconnectedCallback() {
      if (this.abortController) {
        this.abortController.abort();
      }
    }

    attributeChangedCallback(name, oldValue, newValue) {
      if (oldValue === newValue || !this.shadowRoot) return;
      this._applyConfig();
      if (name === 'open') {
        if (newValue !== null && !this.isOpen) {
          this.open();
        } else if (newValue === null && this.isOpen) {
          this.close();
        }
      }
      if (name === 'expanded') {
        const shouldExpand = newValue !== null && newValue !== 'false';
        if (shouldExpand !== this.isExpanded) {
          this.toggleExpand(shouldExpand);
        }
      }
    }

    // Public Getters and Setters
    get apiUrl() {
      // 1. Explicit attribute
      if (this.hasAttribute('api-url')) {
        return this.getAttribute('api-url');
      }
      // 2. Global WordPress injected configuration
      if (window.ivanChatSettings && window.ivanChatSettings.apiUrl) {
        return window.ivanChatSettings.apiUrl;
      }
      // 3. Fallback default relative WordPress REST path
      return '/wp-json/ivan/v1/chat';
    }
    set apiUrl(val) {
      this.setAttribute('api-url', val);
    }

    get isStreamingEnabled() {
      const attr = this.getAttribute('stream');
      if (attr === 'false' || attr === '0') return false;
      if (window.ivanChatSettings && typeof window.ivanChatSettings.stream !== 'undefined') {
        return Boolean(window.ivanChatSettings.stream);
      }
      return true; // Default streaming enabled
    }

    get primaryColor() {
      return this.getAttribute('primary-color') || (window.ivanChatSettings && window.ivanChatSettings.primaryColor) || '#031b45';
    }
    set primaryColor(val) {
      this.setAttribute('primary-color', val);
    }

    get widgetTitle() {
      return this.getAttribute('widget-title') || (window.ivanChatSettings && window.ivanChatSettings.widgetTitle) || 'Ivan AI';
    }
    set widgetTitle(val) {
      this.setAttribute('widget-title', val);
    }

    get widgetSubtitle() {
      return this.getAttribute('widget-subtitle') || (window.ivanChatSettings && window.ivanChatSettings.widgetSubtitle) || 'Online Assistant';
    }
    set widgetSubtitle(val) {
      this.setAttribute('widget-subtitle', val);
    }

    get welcomeMessage() {
      return (
        this.getAttribute('welcome-message') ||
        (window.ivanChatSettings && window.ivanChatSettings.welcomeMessage) ||
        "Hi there! I'm Ivan, your AI assistant. How can I help you today?"
      );
    }
    set welcomeMessage(val) {
      this.setAttribute('welcome-message', val);
    }

    get placeholder() {
      return this.getAttribute('placeholder') || 'Ask Ivan a question...';
    }
    set placeholder(val) {
      this.setAttribute('placeholder', val);
    }

    get expanded() {
      return this.isExpanded;
    }
    set expanded(val) {
      if (val) {
        this.setAttribute('expanded', '');
      } else {
        this.removeAttribute('expanded');
      }
    }

    get position() {
      return this.getAttribute('position') || (window.ivanChatSettings && window.ivanChatSettings.position) || 'bottom-right';
    }
    set position(val) {
      this.setAttribute('position', val);
    }

    get botAvatar() {
      return this.getAttribute('bot-avatar') || (window.ivanChatSettings && window.ivanChatSettings.botAvatar) || '';
    }
    set botAvatar(val) {
      this.setAttribute('bot-avatar', val);
    }

    get channel() {
      return this.getAttribute('channel') || 'wordpress';
    }
    set channel(val) {
      this.setAttribute('channel', val);
    }

    // Session & Conversation ID Persistence
    _getOrInitSessionId() {
      const storageKey = 'ivan_session_id';
      let id = null;
      try {
        id = localStorage.getItem(storageKey);
        if (!id) {
          id = 'ivan-' + generateUUID();
          localStorage.setItem(storageKey, id);
        }
      } catch (e) {
        id = 'ivan-' + generateUUID();
      }
      return id;
    }

    _getOrInitConversationId() {
      const storageKey = `ivan_conv_${this.sessionId}`;
      try {
        return sessionStorage.getItem(storageKey) || null;
      } catch (e) {
        return null;
      }
    }

    _saveConversationId(id) {
      if (!id) return;
      this.conversationId = id;
      try {
        sessionStorage.setItem(`ivan_conv_${this.sessionId}`, id);
      } catch (e) {}
    }

    _loadHistory() {
      try {
        const stored = sessionStorage.getItem(`ivan_history_${this.sessionId}`);
        if (stored) {
          this.messages = JSON.parse(stored);
        }
      } catch (e) {
        this.messages = [];
      }

      if (this.messages.length === 0 && this.welcomeMessage) {
        this.messages.push({
          id: 'welcome',
          role: 'assistant',
          content: this.welcomeMessage,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        });
      }
    }

    _saveHistory() {
      try {
        sessionStorage.setItem(`ivan_history_${this.sessionId}`, JSON.stringify(this.messages));
      } catch (e) {}
    }

    _render() {
      const template = document.createElement('template');
      template.innerHTML = `
        <style>
          ${this._getStyles()}
        </style>
        <div class="ivan-container position-${this.position}" id="container">
          <div class="ivan-window" id="window" role="dialog" aria-label="Ivan Chatbot" aria-modal="false">
            <div class="ivan-header">
              <div class="ivan-header-info">
                <div class="ivan-avatar" id="avatarBox">
                  ${this._renderAvatarIcon()}
                </div>
                <div class="ivan-header-titles">
                  <h3 class="ivan-title" id="headerTitle">${escapeHtml(this.widgetTitle)}</h3>
                  <div class="ivan-subtitle">
                    <span class="ivan-status-indicator"></span>
                    <span id="headerSubtitle">${escapeHtml(this.widgetSubtitle)}</span>
                  </div>
                </div>
              </div>
              <div class="ivan-header-actions">
                <button type="button" class="ivan-btn-icon" id="resetBtn" title="Restart conversation" aria-label="Restart conversation">
                  ${ICONS.reset}
                </button>
                <button type="button" class="ivan-btn-icon" id="expandBtn" title="${this.isExpanded ? 'Restore compact view' : 'Expand chat panel'}" aria-label="${this.isExpanded ? 'Restore compact view' : 'Expand chat panel'}">
                  ${this.isExpanded ? ICONS.compress : ICONS.expand}
                </button>
                <button type="button" class="ivan-btn-icon" id="closeBtn" title="Close chat" aria-label="Close chat">
                  ${ICONS.close}
                </button>
              </div>
            </div>

            <div class="ivan-portrait-banner" id="portraitBanner">
              ${this._renderPortraitBannerContent()}
            </div>

            <div class="ivan-messages" id="messagesArea" role="log" aria-live="polite"></div>

            <div class="ivan-footer">
              <div class="ivan-input-container">
                <textarea
                  class="ivan-textarea"
                  id="messageInput"
                  rows="1"
                  placeholder="${escapeHtml(this.placeholder)}"
                  aria-label="Ask Ivan a question"
                ></textarea>
                <button
                  type="button"
                  class="ivan-send-btn"
                  id="sendBtn"
                  disabled
                  title="Send message"
                  aria-label="Send message"
                >
                  ${ICONS.send}
                </button>
              </div>
            </div>
          </div>

          <button
            type="button"
            class="ivan-launcher"
            id="launcherBtn"
            aria-label="Open chat"
            aria-haspopup="dialog"
          >
            <span class="ivan-launcher-badge"></span>
            <span class="ivan-launcher-icon icon-chat" id="launcherChatIcon">${this._renderLauncherIcon()}</span>
            <span class="ivan-launcher-icon icon-close">${ICONS.close}</span>
          </button>
        </div>
      `;

      this.shadowRoot.innerHTML = '';
      this.shadowRoot.appendChild(template.content.cloneNode(true));

      this.$container = this.shadowRoot.getElementById('container');
      this.$window = this.shadowRoot.getElementById('window');
      this.$launcher = this.shadowRoot.getElementById('launcherBtn');
      this.$launcherChatIcon = this.shadowRoot.getElementById('launcherChatIcon');
      this.$closeBtn = this.shadowRoot.getElementById('closeBtn');
      this.$resetBtn = this.shadowRoot.getElementById('resetBtn');
      this.$expandBtn = this.shadowRoot.getElementById('expandBtn');
      this.$portraitBanner = this.shadowRoot.getElementById('portraitBanner');
      this.$messagesArea = this.shadowRoot.getElementById('messagesArea');
      this.$input = this.shadowRoot.getElementById('messageInput');
      this.$sendBtn = this.shadowRoot.getElementById('sendBtn');
      this.$avatarBox = this.shadowRoot.getElementById('avatarBox');
      this.$headerTitle = this.shadowRoot.getElementById('headerTitle');
      this.$headerSubtitle = this.shadowRoot.getElementById('headerSubtitle');

      this.$launcher.addEventListener('click', this._handleToggle);
      this.$closeBtn.addEventListener('click', () => this.close());
      this.$resetBtn.addEventListener('click', this._handleReset);
      if (this.$expandBtn) {
        this.$expandBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.toggleExpand();
        });
      }
      this.$input.addEventListener('keydown', this._handleKeyDown);
      this.$input.addEventListener('input', this._handleInput);
      this.$sendBtn.addEventListener('click', this._handleSend);

      // Ensure anchor links open safely in a new tab without being blocked by host page scripts
      this.$messagesArea.addEventListener('click', (e) => {
        const path = e.composedPath ? e.composedPath() : [e.target];
        const link = path.find(el => el && el.tagName === 'A');
        if (link && link.getAttribute('href')) {
          const href = link.getAttribute('href');
          const safeUrl = sanitizeUrl(href);
          if (!safeUrl) {
            e.preventDefault();
            return;
          }
        }
      });

      this._renderMessages();
    }

    _renderLauncherIcon() {
      if (this.botAvatar) {
        return `<img src="${escapeHtml(this.botAvatar)}" class="ivan-launcher-avatar" alt="Ivan Chat" onerror="this.onerror=null;this.style.display='none';if(this.nextElementSibling)this.nextElementSibling.style.display='flex';" /><span class="ivan-launcher-fallback" style="display:none;width:100%;height:100%;align-items:center;justify-content:center;">${ICONS.chat}</span>`;
      }
      return ICONS.chat;
    }

    _renderAvatarIcon() {
      if (this.botAvatar) {
        return `<img src="${escapeHtml(this.botAvatar)}" class="ivan-header-avatar" alt="Ivan Avatar" onerror="this.onerror=null;this.style.display='none';if(this.nextElementSibling)this.nextElementSibling.style.display='flex';" /><span class="ivan-header-fallback" style="display:none;width:100%;height:100%;align-items:center;justify-content:center;">${ICONS.bot}</span>`;
      }
      return ICONS.bot;
    }

    _renderMessageAvatar() {
      if (this.botAvatar) {
        return `<div class="ivan-msg-avatar" aria-hidden="true"><img src="${escapeHtml(this.botAvatar)}" class="ivan-msg-avatar-img" alt="Ivan" onerror="this.onerror=null;this.style.display='none';if(this.nextElementSibling)this.nextElementSibling.style.display='flex';" /><span class="ivan-msg-fallback" style="display:none;width:100%;height:100%;align-items:center;justify-content:center;">${ICONS.bot}</span></div>`;
      }
      return `<div class="ivan-msg-avatar" aria-hidden="true"><span class="ivan-msg-fallback" style="display:flex;width:100%;height:100%;align-items:center;justify-content:center;">${ICONS.bot}</span></div>`;
    }

    _renderPortraitBannerContent() {
      const tagText = escapeHtml(this.widgetSubtitle || "Nav's Twin");
      if (this.botAvatar) {
        return `
          <div class="ivan-portrait-media">
            <div class="ivan-portrait-bg" style="background-image: url('${escapeHtml(this.botAvatar)}');" aria-hidden="true"></div>
            <div class="ivan-portrait-bg-overlay" aria-hidden="true"></div>
            <img src="${escapeHtml(this.botAvatar)}" class="ivan-portrait-img" alt="Ivan AI Portrait" onerror="this.onerror=null;this.closest('.ivan-portrait-banner').classList.add('has-fallback');" />
            <div class="ivan-portrait-fallback">
              <div class="ivan-portrait-fallback-icon">${ICONS.bot}</div>
              <div class="ivan-portrait-fallback-text">Ivan AI Assistant</div>
            </div>
            <div class="ivan-portrait-overlay">
              <span class="ivan-portrait-tag"><span class="ivan-status-indicator"></span> ${tagText}</span>
            </div>
          </div>
        `;
      }
      return `
        <div class="ivan-portrait-media has-fallback">
          <div class="ivan-portrait-fallback">
            <div class="ivan-portrait-fallback-icon">${ICONS.bot}</div>
            <div class="ivan-portrait-fallback-text">Ivan AI Assistant</div>
          </div>
          <div class="ivan-portrait-overlay">
            <span class="ivan-portrait-tag"><span class="ivan-status-indicator"></span> ${tagText}</span>
          </div>
        </div>
      `;
    }

    toggleExpand(forceState) {
      const next = forceState !== undefined ? Boolean(forceState) : !this.isExpanded;
      this.isExpanded = next;

      if (this.$container) {
        this.$container.classList.toggle('is-expanded', this.isExpanded);
      }
      if (this.$expandBtn) {
        this.$expandBtn.innerHTML = this.isExpanded ? ICONS.compress : ICONS.expand;
        const title = this.isExpanded ? 'Restore compact view' : 'Expand chat panel';
        this.$expandBtn.title = title;
        this.$expandBtn.setAttribute('aria-label', title);
      }

      this._scrollToBottom();
      this._dispatch('ivan:expand-changed', { expanded: this.isExpanded });
    }

    expand() {
      if (!this.isExpanded) this.toggleExpand(true);
    }

    restore() {
      if (this.isExpanded) this.toggleExpand(false);
    }

    _applyConfig() {
      if (!this.$container) return;
      this.style.setProperty('--ivan-primary', this.primaryColor);
      this.style.setProperty('--ivan-user-bubble', this.primaryColor);
      if (this.primaryColor.toLowerCase() === '#031b45') {
        this.style.setProperty('--ivan-primary-hover', '#0a2e70');
        this.style.setProperty('--ivan-primary-active', '#021435');
      }

      if (this.$headerTitle) this.$headerTitle.textContent = this.widgetTitle;
      if (this.$headerSubtitle) this.$headerSubtitle.textContent = this.widgetSubtitle;
      if (this.$input) this.$input.placeholder = this.placeholder;

      this.$container.className = `ivan-container position-${this.position} ${this.isOpen ? 'is-open' : ''} ${this.isExpanded ? 'is-expanded' : ''}`;

      if (this.$avatarBox) {
        this.$avatarBox.innerHTML = this._renderAvatarIcon();
      }
      if (this.$launcherChatIcon) {
        this.$launcherChatIcon.innerHTML = this._renderLauncherIcon();
      }
      if (this.$portraitBanner) {
        this.$portraitBanner.classList.remove('has-fallback');
        this.$portraitBanner.innerHTML = this._renderPortraitBannerContent();
      }
      if (this.$expandBtn) {
        this.$expandBtn.innerHTML = this.isExpanded ? ICONS.compress : ICONS.expand;
        const title = this.isExpanded ? 'Restore compact view' : 'Expand chat panel';
        this.$expandBtn.title = title;
        this.$expandBtn.setAttribute('aria-label', title);
      }
    }

    _renderMessages() {
      if (!this.$messagesArea) return;
      this.$messagesArea.innerHTML = '';

      this.messages.forEach(msg => {
        this._appendMessageElement(msg);
      });

      this._scrollToBottom();
    }

    _appendMessageElement(msg) {
      const msgDiv = document.createElement('div');
      msgDiv.className = `ivan-message ${msg.role === 'user' ? 'user' : 'bot'} ${msg.isError ? 'error' : ''}`;
      msgDiv.id = `msg-${msg.id || Date.now()}`;

      if (msg.role !== 'user') {
        const avatarContainer = document.createElement('div');
        avatarContainer.className = 'ivan-msg-avatar-container';
        avatarContainer.innerHTML = this._renderMessageAvatar();
        msgDiv.appendChild(avatarContainer);
      }

      const bubbleWrap = document.createElement('div');
      bubbleWrap.className = 'ivan-bubble-wrapper';

      const bubbleDiv = document.createElement('div');
      bubbleDiv.className = 'ivan-bubble';
      bubbleDiv.innerHTML = renderMarkdown(msg.content);

      if (msg.isError) {
        const retryBtn = document.createElement('button');
        retryBtn.type = 'button';
        retryBtn.className = 'ivan-retry-btn';
        retryBtn.innerHTML = `${ICONS.retry} Retry`;
        retryBtn.addEventListener('click', () => this._retryLastMessage());
        bubbleDiv.appendChild(retryBtn);
      }

      bubbleWrap.appendChild(bubbleDiv);

      if (msg.timestamp) {
        const metaDiv = document.createElement('div');
        metaDiv.className = 'ivan-message-meta';
        metaDiv.textContent = msg.timestamp;
        bubbleWrap.appendChild(metaDiv);
      }

      msgDiv.appendChild(bubbleWrap);

      this.$messagesArea.appendChild(msgDiv);
      this._scrollToBottom();
      return msgDiv;
    }

    _showTypingIndicator() {
      this._hideTypingIndicator();
      const indicator = document.createElement('div');
      indicator.className = 'ivan-typing-wrap';
      indicator.id = 'ivan-typing-indicator';
      indicator.innerHTML = `
        <div class="ivan-msg-avatar-container">
          ${this._renderMessageAvatar()}
        </div>
        <div class="ivan-typing-indicator">
          <span class="ivan-typing-dot"></span>
          <span class="ivan-typing-dot"></span>
          <span class="ivan-typing-dot"></span>
        </div>
      `;
      this.$messagesArea.appendChild(indicator);
      this._scrollToBottom();
    }

    _hideTypingIndicator() {
      const existing = this.shadowRoot.getElementById('ivan-typing-indicator');
      if (existing) {
        existing.remove();
      }
    }

    _scrollToBottom() {
      if (this.$messagesArea) {
        requestAnimationFrame(() => {
          this.$messagesArea.scrollTop = this.$messagesArea.scrollHeight;
        });
      }
    }

    _onInput() {
      const val = this.$input.value.trim();
      this.$sendBtn.disabled = val.length === 0 || this.isLoading;

      this.$input.style.height = 'auto';
      const newHeight = Math.min(this.$input.scrollHeight, 100);
      this.$input.style.height = (newHeight > 24 ? newHeight : 24) + 'px';
    }

    _onKeyDown(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!this.$sendBtn.disabled && !this.isLoading) {
          this.sendMessage();
        }
      }
    }

    open() {
      this.isOpen = true;
      if (this.$container) {
        this.$container.classList.add('is-open');
        this.$launcher.setAttribute('aria-expanded', 'true');
      }
      this.dispatchEvent(new CustomEvent('ivan:open', { bubbles: true, composed: true }));
      setTimeout(() => {
        if (this.$input) this.$input.focus();
        this._scrollToBottom();
      }, 200);
    }

    close() {
      this.isOpen = false;
      if (this.$container) {
        this.$container.classList.remove('is-open');
        this.$launcher.setAttribute('aria-expanded', 'false');
      }
      this.dispatchEvent(new CustomEvent('ivan:close', { bubbles: true, composed: true }));
    }

    toggle() {
      if (this.isOpen) {
        this.close();
      } else {
        this.open();
      }
    }

    resetConversation() {
      if (confirm('Start a new conversation? This will clear current chat history.')) {
        if (this.abortController) {
          this.abortController.abort();
        }
        this.isLoading = false;
        this.conversationId = null;
        this.sessionId = 'ivan-' + generateUUID();

        try {
          localStorage.setItem('ivan_session_id', this.sessionId);
          sessionStorage.removeItem(`ivan_conv_${this.sessionId}`);
          sessionStorage.removeItem(`ivan_history_${this.sessionId}`);
        } catch (e) {}

        this.messages = [];
        if (this.welcomeMessage) {
          this.messages.push({
            id: 'welcome',
            role: 'assistant',
            content: this.welcomeMessage,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          });
        }
        this._saveHistory();
        this._renderMessages();
        this._hideTypingIndicator();
        this.dispatchEvent(new CustomEvent('ivan:reset', { bubbles: true, composed: true }));
      }
    }

    async sendMessage(customText = null) {
      let text = '';
      if (typeof customText === 'string') {
        text = customText.trim();
      } else if (this.$input && typeof this.$input.value === 'string') {
        text = this.$input.value.trim();
      }

      if (!text || this.isLoading) return;

      this.lastFailedMessage = text;

      if (this.$input) {
        this.$input.value = '';
        this.$input.style.height = 'auto';
        this.$sendBtn.disabled = true;
      }

      const userMsg = {
        id: 'msg-' + Date.now(),
        role: 'user',
        content: text,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      this.messages.push(userMsg);
      this._appendMessageElement(userMsg);
      this._saveHistory();

      this.dispatchEvent(
        new CustomEvent('ivan:message-sent', {
          detail: {
            message: userMsg,
            sessionId: this.sessionId,
            conversationId: this.conversationId
          },
          bubbles: true,
          composed: true
        })
      );

      this.isLoading = true;
      this._showTypingIndicator();

      try {
        if (!this.apiUrl || this.apiUrl === 'mock' || this.apiUrl === 'demo') {
          await this._mockStreamingResponse(text);
        } else if (this.isStreamingEnabled) {
          await this._sendStreamingRequest(text);
        } else {
          await this._sendUnaryRequest(text);
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('[Ivan AI] Error:', err);
          this._handleError(err.message || 'Unable to connect to Ivan AI service.');
        }
      } finally {
        this.isLoading = false;
        this._hideTypingIndicator();
        if (this.$input) {
          this._onInput();
          this.$input.focus();
        }
      }
    }

    _retryLastMessage() {
      if (this.lastFailedMessage && typeof this.lastFailedMessage === 'string') {
        const textToRetry = this.lastFailedMessage;
        this.messages = this.messages.filter(m => !m.isError);
        this._renderMessages();
        this.sendMessage(textToRetry);
      }
    }

    _handleError(errorMessage) {
      this._hideTypingIndicator();
      const errItem = {
        id: 'err-' + Date.now(),
        role: 'assistant',
        isError: true,
        content: `**Error**: ${errorMessage}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      this.messages.push(errItem);
      this._appendMessageElement(errItem);
      this._saveHistory();

      this.dispatchEvent(
        new CustomEvent('ivan:error', {
          detail: { error: errorMessage },
          bubbles: true,
          composed: true
        })
      );
    }

    /**
     * Unary JSON Integration
     * Sends message to /wp-json/ivan/v1/chat, parses answer, and updates conversation_id.
     */
    async _sendUnaryRequest(promptText) {
      this.abortController = new AbortController();
      const timeoutId = setTimeout(() => this.abortController.abort(), 50000);

      const payload = {
        message: promptText,
        conversation_id: this.conversationId,
        session_id: this.sessionId,
        stream: false
      };

      const headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      };

      if (window.ivanChatSettings && window.ivanChatSettings.nonce) {
        headers['X-WP-Nonce'] = window.ivanChatSettings.nonce;
      }

      const response = await fetch(this.apiUrl, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(payload),
        signal: this.abortController.signal
      });

      clearTimeout(timeoutId);

      const contentType = response.headers.get('content-type') || '';
      let data = {};
      if (contentType.includes('application/json')) {
        data = await response.json();
      } else {
        const raw = await response.text();
        throw new Error(`Server returned HTTP ${response.status}: ${raw.substring(0, 100)}`);
      }

      if (!response.ok) {
        const errMsg = data.message || data.detail || (data.data && data.data.message) || `HTTP error ${response.status}`;
        throw new Error(errMsg);
      }

      // Update and persist state
      if (data.conversation_id) {
        this._saveConversationId(data.conversation_id);
      }
      if (data.session_id) {
        this.sessionId = data.session_id;
      }

      const replyText = data.answer || data.reply || data.response || 'No response generated.';
      this._hideTypingIndicator();

      const botMsg = {
        id: 'bot-' + Date.now(),
        role: 'assistant',
        content: replyText,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      this.messages.push(botMsg);
      this._appendMessageElement(botMsg);
      this._saveHistory();

      this.dispatchEvent(
        new CustomEvent('ivan:message-received', {
          detail: {
            message: botMsg,
            sessionId: this.sessionId,
            conversationId: this.conversationId
          },
          bubbles: true,
          composed: true
        })
      );
    }

    /**
     * Real-Time SSE Streaming Request
     * Streams tokens from /wp-json/ivan/v1/chat, updates bubble incrementally,
     * and captures conversation_id on 'done' event.
     */
    async _sendStreamingRequest(promptText) {
      this.abortController = new AbortController();
      const timeoutId = setTimeout(() => this.abortController.abort(), 65000);

      const payload = {
        message: promptText,
        conversation_id: this.conversationId,
        session_id: this.sessionId,
        stream: true
      };

      const headers = {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream, application/json'
      };

      if (window.ivanChatSettings && window.ivanChatSettings.nonce) {
        headers['X-WP-Nonce'] = window.ivanChatSettings.nonce;
      }

      const response = await fetch(this.apiUrl, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(payload),
        signal: this.abortController.signal
      });

      clearTimeout(timeoutId);

      const contentType = response.headers.get('content-type') || '';

      // If server returned non-200 JSON or plain error
      if (!response.ok) {
        if (contentType.includes('application/json')) {
          const errData = await response.json();
          const errMsg = errData.message || errData.detail || `HTTP ${response.status}`;
          throw new Error(errMsg);
        } else {
          const errText = await response.text();
          throw new Error(`Server returned HTTP ${response.status}: ${errText.substring(0, 100)}`);
        }
      }

      // Check if response is streaming SSE or fallback JSON
      if (!contentType.includes('text/event-stream') && contentType.includes('application/json')) {
        const data = await response.json();
        if (data.conversation_id) this._saveConversationId(data.conversation_id);
        if (data.session_id) this.sessionId = data.session_id;

        this._hideTypingIndicator();
        const botMsg = {
          id: 'bot-' + Date.now(),
          role: 'assistant',
          content: data.answer || data.reply || '',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        };
        this.messages.push(botMsg);
        this._appendMessageElement(botMsg);
        this._saveHistory();
        return;
      }

      // Read SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');

      this._hideTypingIndicator();

      const botMsgId = 'bot-' + Date.now();
      const botMsg = {
        id: botMsgId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      this.messages.push(botMsg);

      const msgElement = this._appendMessageElement(botMsg);
      const bubble = msgElement.querySelector('.ivan-bubble');

      let accumulatedText = '';
      let buffer = '';
      let hasReceivedToken = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop(); // Keep partial line for next iteration

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data:')) continue;

          const dataPayload = trimmed.replace(/^data:\s*/, '').trim();
          if (dataPayload === '[DONE]') continue;

          try {
            const event = JSON.parse(dataPayload);

            if (event.type === 'token') {
              hasReceivedToken = true;
              accumulatedText += event.token || '';
              botMsg.content = accumulatedText;
              bubble.innerHTML = renderMarkdown(accumulatedText);
              this._scrollToBottom();
            } else if (event.type === 'done') {
              if (event.conversation_id) {
                this._saveConversationId(event.conversation_id);
              }
              if (event.session_id) {
                this.sessionId = event.session_id;
              }
              const finalAnswer = event.answer || accumulatedText;
              if (finalAnswer) {
                accumulatedText = finalAnswer;
                botMsg.content = finalAnswer;
                bubble.innerHTML = renderMarkdown(finalAnswer);
                this._scrollToBottom();
              }
            } else if (event.type === 'error') {
              throw new Error(event.message || 'Stream processing error');
            }
          } catch (jsonErr) {
            // Raw text fallback if payload is not JSON
            if (dataPayload && !dataPayload.startsWith('{')) {
              accumulatedText += dataPayload;
              botMsg.content = accumulatedText;
              bubble.innerHTML = renderMarkdown(accumulatedText);
              this._scrollToBottom();
            }
          }
        }
      }

      this._saveHistory();
      this.dispatchEvent(
        new CustomEvent('ivan:message-received', {
          detail: {
            message: botMsg,
            sessionId: this.sessionId,
            conversationId: this.conversationId
          },
          bubbles: true,
          composed: true
        })
      );
    }

    /**
     * Mock Streaming Response for Demo Mode
     */
    async _mockStreamingResponse(userPrompt) {
      await new Promise(r => setTimeout(r, 400));
      this._hideTypingIndicator();

      if (!this.conversationId) {
        this._saveConversationId(generateUUID());
      }

      const botMsgId = 'bot-' + Date.now();
      const botMsg = {
        id: botMsgId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      this.messages.push(botMsg);

      const msgElement = this._appendMessageElement(botMsg);
      const bubble = msgElement.querySelector('.ivan-bubble');

      const mockText = `Received your message: "${userPrompt}"\n\n- Conversation ID: \`${this.conversationId}\`\n- Session ID: \`${this.sessionId}\`\n\nI am Ivan, the digital twin of Nav Thethi. How can I assist you further?`;
      const chunks = mockText.split(/(.{3,6})/g).filter(Boolean);

      for (const chunk of chunks) {
        botMsg.content += chunk;
        bubble.innerHTML = renderMarkdown(botMsg.content);
        this._scrollToBottom();
        await new Promise(r => setTimeout(r, 30));
      }

      this._saveHistory();
      this.dispatchEvent(
        new CustomEvent('ivan:message-received', {
          detail: {
            message: botMsg,
            sessionId: this.sessionId,
            conversationId: this.conversationId
          },
          bubbles: true,
          composed: true
        })
      );
    }

    _getStyles() {
      return `
        :host {
          --ivan-primary: #031b45;
          --ivan-primary-hover: #0a2e70;
          --ivan-primary-active: #021435;
          --ivan-primary-contrast: #ffffff;
          --ivan-surface: #ffffff;
          --ivan-surface-secondary: #f8fafc;
          --ivan-border: #e2e8f0;
          --ivan-text: #0f172a;
          --ivan-text-muted: #64748b;
          --ivan-bot-bubble: #f1f5f9;
          --ivan-bot-bubble-text: #0f172a;
          --ivan-user-bubble: var(--ivan-primary);
          --ivan-user-bubble-text: var(--ivan-primary-contrast);
          --ivan-font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
          --ivan-radius-lg: 16px;
          --ivan-radius-md: 12px;
          --ivan-radius-sm: 8px;
          --ivan-shadow-lg: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
          --ivan-shadow-launcher: 0 10px 15px -3px rgba(3, 27, 69, 0.4), 0 4px 6px -4px rgba(3, 27, 69, 0.25);
          --ivan-z-index: 999999;
          --ivan-transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
          --ivan-transition-normal: 250ms cubic-bezier(0.16, 1, 0.3, 1);

          display: block;
          font-family: var(--ivan-font-family);
          color: var(--ivan-text);
          line-height: 1.5;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;
        }

        .ivan-container {
          position: fixed;
          z-index: var(--ivan-z-index);
          display: flex;
          flex-direction: column;
          box-sizing: border-box;
        }

        .ivan-container * {
          box-sizing: border-box;
        }

        .ivan-container.position-bottom-right {
          bottom: 24px;
          right: 24px;
          align-items: flex-end;
        }

        .ivan-container.position-bottom-left {
          bottom: 24px;
          left: 24px;
          align-items: flex-start;
        }

        .ivan-launcher {
          width: 60px;
          height: 60px;
          border-radius: 50%;
          background: var(--ivan-primary);
          color: var(--ivan-primary-contrast);
          border: none;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: var(--ivan-shadow-launcher);
          transition: transform var(--ivan-transition-normal), background-color var(--ivan-transition-fast), box-shadow var(--ivan-transition-fast);
          outline: none;
          padding: 0;
          position: relative;
        }

        .ivan-launcher-avatar {
          width: 48px;
          height: 48px;
          border-radius: 50%;
          object-fit: cover;
          object-position: center top;
          border: 2px solid rgba(255, 255, 255, 0.7);
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
          display: block;
        }

        .ivan-launcher:hover {
          transform: scale(1.06);
          background: var(--ivan-primary-hover);
          box-shadow: 0 12px 20px -3px rgba(3, 27, 69, 0.5);
        }

        .ivan-launcher:active {
          transform: scale(0.96);
          background: var(--ivan-primary-active, #021435);
        }

        .ivan-launcher:focus-visible {
          outline: 3px solid rgba(3, 27, 69, 0.45);
          outline-offset: 3px;
        }

        .ivan-launcher-icon {
          width: 100%;
          height: 100%;
          transition: transform var(--ivan-transition-normal), opacity var(--ivan-transition-fast);
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .ivan-launcher-icon svg {
          width: 28px;
          height: 28px;
          fill: currentColor;
        }

        .ivan-launcher .icon-close {
          display: none;
        }

        /* Hide floating launcher completely whenever chat window is open */
        .ivan-container.is-open .ivan-launcher {
          display: none !important;
        }

        .ivan-launcher-badge {
          position: absolute;
          top: 2px;
          right: 2px;
          width: 14px;
          height: 14px;
          background: #10b981;
          border: 2px solid #ffffff;
          border-radius: 50%;
          box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.05);
        }

        .ivan-window {
          width: 380px;
          height: 600px;
          max-width: calc(100vw - 32px);
          max-height: calc(100vh - 48px);
          background: var(--ivan-surface);
          border-radius: var(--ivan-radius-lg);
          box-shadow: var(--ivan-shadow-lg);
          border: 1px solid var(--ivan-border);
          display: flex;
          flex-direction: column;
          overflow: hidden;
          margin-bottom: 0;
          opacity: 0;
          visibility: hidden;
          transform: scale(0.95) translateY(10px);
          transform-origin: bottom right;
          transition: opacity var(--ivan-transition-normal), transform var(--ivan-transition-normal), visibility var(--ivan-transition-normal), width var(--ivan-transition-normal), height var(--ivan-transition-normal);
        }

        .ivan-container.position-bottom-left .ivan-window {
          transform-origin: bottom left;
        }

        .ivan-container.is-open .ivan-window {
          opacity: 1;
          visibility: visible;
          transform: scale(1) translateY(0);
        }

        /* Expanded Mode (Right-Side Panel per Screenshot 3) */
        .ivan-container.is-expanded .ivan-window {
          width: min(380px, calc(100vw - 24px));
          height: min(850px, calc(100vh - 48px));
          max-width: calc(100vw - 24px);
          max-height: calc(100vh - 48px);
          margin-bottom: 0;
          box-shadow: 0 25px 50px -12px rgba(3, 27, 69, 0.35), 0 0 0 1px rgba(3, 27, 69, 0.1);
        }

        .ivan-container.is-expanded .ivan-portrait-banner {
          display: none;
        }

        /* Portrait Banner (Layered portrait treatment) */
        .ivan-portrait-banner {
          width: 100%;
          height: 180px;
          background: linear-gradient(180deg, #0b224f 0%, #031b45 100%);
          position: relative;
          overflow: hidden;
          flex-shrink: 0;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
          display: block;
        }

        .ivan-portrait-media {
          width: 100%;
          height: 100%;
          position: relative;
          overflow: hidden;
        }

        /* Background Layer: Avatar image, cover sizing, blur, subtle dark/teal overlay */
        .ivan-portrait-bg {
          position: absolute;
          top: -24px;
          left: -24px;
          right: -24px;
          bottom: -24px;
          background-size: cover;
          background-position: center 25%;
          background-repeat: no-repeat;
          filter: blur(18px) brightness(0.68) saturate(1.3);
          transform: scale(1.15);
          pointer-events: none;
          z-index: 0;
        }

        .ivan-portrait-bg-overlay {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: linear-gradient(
            180deg,
            rgba(3, 27, 69, 0.2) 0%,
            rgba(3, 27, 69, 0.45) 55%,
            rgba(3, 27, 69, 0.88) 100%
          );
          pointer-events: none;
          z-index: 1;
        }

        /* Foreground Layer: Uncropped contained avatar with full head & shoulders */
        .ivan-portrait-img {
          position: absolute;
          top: 6px;
          left: 50%;
          transform: translateX(-50%);
          z-index: 2;
          width: auto;
          max-width: 100%;
          height: 280px;
          object-fit: contain;
          filter: drop-shadow(0 8px 18px rgba(0, 0, 0, 0.5));
          -webkit-mask-image: linear-gradient(to right, transparent 0%, black 22%, black 78%, transparent 100%),
                              linear-gradient(to bottom, black 68%, transparent 95%);
          mask-image: linear-gradient(to right, transparent 0%, black 22%, black 78%, transparent 100%),
                      linear-gradient(to bottom, black 68%, transparent 95%);
          -webkit-mask-composite: source-in;
          mask-composite: intersect;
          pointer-events: none;
        }

        .ivan-portrait-banner.has-fallback .ivan-portrait-bg,
        .ivan-portrait-banner.has-fallback .ivan-portrait-bg-overlay,
        .ivan-portrait-banner.has-fallback .ivan-portrait-img {
          display: none !important;
        }

        .ivan-portrait-fallback {
          display: none;
          width: 100%;
          height: 100%;
          background: linear-gradient(135deg, #0b2559 0%, #031b45 100%);
          color: #ffffff;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 8px;
          z-index: 2;
        }

        .ivan-portrait-banner.has-fallback .ivan-portrait-fallback {
          display: flex;
        }

        .ivan-portrait-fallback-icon svg {
          width: 48px;
          height: 48px;
          fill: rgba(255, 255, 255, 0.85);
        }

        .ivan-portrait-fallback-text {
          font-size: 13px;
          font-weight: 500;
          letter-spacing: 0.5px;
          color: rgba(255, 255, 255, 0.9);
        }

        .ivan-portrait-overlay {
          position: absolute;
          bottom: 10px;
          left: 12px;
          right: 12px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          pointer-events: none;
          z-index: 3;
        }

        .ivan-portrait-tag {
          background: rgba(3, 27, 69, 0.78);
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
          color: #ffffff;
          font-size: 11px;
          font-weight: 500;
          padding: 4px 10px;
          border-radius: 9999px;
          border: 1px solid rgba(255, 255, 255, 0.2);
          display: inline-flex;
          align-items: center;
          gap: 6px;
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.25);
        }

        .ivan-header {
          background: var(--ivan-primary);
          color: var(--ivan-primary-contrast);
          padding: 16px 20px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
          flex-shrink: 0;
        }

        .ivan-header-info {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .ivan-avatar {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.2);
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
          flex-shrink: 0;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }

        .ivan-avatar img,
        .ivan-header-avatar {
          width: 100%;
          height: 100%;
          object-fit: cover;
          object-position: center top;
          border-radius: 50%;
          display: block;
          border: 2px solid rgba(255, 255, 255, 0.7);
          box-sizing: border-box;
        }

        .ivan-avatar svg {
          width: 22px;
          height: 22px;
          fill: currentColor;
        }

        .ivan-header-titles {
          display: flex;
          flex-direction: column;
        }

        .ivan-title {
          font-weight: 600;
          font-size: 16px;
          line-height: 1.25;
          margin: 0;
        }

        .ivan-subtitle {
          font-size: 12px;
          opacity: 0.85;
          margin-top: 2px;
          display: flex;
          align-items: center;
          gap: 5px;
        }

        .ivan-status-indicator {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background-color: #34d399;
          display: inline-block;
          box-shadow: 0 0 6px #34d399;
        }

        .ivan-header-actions {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .ivan-btn-icon {
          background: transparent;
          border: none;
          color: var(--ivan-primary-contrast);
          width: 32px;
          height: 32px;
          border-radius: 6px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          opacity: 0.85;
          transition: opacity var(--ivan-transition-fast), background-color var(--ivan-transition-fast);
          padding: 0;
        }

        .ivan-btn-icon:hover {
          opacity: 1;
          background: rgba(255, 255, 255, 0.15);
        }

        .ivan-btn-icon svg {
          width: 18px;
          height: 18px;
          fill: currentColor;
        }

        .ivan-messages {
          flex: 1 1 auto;
          overflow-y: auto;
          padding: 20px 16px;
          display: flex;
          flex-direction: column;
          gap: 16px;
          background: var(--ivan-surface-secondary);
          scroll-behavior: smooth;
        }

        .ivan-message {
          display: flex;
          flex-direction: row;
          max-width: 88%;
          animation: ivan-fade-in 200ms ease-out forwards;
          gap: 8px;
          align-items: flex-start;
        }

        @keyframes ivan-fade-in {
          from {
            opacity: 0;
            transform: translateY(6px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .ivan-message.user {
          align-self: flex-end;
          flex-direction: column;
        }

        .ivan-message.bot {
          align-self: flex-start;
        }

        .ivan-msg-avatar-container {
          flex-shrink: 0;
          margin-top: 2px;
        }

        .ivan-msg-avatar {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          overflow: hidden;
          flex-shrink: 0;
          border: 1.5px solid rgba(0, 0, 0, 0.12);
          background: #ffffff;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .ivan-msg-avatar img,
        .ivan-msg-avatar-img {
          width: 100%;
          height: 100%;
          object-fit: cover;
          object-position: center top;
          border-radius: 50%;
          display: block;
        }

        .ivan-msg-avatar svg {
          width: 18px;
          height: 18px;
          fill: var(--ivan-primary);
        }

        .ivan-bubble-wrapper {
          display: flex;
          flex-direction: column;
          flex: 1 1 auto;
          min-width: 0;
        }

        .ivan-bubble {
          padding: 12px 16px;
          border-radius: var(--ivan-radius-md);
          font-size: 14px;
          line-height: 1.5;
          word-break: break-word;
          position: relative;
        }

        .ivan-message.user .ivan-bubble {
          background: var(--ivan-user-bubble);
          color: var(--ivan-user-bubble-text);
          border-bottom-right-radius: 4px;
          box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
        }

        .ivan-message.bot .ivan-bubble {
          background: var(--ivan-bot-bubble);
          color: var(--ivan-bot-bubble-text);
          border-bottom-left-radius: 4px;
          border: 1px solid var(--ivan-border);
        }

        .ivan-message-meta {
          font-size: 11px;
          color: var(--ivan-text-muted);
          margin-top: 4px;
          padding: 0 4px;
        }

        .ivan-message.user .ivan-message-meta {
          text-align: right;
        }

        .ivan-bubble p {
          margin: 0 0 8px 0;
        }

        .ivan-bubble p:last-child {
          margin-bottom: 0;
        }

        .ivan-bubble a {
          color: var(--ivan-primary);
          text-decoration: underline;
          cursor: pointer;
          word-break: break-all;
          transition: opacity var(--ivan-transition-fast);
        }

        .ivan-bubble a:hover {
          opacity: 0.8;
        }

        .ivan-message.user .ivan-bubble a {
          color: #ffffff;
          text-decoration: underline;
        }

        .ivan-bubble code {
          font-family: monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo;
          font-size: 12px;
          background: rgba(0, 0, 0, 0.06);
          padding: 2px 5px;
          border-radius: 4px;
        }

        .ivan-message.user .ivan-bubble code {
          background: rgba(255, 255, 255, 0.2);
        }

        .ivan-bubble pre {
          margin: 8px 0;
          padding: 10px;
          background: #1e293b;
          color: #f8fafc;
          border-radius: 6px;
          overflow-x: auto;
          font-size: 12px;
        }

        .ivan-bubble pre code {
          background: transparent;
          padding: 0;
          color: inherit;
        }

        .ivan-bubble ul, .ivan-bubble ol {
          margin: 4px 0 8px 18px;
          padding: 0;
        }

        .ivan-bubble li {
          margin-bottom: 3px;
        }

        .ivan-bubble blockquote {
          border-left: 3px solid var(--ivan-primary);
          margin: 6px 0;
          padding-left: 10px;
          color: var(--ivan-text-muted);
        }

        .ivan-typing-wrap {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          align-self: flex-start;
          margin-top: 2px;
        }

        .ivan-typing-indicator {
          display: flex;
          align-items: center;
          gap: 4px;
          padding: 10px 14px;
          background: var(--ivan-bot-bubble);
          border-radius: var(--ivan-radius-md);
          border-bottom-left-radius: 4px;
          border: 1px solid var(--ivan-border);
          align-self: flex-start;
          width: fit-content;
        }

        .ivan-typing-dot {
          width: 7px;
          height: 7px;
          background-color: var(--ivan-text-muted);
          border-radius: 50%;
          animation: ivan-bounce 1.4s infinite ease-in-out both;
        }

        .ivan-typing-dot:nth-child(1) {
          animation-delay: -0.32s;
        }

        .ivan-typing-dot:nth-child(2) {
          animation-delay: -0.16s;
        }

        @keyframes ivan-bounce {
          0%, 80%, 100% {
            transform: scale(0.6);
            opacity: 0.5;
          }
          40% {
            transform: scale(1);
            opacity: 1;
          }
        }

        .ivan-message.error .ivan-bubble {
          background: #fef2f2;
          color: #991b1b;
          border: 1px solid #fecaca;
        }

        .ivan-retry-btn {
          margin-top: 8px;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          background: #ffffff;
          border: 1px solid #f87171;
          color: #b91c1c;
          padding: 4px 10px;
          border-radius: var(--ivan-radius-sm);
          font-size: 12px;
          font-weight: 500;
          cursor: pointer;
          transition: all var(--ivan-transition-fast);
        }

        .ivan-retry-btn:hover {
          background: #fee2e2;
        }

        .ivan-footer {
          padding: 12px 16px;
          background: var(--ivan-surface);
          border-top: 1px solid var(--ivan-border);
          display: flex;
          flex-direction: column;
        }

        .ivan-input-container {
          display: flex;
          align-items: center;
          gap: 8px;
          background: var(--ivan-surface-secondary);
          border: 1px solid var(--ivan-border);
          border-radius: 24px;
          padding: 4px 6px 4px 16px;
          transition: border-color var(--ivan-transition-fast), box-shadow var(--ivan-transition-fast);
        }

        .ivan-input-container:focus-within {
          border-color: var(--ivan-primary);
          box-shadow: 0 0 0 3px rgba(3, 27, 69, 0.2);
          background: var(--ivan-surface);
        }

        .ivan-textarea {
          flex: 1;
          border: none;
          background: transparent;
          font-family: inherit;
          font-size: 14px;
          color: var(--ivan-text);
          outline: none;
          resize: none;
          max-height: 100px;
          min-height: 24px;
          line-height: 24px;
          padding: 0;
          margin: 0;
        }

        .ivan-textarea::placeholder {
          color: var(--ivan-text-muted);
        }

        .ivan-send-btn {
          width: 36px;
          height: 36px;
          border-radius: 50%;
          background: var(--ivan-primary);
          color: var(--ivan-primary-contrast);
          border: none;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
          transition: background-color var(--ivan-transition-fast), transform var(--ivan-transition-fast), opacity var(--ivan-transition-fast);
          outline: none;
          padding: 0;
        }

        .ivan-send-btn:hover:not(:disabled) {
          background: var(--ivan-primary-hover);
          transform: scale(1.05);
        }

        .ivan-send-btn:active:not(:disabled) {
          background: var(--ivan-primary-active, #021435);
          transform: scale(0.96);
        }

        .ivan-send-btn:focus-visible {
          outline: 2px solid rgba(3, 27, 69, 0.45);
          outline-offset: 2px;
        }

        .ivan-send-btn:disabled {
          opacity: 0.4;
          cursor: not-allowed;
          transform: none;
        }

        .ivan-send-btn svg {
          width: 16px;
          height: 16px;
          fill: currentColor;
          transform: translateX(1px);
        }

        .ivan-brand-note {
          display: none;
        }

        .ivan-btn-icon:focus-visible {
          outline: 2px solid rgba(255, 255, 255, 0.7);
          outline-offset: 2px;
        }

        @media (max-width: 480px) {
          .ivan-container.position-bottom-right,
          .ivan-container.position-bottom-left {
            bottom: 16px;
            right: 16px;
            left: 16px;
            align-items: stretch;
          }

          .ivan-container.is-open:not(.is-expanded) .ivan-window {
            position: fixed;
            bottom: 16px;
            right: 16px;
            left: 16px;
            width: auto;
            max-width: calc(100vw - 32px);
            height: min(580px, calc(100vh - 32px));
            margin: 0;
            border-radius: var(--ivan-radius-lg);
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
          }

          .ivan-container.is-open.is-expanded .ivan-window {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            width: 100vw;
            height: 100dvh;
            max-width: 100vw;
            max-height: 100dvh;
            margin: 0;
            border-radius: 0;
            border: none;
            z-index: calc(var(--ivan-z-index) + 1);
          }

          .ivan-container.is-open .ivan-launcher {
            display: none !important;
          }
        }
      `;
    }
  }

  if (!customElements.get('ivan-chat-widget')) {
    customElements.define('ivan-chat-widget', IvanChatWidget);
  }

  window.IvanChatWidget = IvanChatWidget;
})();
