"""Noindex HTML bridge: wait for both OAuth code and coexistence session."""

from __future__ import annotations

import json

from services.whatsapp_cloud.config import WHATSAPP_COEXISTENCE_FEATURE
from services.whatsapp_cloud.embedded_signup_session import (
    COEXISTENCE_FINISH_EVENT,
    EMBEDDED_SIGNUP_VERSION,
    META_EMBEDDED_SIGNUP_ORIGINS,
    SESSION_INFO_VERSION,
    WA_EMBEDDED_SIGNUP_TYPE,
    coexistence_launch_extras,
)


WAIT_BOTH_MS = 20000


def render_embedded_signup_bridge_html(
    *,
    app_id: str,
    state: str,
    config_id: str,
    redirect_uri: str,
    feature: str = WHATSAPP_COEXISTENCE_FEATURE,
) -> str:
    extras = coexistence_launch_extras()
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="robots" content="noindex,nofollow"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Connect WhatsApp — Linas AI</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 1.25rem; background: #0b1220; color: #f5f7fb; }
    .card { max-width: 28rem; margin: 0 auto; }
    button { background: #25D366; color: #04210f; border: 0; padding: .85rem 1.2rem; border-radius: 10px; font-weight: 700; width: 100%; }
    p { opacity: .9; line-height: 1.5; font-size: 15px; }
    .warn { color: #ffd27a; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Keep using WhatsApp Business App</h1>
    <p>Your WhatsApp Business App and existing chats stay on your phone.</p>
    <p class="warn">Inside Meta, select “Connect a WhatsApp Business app”. Do not select “Create a WhatsApp Business account”, an existing WABA, or Add a new number. Never disconnect or migrate your current number.</p>
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
    const extras = __EXTRAS__;
    const allowedOrigins = new Set(__ORIGINS__);
    const statusEl = document.getElementById('status');
    const WAIT_BOTH_MS = __WAIT_MS__;
    const COEXISTENCE_FINISH = __COEX_FINISH__;
    const SESSION_TYPE = __SESSION_TYPE__;
    const SESSION_VERSION = __SESSION_VERSION__;
    let authCode = '';
    let sessionInfo = null;
    let finished = false;
    let waitTimer = null;

    function finishOnce(payload) {
      if (finished) return;
      finished = true;
      if (waitTimer) { clearTimeout(waitTimer); waitTimer = null; }
      const q = new URLSearchParams(Object.assign({ state: state }, payload));
      window.location = redirectUri + (redirectUri.indexOf('?') >= 0 ? '&' : '?') + q.toString();
    }

    function startWait() {
      if (waitTimer || finished) return;
      waitTimer = setTimeout(function() {
        finishOnce({ error: 'session_timeout' });
      }, WAIT_BOTH_MS);
    }

    function sessionFromMessage(data) {
      const nested = (data && data.data && typeof data.data === 'object') ? data.data : {};
      const inner = (nested.data && typeof nested.data === 'object') ? nested.data : {};
      const versionRaw = (data.version != null) ? data.version : nested.version;
      return {
        type: String(data.type || ''),
        event: String(data.event || nested.event || ''),
        version: String(versionRaw == null ? '' : versionRaw),
        business_id: String(data.business_id || nested.business_id || inner.business_id || ''),
        waba_id: String(data.waba_id || nested.waba_id || inner.waba_id || ''),
        phone_number_id: String(data.phone_number_id || nested.phone_number_id || inner.phone_number_id || ''),
        error_code: String(nested.error_code || data.error_code || inner.error_code || '')
      };
    }

    function maybeComplete() {
      if (finished || !authCode || !sessionInfo) return;
      if (sessionInfo.event !== COEXISTENCE_FINISH || sessionInfo.version !== SESSION_VERSION || !sessionInfo.waba_id) {
        finishOnce({
          error: 'coexistence_flow_required',
          session_event: sessionInfo.event,
          session_version: sessionInfo.version,
          session_type: sessionInfo.type
        });
        return;
      }
      finishOnce({
        code: authCode,
        waba_id: sessionInfo.waba_id,
        phone_number_id: sessionInfo.phone_number_id,
        session_event: sessionInfo.event,
        session_version: sessionInfo.version,
        business_id: sessionInfo.business_id,
        session_type: sessionInfo.type
      });
    }

    window.addEventListener('message', function(event) {
      if (!allowedOrigins.has(String(event.origin || ''))) return;
      var parsed = event.data;
      try {
        if (typeof parsed === 'string') parsed = JSON.parse(parsed);
      } catch (err) {
        return;
      }
      if (!parsed || typeof parsed !== 'object') return;
      if (parsed.type !== SESSION_TYPE) return;
      const info = sessionFromMessage(parsed);
      if (info.event === 'CANCEL' || info.event === 'CANCELLED' || info.event === 'CANCELED') {
        finishOnce({ error: 'user_cancelled', session_event: info.event, session_type: info.type });
        return;
      }
      if (info.event === 'ERROR') {
        const advanced = (info.error_code === '10' || info.error_code === '200' || info.error_code === '294');
        finishOnce({
          error: advanced ? 'meta_advanced_access_required' : 'meta_embedded_signup_error',
          session_event: info.event,
          session_type: info.type
        });
        return;
      }
      sessionInfo = info;
      startWait();
      maybeComplete();
    });

    document.getElementById('start').addEventListener('click', function() {
      statusEl.textContent = 'Opening Meta…';
      if (!configId) { statusEl.textContent = 'Embedded Signup config is missing. Return to Linas AI and try again later.'; return; }
      if (!window.FB) { statusEl.textContent = 'Meta SDK failed to load.'; return; }
      FB.login(function(response) {
        if (!response || response.error) {
          finishOnce({ error: 'login_failed' });
          return;
        }
        if (!response.authResponse) {
          finishOnce({ error: 'user_cancelled' });
          return;
        }
        const code = String((response.authResponse || {}).code || '');
        if (!code) {
          finishOnce({ error: 'missing_code' });
          return;
        }
        authCode = code;
        startWait();
        maybeComplete();
      }, {
        config_id: configId,
        response_type: 'code',
        override_default_response_type: true,
        extras: extras
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
        .replace("__EXTRAS__", json.dumps(extras))
        .replace("__ORIGINS__", json.dumps(sorted(META_EMBEDDED_SIGNUP_ORIGINS)))
        .replace("__WAIT_MS__", str(WAIT_BOTH_MS))
        .replace("__COEX_FINISH__", json.dumps(COEXISTENCE_FINISH_EVENT))
        .replace("__SESSION_TYPE__", json.dumps(WA_EMBEDDED_SIGNUP_TYPE))
        .replace("__SESSION_VERSION__", json.dumps(SESSION_INFO_VERSION))
        .replace("__ES_VERSION__", json.dumps(EMBEDDED_SIGNUP_VERSION))
    )
