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
      return new URL(script.src).origin;
    } catch (e) {
      return 'https://www.linasaibot.com';
    }
  })();

  function loadScript(src, onload) {
    var tag = document.createElement('script');
    tag.src = src;
    tag.async = false;
    tag.onload = onload;
    tag.onerror = function () {
      console.error('[Linas Web Chat] Could not load widget runtime script: ' + src);
    };
    document.head.appendChild(tag);
  }

  function boot() {
    if (!window.LinasWebChat) {
      console.error('[Linas Web Chat] Runtime failed to load');
      return;
    }
    window.LinasWebChat.init({ widgetKey: widgetKey, apiBase: apiBase });
  }

  loadScript(apiBase + '/web-chat/widget-runtime-shared.js', function () {
    loadScript(apiBase + '/web-chat/widget-runtime.js', boot);
  });
})();
