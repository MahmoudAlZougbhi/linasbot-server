(function (global) {
  'use strict';

  function createClient(opts) {
    var apiBase = (opts.apiBase || '').replace(/\/$/, '');
    var integrationId = opts.integrationId || opts.widgetKey || '';
    var sessionId = opts.sessionId || ('w' + Math.random().toString(36).slice(2) + Date.now().toString(36));
    var language = (opts.language || (global.navigator && global.navigator.language) || 'en').slice(0, 2);

    function request(method, path, body) {
      return fetch(apiBase + path, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        credentials: 'omit',
        body: body ? JSON.stringify(body) : undefined,
      }).then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) {
            var err = new Error((data && data.message) || 'Request failed');
            err.code = (data && data.error) || 'request_failed';
            err.payload = data;
            throw err;
          }
          return data;
        });
      });
    }

    return {
      sessionId: sessionId,
      bootstrap: function () {
        return request('POST', '/api/web-chat/session', {
          visitor_session_id: sessionId,
          widget_key: integrationId,
          language: language,
        });
      },
      sendMessage: function (content) {
        return request('POST', '/api/web-chat/session/messages', {
          visitor_session_id: sessionId,
          widget_key: integrationId,
          content: content,
          language: language,
        });
      },
      getConfig: function () {
        return request('GET', '/api/web-chat/config?widget_key=' + encodeURIComponent(integrationId));
      },
    };
  }

  global.LinasWebChatSdk = { createClient: createClient };
})(window);
