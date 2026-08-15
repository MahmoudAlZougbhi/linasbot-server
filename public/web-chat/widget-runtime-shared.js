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

  function widgetStorageDigest(widgetKey) {
    var h1 = 2166136261;
    var h2 = 374761393;
    var key = String(widgetKey || '');
    for (var i = 0; i < key.length; i++) {
      var c = key.charCodeAt(i);
      h1 ^= c;
      h1 = Math.imul(h1, 16777619);
      h2 ^= c;
      h2 = Math.imul(h2, 2246822519);
    }
    return (h1 >>> 0).toString(16).padStart(8, '0') + (h2 >>> 0).toString(16).padStart(8, '0');
  }

  function errorMessage(code, fallback) {
    var map = {
      WIDGET_DISABLED: 'Website chat is turned off.',
      ORIGIN_NOT_ALLOWED: 'This domain is not allowed for this widget.',
      RATE_LIMIT: 'Too many messages. Please wait a moment.',
      SESSION_AUTHORITY_INVALID: 'Your chat session expired. Please reopen chat.',
      SESSION_BOUNDARY: 'This chat session is not valid for this widget.',
      insufficient_credits: 'AI replies are paused until credits are available.',
      web_plan_denied: 'Website chat is not available on this plan.',
      widget_disabled: 'Website chat is turned off.',
      published_cm_missing: 'AI setup is not published yet.',
    };
    return map[code] || fallback || 'Something went wrong. Please try again.';
  }

  function newClientMessageKey() {
    try {
      if (global.crypto && typeof global.crypto.randomUUID === 'function') {
        return global.crypto.randomUUID();
      }
    } catch (e) {
      /* fall through */
    }
    return 'cmk-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
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
      bootstrap: function (language) {
        return request('POST', '/api/web-chat/session', {
          widget_key: widgetKey,
          language: language,
        });
      },
      send: function (sessionId, sessionAuthority, content, language, clientMessageKey) {
        return request('POST', '/api/web-chat/session/messages', {
          session_id: sessionId,
          session_authority: sessionAuthority,
          widget_key: widgetKey,
          content: content,
          language: language,
          client_message_key: clientMessageKey,
        });
      },
      poll: function (sessionId, sessionAuthority, cursor) {
        return request('POST', '/api/web-chat/session/poll', {
          session_id: sessionId,
          session_authority: sessionAuthority,
          widget_key: widgetKey,
          cursor: cursor || null,
        });
      },
      ack: function (sessionId, sessionAuthority, messageIds) {
        return request('POST', '/api/web-chat/session/ack', {
          session_id: sessionId,
          session_authority: sessionAuthority,
          widget_key: widgetKey,
          message_ids: messageIds,
        });
      },
    };
  }

  global.LinasWebChatShared = {
    escapeHtml: escapeHtml,
    buildStyles: buildStyles,
    sizeMap: sizeMap,
    radiusMap: radiusMap,
    widgetStorageDigest: widgetStorageDigest,
    errorMessage: errorMessage,
    newClientMessageKey: newClientMessageKey,
    createApi: createApi,
  };
})(window);
