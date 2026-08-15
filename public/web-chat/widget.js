(function () {
  'use strict';

  var script = document.currentScript;
  if (!script) return;

  var widgetKey = script.getAttribute('data-widget-key') || '';
  if (!widgetKey) {
    console.error('[Linas Web Chat] Missing data-widget-key');
    return;
  }

  var apiBase = (function () {
    try {
      var src = new URL(script.src);
      return src.origin;
    } catch (e) {
      return 'https://www.linasaibot.com';
    }
  })();

  var storageKey = 'linas_web_chat_session_' + widgetKey.slice(0, 12);
  var sessionId = localStorage.getItem(storageKey);
  if (!sessionId || sessionId.length < 8) {
    sessionId = 'w' + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(storageKey, sessionId);
  }

  var state = {
    open: false,
    messages: [],
    loading: false,
  };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function css() {
    return (
      '#linas-web-chat-root{position:fixed;bottom:20px;right:20px;z-index:2147483000;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}' +
      '#linas-web-chat-launcher{width:56px;height:56px;border-radius:28px;border:none;background:#0d9488;color:#fff;font-size:24px;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.18)}' +
      '#linas-web-chat-panel{display:none;width:min(360px,calc(100vw - 32px));height:min(520px,calc(100vh - 120px));background:#fff;border-radius:16px;box-shadow:0 12px 40px rgba(0,0,0,.2);overflow:hidden;flex-direction:column;margin-bottom:12px}' +
      '#linas-web-chat-panel.open{display:flex}' +
      '#linas-web-chat-header{background:#0d9488;color:#fff;padding:12px 14px;font-weight:600}' +
      '#linas-web-chat-messages{flex:1;overflow:auto;padding:12px;background:#f8fafc}' +
      '.linas-web-chat-msg{margin:8px 0;max-width:85%;padding:10px 12px;border-radius:12px;line-height:1.4;font-size:14px;white-space:pre-wrap}' +
      '.linas-web-chat-msg.user{margin-left:auto;background:#0d9488;color:#fff}' +
      '.linas-web-chat-msg.assistant{margin-right:auto;background:#fff;border:1px solid #e2e8f0;color:#0f172a}' +
      '#linas-web-chat-input-row{display:flex;gap:8px;padding:10px;border-top:1px solid #e2e8f0;background:#fff}' +
      '#linas-web-chat-input{flex:1;border:1px solid #cbd5e1;border-radius:10px;padding:10px 12px;font-size:14px}' +
      '#linas-web-chat-send{border:none;background:#0d9488;color:#fff;border-radius:10px;padding:0 14px;cursor:pointer;font-weight:600}'
    );
  }

  function renderMessages(container) {
    container.innerHTML = '';
    state.messages.forEach(function (m) {
      container.appendChild(el('div', 'linas-web-chat-msg ' + (m.role === 'user' ? 'user' : 'assistant'), m.content));
    });
    container.scrollTop = container.scrollHeight;
  }

  function api(path, body) {
    return fetch(apiBase + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'omit',
      body: JSON.stringify(body),
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          var err = new Error((data && data.message) || 'Request failed');
          err.payload = data;
          throw err;
        }
        return data;
      });
    });
  }

  function bootstrap() {
    return api('/api/web-chat/session', {
      visitor_session_id: sessionId,
      widget_key: widgetKey,
      language: (navigator.language || 'en').slice(0, 2),
    }).then(function (data) {
      state.messages = data.messages || [];
    });
  }

  function sendMessage(text) {
    state.loading = true;
    state.messages.push({ role: 'user', content: text });
    renderMessages(messagesEl);
    return api('/api/web-chat/session/messages', {
      visitor_session_id: sessionId,
      widget_key: widgetKey,
      content: text,
      language: (navigator.language || 'en').slice(0, 2),
    })
      .then(function (data) {
        state.messages = data.messages || state.messages;
      })
      .finally(function () {
        state.loading = false;
        renderMessages(messagesEl);
      });
  }

  var style = el('style');
  style.textContent = css();
  document.head.appendChild(style);

  var root = el('div');
  root.id = 'linas-web-chat-root';

  var panel = el('div');
  panel.id = 'linas-web-chat-panel';
  panel.appendChild(el('div', null, 'Chat with us'));
  panel.firstChild.id = 'linas-web-chat-header';

  var messagesEl = el('div');
  messagesEl.id = 'linas-web-chat-messages';
  panel.appendChild(messagesEl);

  var inputRow = el('div');
  inputRow.id = 'linas-web-chat-input-row';
  var input = el('input');
  input.id = 'linas-web-chat-input';
  input.placeholder = 'Type a message…';
  var sendBtn = el('button', null, 'Send');
  sendBtn.id = 'linas-web-chat-send';
  inputRow.appendChild(input);
  inputRow.appendChild(sendBtn);
  panel.appendChild(inputRow);

  var launcher = el('button', null, '💬');
  launcher.id = 'linas-web-chat-launcher';

  launcher.addEventListener('click', function () {
    state.open = !state.open;
    panel.classList.toggle('open', state.open);
    if (state.open && !state.messages.length) {
      bootstrap().then(function () {
        renderMessages(messagesEl);
      });
    }
  });

  function submit() {
    var text = (input.value || '').trim();
    if (!text || state.loading) return;
    input.value = '';
    sendMessage(text).catch(function (err) {
      var msg = (err.payload && err.payload.message) || 'Could not send message.';
      state.messages.push({ role: 'assistant', content: msg });
      renderMessages(messagesEl);
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
  root.appendChild(launcher);
  document.body.appendChild(root);
})();
