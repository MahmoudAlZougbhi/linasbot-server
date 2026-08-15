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

  function boot() {
    if (!window.LinasWebChat) {
      console.error('[Linas Web Chat] Runtime failed to load');
      return;
    }
    window.LinasWebChat.init({ widgetKey: widgetKey, apiBase: apiBase });
  }

  var runtime = document.createElement('script');
  runtime.src = apiBase + '/web-chat/widget-runtime.js';
  runtime.async = true;
  runtime.onload = boot;
  runtime.onerror = function () {
    console.error('[Linas Web Chat] Could not load widget runtime');
  };
  document.head.appendChild(runtime);
})();
