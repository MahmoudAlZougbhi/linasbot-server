(function (global) {
  'use strict';

  function escapeHtml(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function prefersReducedMotion() {
    try {
      return global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) {
      return false;
    }
  }

  function sizeMap(size) {
    if (size === 'compact') return { width: 320, height: 440, launcher: 48, font: 13 };
    if (size === 'large') return { width: 400, height: 600, launcher: 60, font: 15 };
    return { width: 360, height: 520, launcher: 56, font: 14 };
  }

  function radiusMap(corners) {
    if (corners === 'soft') return { panel: 10, bubble: 8, input: 8 };
    if (corners === 'extra_rounded') return { panel: 24, bubble: 18, input: 14 };
    return { panel: 16, bubble: 12, input: 10 };
  }

  function buildStyles(cfg, dims, radii) {
    var a = (cfg && cfg.appearance) || {};
    var theme = a.theme || {};
    var bubbles = a.bubbles || {};
    var layout = a.layout || {};
    var accent = theme.accent_color || '#0D9488';
    var dark = theme.mode === 'dark';
    var panelBg = dark ? '#0F172A' : '#FFFFFF';
    var surface = dark ? '#1E293B' : '#F8FAFC';
    var text = dark ? '#F8FAFC' : '#0F172A';
    var muted = dark ? '#94A3B8' : '#64748B';
    var pos = layout.position === 'bottom_left' ? 'left:20px;right:auto' : 'right:20px;left:auto';
  var motion = prefersReducedMotion() ? '' : 'transition:transform .2s ease,opacity .2s ease;';
    return (
      '#linas-web-chat-root{position:fixed;bottom:20px;' + pos + ';z-index:2147483000;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}' +
      '#linas-web-chat-panel{display:none;width:min(' + dims.width + 'px,calc(100vw - 32px));height:min(' + dims.height + 'px,calc(100vh - 120px));background:' + panelBg + ';border-radius:' + radii.panel + 'px;box-shadow:0 16px 48px rgba(15,23,42,.22);overflow:hidden;flex-direction:column;margin-bottom:12px;border:1px solid ' + (dark ? '#334155' : '#E2E8F0') + ';' + motion + '}' +
      '#linas-web-chat-panel.open{display:flex}' +
      '#linas-web-chat-header{background:' + accent + ';color:#fff;padding:14px 16px;display:flex;align-items:center;gap:10px}' +
      '#linas-web-chat-header-text{flex:1;min-width:0}' +
      '#linas-web-chat-title{font-weight:700;font-size:15px;line-height:1.2}' +
      '#linas-web-chat-subtitle{font-size:12px;opacity:.9;margin-top:2px}' +
      '#linas-web-chat-close{margin-left:auto;background:rgba(255,255,255,.18);border:none;color:#fff;width:28px;height:28px;border-radius:999px;cursor:pointer;font-size:16px}' +
      '#linas-web-chat-messages{flex:1;overflow:auto;padding:14px;background:' + surface + '}' +
      '.linas-web-chat-msg{margin:8px 0;max-width:85%;padding:10px 12px;border-radius:' + radii.bubble + 'px;line-height:1.45;font-size:' + dims.font + 'px;white-space:pre-wrap;word-break:break-word}' +
      '.linas-web-chat-msg.user{margin-left:auto;background:' + (bubbles.visitor_bg || accent) + ';color:' + (bubbles.visitor_text || '#fff') + '}' +
      '.linas-web-chat-msg.assistant{margin-right:auto;background:' + (bubbles.assistant_bg || panelBg) + ';color:' + (bubbles.assistant_text || text) + ';border:1px solid ' + (dark ? '#334155' : '#E2E8F0') + '}' +
      '.linas-web-chat-typing{margin:8px 0;color:' + muted + ';font-size:12px;font-style:italic}' +
      '#linas-web-chat-banner{margin:8px 12px;padding:8px 10px;border-radius:' + radii.bubble + 'px;background:#FEF3C7;color:#92400E;font-size:12px;display:none}' +
      '#linas-web-chat-input-row{display:flex;gap:8px;padding:10px;border-top:1px solid ' + (dark ? '#334155' : '#E2E8F0') + ';background:' + panelBg + '}' +
      '#linas-web-chat-input{flex:1;border:1px solid ' + (dark ? '#475569' : '#CBD5E1') + ';border-radius:' + radii.input + 'px;padding:10px 12px;font-size:' + dims.font + 'px;background:' + (dark ? '#0F172A' : '#fff') + ';color:' + text + '}' +
      '#linas-web-chat-send{border:none;background:' + accent + ';color:#fff;border-radius:' + radii.input + 'px;padding:0 14px;cursor:pointer;font-weight:600}' +
      '#linas-web-chat-launcher{border:none;background:' + accent + ';color:#fff;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.18);display:inline-flex;align-items:center;gap:8px;font-weight:600;font-size:14px;padding:0 16px;height:' + dims.launcher + 'px;border-radius:999px;' + motion + '}' +
      '#linas-web-chat-launcher.icon-only{width:' + dims.launcher + 'px;padding:0;justify-content:center;font-size:22px}' +
      '#linas-web-chat-logo{width:28px;height:28px;border-radius:999px;object-fit:cover;background:rgba(255,255,255,.2)}'
    );
  }

  function errorMessage(code, fallback) {
    var map = {
      WIDGET_DISABLED: 'Website chat is turned off.',
      ORIGIN_NOT_ALLOWED: 'This domain is not allowed for this widget.',
      RATE_LIMIT: 'Too many messages. Please wait a moment.',
      insufficient_credits: 'AI replies are paused until credits are available.',
      web_plan_denied: 'Website chat is not available on this plan.',
      widget_disabled: 'Website chat is turned off.',
      published_cm_missing: 'AI setup is not published yet.',
    };
    return map[code] || fallback || 'Something went wrong. Please try again.';
  }

  function createApi(apiBase, widgetKey) {
    function request(method, path, body) {
      var opts = {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        credentials: 'omit',
      };
      if (body) opts.body = JSON.stringify(body);
      return fetch(apiBase + path, opts).then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) {
            var err = new Error(errorMessage(data && data.error, data && data.message));
            err.code = (data && data.error) || 'request_failed';
            err.status = res.status;
            err.payload = data;
            throw err;
          }
          return data;
        });
      });
    }
    return {
      loadConfig: function () {
        return request('GET', '/api/web-chat/config?widget_key=' + encodeURIComponent(widgetKey));
      },
      heartbeat: function () {
        return request('POST', '/api/web-chat/heartbeat', { widget_key: widgetKey });
      },
      bootstrap: function (sessionId, language) {
        return request('POST', '/api/web-chat/session', {
          visitor_session_id: sessionId,
          widget_key: widgetKey,
          language: language,
        });
      },
      send: function (sessionId, content, language) {
        return request('POST', '/api/web-chat/session/messages', {
          visitor_session_id: sessionId,
          widget_key: widgetKey,
          content: content,
          language: language,
        });
      },
    };
  }

  function init(opts) {
    var widgetKey = opts.widgetKey;
    var apiBase = opts.apiBase;
    var api = createApi(apiBase, widgetKey);
    var storageKey = 'linas_web_chat_session_' + widgetKey.slice(0, 12);
    var sessionId = global.localStorage.getItem(storageKey);
    if (!sessionId || sessionId.length < 8) {
      sessionId = 'w' + Math.random().toString(36).slice(2) + Date.now().toString(36);
      global.localStorage.setItem(storageKey, sessionId);
    }

    var state = { open: false, messages: [], loading: false, config: null, banner: '' };
    var lang = (global.navigator.language || 'en').slice(0, 2);

    function el(tag, className) {
      var node = global.document.createElement(tag);
      if (className) node.className = className;
      return node;
    }

    function applyConfig(cfg) {
      state.config = cfg;
      var appearance = (cfg && cfg.appearance) || {};
      var identity = appearance.identity || {};
      var launcher = appearance.launcher || {};
      var layout = appearance.layout || {};
      var dims = sizeMap(layout.size);
      var radii = radiusMap(layout.corners);
      styleEl.textContent = buildStyles(cfg, dims, radii);
      titleEl.textContent = identity.display_name || 'Chat with us';
      subtitleEl.textContent = identity.subtitle || '';
      subtitleEl.style.display = identity.subtitle ? 'block' : 'none';
      if (identity.logo_url) {
        logoEl.src = identity.logo_url;
        logoEl.style.display = 'block';
      } else {
        logoEl.style.display = 'none';
      }
      if (launcher.mode === 'icon_text') {
        launcherBtn.classList.remove('icon-only');
        launcherLabel.textContent = launcher.text || 'Chat';
        launcherLabel.style.display = 'inline';
      } else {
        launcherBtn.classList.add('icon-only');
        launcherLabel.style.display = 'none';
        launcherBtn.textContent = '💬';
      }
      if (!cfg.ai_available) {
        showBanner(errorMessage(cfg.blocker_code, 'AI replies are unavailable right now.'));
      }
    }

    function showBanner(text) {
      state.banner = text;
      bannerEl.textContent = text;
      bannerEl.style.display = text ? 'block' : 'none';
    }

    function renderMessages() {
      messagesEl.innerHTML = '';
      state.messages.forEach(function (m) {
        var node = el('div', 'linas-web-chat-msg ' + (m.role === 'user' ? 'user' : 'assistant'));
        node.textContent = m.content;
        messagesEl.appendChild(node);
      });
      if (state.loading) {
        var typing = el('div', 'linas-web-chat-typing');
        typing.textContent = 'Typing…';
        messagesEl.appendChild(typing);
      }
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    var styleEl = el('style');
    global.document.head.appendChild(styleEl);

    var root = el('div');
    root.id = 'linas-web-chat-root';

    var panel = el('div');
    panel.id = 'linas-web-chat-panel';

    var header = el('div');
    header.id = 'linas-web-chat-header';
    var logoEl = el('img');
    logoEl.id = 'linas-web-chat-logo';
    logoEl.alt = '';
    var headerText = el('div');
    headerText.id = 'linas-web-chat-header-text';
    var titleEl = el('div');
    titleEl.id = 'linas-web-chat-title';
    var subtitleEl = el('div');
    subtitleEl.id = 'linas-web-chat-subtitle';
    headerText.appendChild(titleEl);
    headerText.appendChild(subtitleEl);
    var closeBtn = el('button');
    closeBtn.id = 'linas-web-chat-close';
    closeBtn.textContent = '×';
    closeBtn.setAttribute('aria-label', 'Close chat');
    header.appendChild(logoEl);
    header.appendChild(headerText);
    header.appendChild(closeBtn);
    panel.appendChild(header);

    var bannerEl = el('div');
    bannerEl.id = 'linas-web-chat-banner';
    panel.appendChild(bannerEl);

    var messagesEl = el('div');
    messagesEl.id = 'linas-web-chat-messages';
    panel.appendChild(messagesEl);

    var inputRow = el('div');
    inputRow.id = 'linas-web-chat-input-row';
    var input = el('input');
    input.id = 'linas-web-chat-input';
    input.placeholder = 'Type a message…';
    var sendBtn = el('button');
    sendBtn.id = 'linas-web-chat-send';
    sendBtn.textContent = 'Send';
    inputRow.appendChild(input);
    inputRow.appendChild(sendBtn);
    panel.appendChild(inputRow);

    var launcherBtn = el('button');
    launcherBtn.id = 'linas-web-chat-launcher';
    launcherBtn.className = 'icon-only';
    launcherBtn.textContent = '💬';
    var launcherLabel = el('span');
    launcherBtn.appendChild(launcherLabel);

    function openPanel() {
      state.open = true;
      panel.classList.add('open');
      if (!state.messages.length) {
        api.bootstrap(sessionId, lang).then(function (data) {
          state.messages = data.messages || [];
          if (data.config) applyConfig(data.config);
          renderMessages();
        }).catch(function (err) {
          showBanner(err.message);
        });
      }
    }

    function closePanel() {
      state.open = false;
      panel.classList.remove('open');
    }

    launcherBtn.addEventListener('click', function () {
      if (state.open) closePanel();
      else openPanel();
    });
    closeBtn.addEventListener('click', closePanel);

    function submit() {
      var text = (input.value || '').trim();
      if (!text || state.loading) return;
      input.value = '';
      state.loading = true;
      state.messages.push({ role: 'user', content: text });
      renderMessages();
      api.send(sessionId, text, lang).then(function (data) {
        state.messages = data.messages || state.messages;
      }).catch(function (err) {
        state.messages.push({ role: 'assistant', content: err.message });
      }).finally(function () {
        state.loading = false;
        renderMessages();
      });
    }

    sendBtn.addEventListener('click', submit);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submit();
      }
    });

    root.appendChild(panel);
    root.appendChild(launcherBtn);
    global.document.body.appendChild(root);

    api.loadConfig().then(function (data) {
      applyConfig(data.config || {});
      api.heartbeat().catch(function () {});
    }).catch(function (err) {
      showBanner(err.message);
      applyConfig({ appearance: {} });
    });
  }

  global.LinasWebChat = { init: init, escapeHtml: escapeHtml };
})(window);
