"""Noindex HTML bridge for Meta Embedded Signup coexistence (v4 extras)."""

from __future__ import annotations

import json

from services.whatsapp_cloud.config import WHATSAPP_COEXISTENCE_FEATURE


def render_embedded_signup_bridge_html(
    *,
    app_id: str,
    state: str,
    config_id: str,
    redirect_uri: str,
    feature: str = WHATSAPP_COEXISTENCE_FEATURE,
) -> str:
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="robots" content="noindex,nofollow"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Connect WhatsApp — Linas AI</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; background: #0b1220; color: #f5f7fb; }
    .card { max-width: 28rem; margin: 0 auto; }
    button { background: #25D366; color: #04210f; border: 0; padding: .85rem 1.2rem; border-radius: 10px; font-weight: 700; width: 100%; }
    p { opacity: .85; line-height: 1.45; }
    .warn { color: #ffd27a; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Connect WhatsApp</h1>
    <p>Continue to Meta to link your existing WhatsApp Business app number (coexistence). You will return to Linas AI.</p>
    <p class="warn">Select your existing WhatsApp Business app number. Do not choose Add a new number.</p>
    <button id="start" type="button">Continue with Meta</button>
    <p id="status"></p>
  </div>
  <script>
    window.fbAsyncInit = function() {
      FB.init({ appId: __APP_ID__, autoLogAppEvents: true, xfbml: true, version: 'v24.0' });
    };
    (function(d, s, id){
      var js, fjs = d.getElementsByTagName(s)[0];
      if (d.getElementById(id)) return;
      js = d.createElement(s); js.id = id;
      js.src = "https://connect.facebook.net/en_US/sdk.js";
      fjs.parentNode.insertBefore(js, fjs);
    }(document, 'script', 'facebook-jssdk'));

    const state = __STATE__;
    const configId = __CONFIG_ID__;
    const featureType = __FEATURE__;
    const redirectUri = __REDIRECT__;
    const statusEl = document.getElementById('status');
    const SESSION_WAIT_MS = 4000;
    const POLL_MS = 150;
    window.__WA_WABA_ID = '';
    window.__WA_PHONE_NUMBER_ID = '';
    window.__WA_SESSION_EVENT = '';
    window.__WA_CANCELLED = false;

    function finish(payload) {
      const q = new URLSearchParams(Object.assign({ state: state }, payload));
      window.location = redirectUri + (redirectUri.includes('?') ? '&' : '?') + q.toString();
    }

    function extractAssets(data) {
      const nested = (data && data.data) ? data.data : {};
      const inner = (nested && nested.data) ? nested.data : {};
      return {
        eventName: String(data.event || nested.event || data.type || ''),
        waba: String(data.waba_id || nested.waba_id || inner.waba_id || ''),
        phone: String(data.phone_number_id || nested.phone_number_id || inner.phone_number_id || '')
      };
    }

    function originAllowed(origin) {
      return origin.indexOf('facebook.com') !== -1 || origin.indexOf('fb.com') !== -1;
    }

    window.addEventListener('message', function(event) {
      if (!originAllowed(String(event.origin || ''))) return;
      try {
        const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
        if (!data) return;
        const assets = extractAssets(data);
        const eventName = assets.eventName;
        if (/CANCEL/i.test(eventName)) {
          window.__WA_CANCELLED = true;
          window.__WA_SESSION_EVENT = eventName;
          return;
        }
        const isFinish = eventName === 'FINISH'
          || eventName === 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING'
          || eventName === 'WA_EMBEDDED_SIGNUP'
          || data.type === 'WA_EMBEDDED_SIGNUP';
        if (!isFinish) return;
        window.__WA_SESSION_EVENT = eventName || 'FINISH';
        if (assets.waba) window.__WA_WABA_ID = assets.waba;
        if (assets.phone) window.__WA_PHONE_NUMBER_ID = assets.phone;
      } catch (e) {}
    });

    function waitThenFinish(code) {
      const started = Date.now();
      (function poll() {
        if (window.__WA_CANCELLED) {
          finish({ error: 'user_cancelled', session_event: window.__WA_SESSION_EVENT || 'CANCEL' });
          return;
        }
        const waba = window.__WA_WABA_ID || '';
        const phone = window.__WA_PHONE_NUMBER_ID || '';
        const sessionEvent = window.__WA_SESSION_EVENT || '';
        if (waba || Date.now() - started >= SESSION_WAIT_MS) {
          finish({
            code: code,
            waba_id: waba,
            phone_number_id: phone,
            session_event: sessionEvent
          });
          return;
        }
        setTimeout(poll, POLL_MS);
      })();
    }

    document.getElementById('start').addEventListener('click', function() {
      statusEl.textContent = 'Opening Meta…';
      if (!configId) { statusEl.textContent = 'Embedded Signup config is missing. Return to Linas AI and try again later.'; return; }
      if (!window.FB) { statusEl.textContent = 'Meta SDK failed to load.'; return; }
      FB.login(function(response) {
        if (!response || response.error) {
          finish({ error: 'login_failed' });
          return;
        }
        const auth = response.authResponse || {};
        const code = auth.code || '';
        if (!code) {
          finish({ error: 'missing_code' });
          return;
        }
        waitThenFinish(code);
      }, {
        config_id: configId,
        response_type: 'code',
        override_default_response_type: true,
        extras: {
          setup: {},
          featureType: featureType,
          sessionInfoVersion: '3'
        }
      });
    });
  </script>
</body>
</html>"""
    return (
        html.replace("__APP_ID__", json.dumps(str(app_id)))
        .replace("__STATE__", json.dumps(str(state)))
        .replace("__CONFIG_ID__", json.dumps(str(config_id)))
        .replace("__FEATURE__", json.dumps(str(feature)))
        .replace("__REDIRECT__", json.dumps(str(redirect_uri)))
    )
