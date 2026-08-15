(function (global) {
  'use strict';

  var shared = global.LinasWebChatShared || {};
  var escapeHtml = shared.escapeHtml;
  var buildStyles = shared.buildStyles;
  var sizeMap = shared.sizeMap;
  var radiusMap = shared.radiusMap;
  var widgetStorageDigest = shared.widgetStorageDigest;
  var errorMessage = shared.errorMessage;
  var newClientMessageKey = shared.newClientMessageKey;
  var createApi = shared.createApi;

  function init(opts) {
    var widgetKey = opts.widgetKey;
    var apiBase = opts.apiBase;
    var api = createApi(apiBase, widgetKey);
    var storageDigest = widgetStorageDigest(widgetKey);
    var sessionIdKey = 'linas_web_chat_session_id_' + storageDigest;
    var sessionAuthKey = 'linas_web_chat_session_auth_' + storageDigest;
    var pollCursorKey = 'linas_web_chat_poll_cursor_' + storageDigest;
    var pendingAckKey = 'linas_web_chat_pending_ack_' + storageDigest;
    var transcriptKey = 'linas_web_chat_transcript_' + storageDigest;
    var sessionId = global.localStorage.getItem(sessionIdKey) || '';
    var sessionAuthority = global.localStorage.getItem(sessionAuthKey) || '';
    var pollCursor = null;
    var pollTimer = null;
    var ackedMessageIds = {};
    var ackQueue = [];

    var state = { open: false, messages: [], loading: false, config: null, banner: '' };
    var lang = (global.navigator.language || 'en').slice(0, 2);
    var pendingSend = null;

    function persistSession(id, authority) {
      sessionId = id;
      sessionAuthority = authority;
      global.localStorage.setItem(sessionIdKey, id);
      global.localStorage.setItem(sessionAuthKey, authority);
    }

    function persistTranscript() {
      try {
        global.localStorage.setItem(transcriptKey, JSON.stringify(state.messages));
      } catch (e) {
        /* ignore quota errors */
      }
    }

    function persistPollCursor() {
      if (pollCursor) {
        global.localStorage.setItem(pollCursorKey, pollCursor);
      } else {
        global.localStorage.removeItem(pollCursorKey);
      }
    }

    function persistPendingAckQueue() {
      if (!ackQueue.length) {
        global.localStorage.removeItem(pendingAckKey);
        return;
      }
      var pending = ackQueue[0].ids.filter(function (id) {
        return !ackedMessageIds[id];
      });
      if (pending.length) {
        global.localStorage.setItem(pendingAckKey, JSON.stringify(pending));
      } else {
        global.localStorage.removeItem(pendingAckKey);
      }
    }

    function loadDurablePollState() {
      try {
        var storedCursor = global.localStorage.getItem(pollCursorKey);
        pollCursor = storedCursor || null;
        var pendingRaw = global.localStorage.getItem(pendingAckKey);
        if (pendingRaw) {
          var pendingIds = JSON.parse(pendingRaw);
          if (pendingIds && pendingIds.length) {
            ackQueue.push({ ids: pendingIds, cursor: pollCursor });
          }
        }
        var transcriptRaw = global.localStorage.getItem(transcriptKey);
        if (transcriptRaw) {
          var transcript = JSON.parse(transcriptRaw);
          if (transcript && transcript.length) {
            state.messages = transcript;
          }
        }
      } catch (e) {
        /* ignore corrupt local state */
      }
    }

    function clearSession() {
      sessionId = '';
      sessionAuthority = '';
      pollCursor = null;
      ackQueue = [];
      ackedMessageIds = {};
      global.localStorage.removeItem(sessionIdKey);
      global.localStorage.removeItem(sessionAuthKey);
      global.localStorage.removeItem(pollCursorKey);
      global.localStorage.removeItem(pendingAckKey);
      global.localStorage.removeItem(transcriptKey);
    }

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
        if (m.id) node.setAttribute('data-message-id', m.id);
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

    function mergeServerMessages(serverMessages) {
      if (!serverMessages || !serverMessages.length) return false;
      var known = {};
      state.messages.forEach(function (m) {
        if (m.id) known[m.id] = true;
      });
      var added = false;
      serverMessages.forEach(function (m) {
        if (m.id && known[m.id]) return;
        state.messages.push({ id: m.id, role: m.role, content: m.content });
        added = true;
      });
      if (added) {
        persistTranscript();
      }
      return added;
    }

    function flushAckQueue() {
      if (!sessionId || !sessionAuthority || !ackQueue.length) {
        return Promise.resolve(true);
      }
      var batch = ackQueue[0];
      var ids = batch.ids.filter(function (id) {
        return !ackedMessageIds[id];
      });
      if (!ids.length) {
        ackQueue.shift();
        pollCursor = batch.cursor || pollCursor;
        persistPollCursor();
        persistPendingAckQueue();
        return flushAckQueue();
      }
      return api.ack(sessionId, sessionAuthority, ids).then(function () {
        ids.forEach(function (id) {
          ackedMessageIds[id] = true;
        });
        ackQueue.shift();
        pollCursor = batch.cursor || pollCursor;
        persistPollCursor();
        persistPendingAckQueue();
        return flushAckQueue();
      }).catch(function (err) {
        if (err.code === 'SESSION_AUTHORITY_INVALID' || err.code === 'SESSION_NOT_FOUND') {
          clearSession();
        }
        return false;
      });
    }

    function pollFollowups() {
      if (!sessionId || !sessionAuthority) return Promise.resolve();
      return flushAckQueue().then(function (ready) {
        if (!ready) return;
        return api.poll(sessionId, sessionAuthority, pollCursor).then(function (data) {
          var incoming = data.messages || [];
          if (!incoming.length) return;
          mergeServerMessages(incoming);
          renderMessages();
          var ids = incoming.map(function (m) { return m.id; }).filter(Boolean);
          var pendingAck = ids.filter(function (id) { return !ackedMessageIds[id]; });
          if (!pendingAck.length) return;
          ackQueue.push({ ids: pendingAck, cursor: data.cursor || pollCursor });
          persistPendingAckQueue();
          return flushAckQueue();
        }).catch(function (err) {
          if (err.code === 'SESSION_AUTHORITY_INVALID' || err.code === 'SESSION_NOT_FOUND') {
            clearSession();
          }
        });
      });
    }

    function startPolling() {
      if (pollTimer) return;
      pollFollowups();
      pollTimer = global.setInterval(pollFollowups, 5000);
    }

    function stopPolling() {
      if (pollTimer) {
        global.clearInterval(pollTimer);
        pollTimer = null;
      }
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

    function bootstrapSession() {
      return api.bootstrap(lang).then(function (data) {
        persistSession(data.session_id, data.session_authority);
        state.messages = data.messages || [];
        pollCursor = null;
        ackQueue = [];
        ackedMessageIds = {};
        persistPollCursor();
        persistPendingAckQueue();
        persistTranscript();
        if (data.config) applyConfig(data.config);
        renderMessages();
        startPolling();
      });
    }

    function openPanel() {
      state.open = true;
      panel.classList.add('open');
      if (!sessionId || !sessionAuthority) {
        bootstrapSession().catch(function (err) {
          showBanner(err.message);
        });
        return;
      }
      startPolling();
      if (!state.messages.length) {
        pollFollowups();
      }
    }

    function closePanel() {
      state.open = false;
      panel.classList.remove('open');
      stopPolling();
    }

    launcherBtn.addEventListener('click', function () {
      if (state.open) closePanel();
      else openPanel();
    });
    closeBtn.addEventListener('click', closePanel);

    function deliverSend(text, clientMessageKey, attempt) {
      var sendPromise = sessionId && sessionAuthority
        ? api.send(sessionId, sessionAuthority, text, lang, clientMessageKey)
        : bootstrapSession().then(function () {
          return api.send(sessionId, sessionAuthority, text, lang, clientMessageKey);
        });
      return sendPromise.then(function (data) {
        pendingSend = null;
        state.messages = data.messages || state.messages;
        persistTranscript();
      }).catch(function (err) {
        if (err.code === 'SESSION_AUTHORITY_INVALID' || err.code === 'SESSION_NOT_FOUND') {
          clearSession();
          pendingSend = null;
          state.messages.push({ role: 'assistant', content: err.message });
          return;
        }
        if (attempt < 1 && (!err.code || err.code === 'request_failed')) {
          return deliverSend(text, clientMessageKey, attempt + 1);
        }
        pendingSend = null;
        state.messages.push({ role: 'assistant', content: err.message });
      });
    }

    function submit() {
      var text = (input.value || '').trim();
      if (!text || state.loading) return;
      input.value = '';
      state.loading = true;
      var clientMessageKey = pendingSend && pendingSend.text === text
        ? pendingSend.clientMessageKey
        : newClientMessageKey();
      pendingSend = { text: text, clientMessageKey: clientMessageKey };
      state.messages.push({ role: 'user', content: text });
      renderMessages();
      deliverSend(text, clientMessageKey, 0).finally(function () {
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

    loadDurablePollState();
    if (state.messages.length) {
      renderMessages();
    }

    api.loadConfig().then(function (data) {
      applyConfig(data.config || {});
      api.heartbeat().catch(function () {});
    }).catch(function (err) {
      showBanner(err.message);
      applyConfig({ appearance: {} });
    });
  }

  global.LinasWebChat = {
    init: init,
    escapeHtml: escapeHtml,
    widgetStorageDigest: widgetStorageDigest,
    newClientMessageKey: newClientMessageKey,
  };
})(window);
