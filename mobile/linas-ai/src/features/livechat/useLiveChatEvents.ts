import { useEffect, useRef } from 'react';
import { AppState } from 'react-native';

import { API_BASE, ensureAccessToken, refreshAccessToken } from '../../api/client';
import { getStoredAppLanguage } from '../../i18n/languageStore';
import { drainLiveChatSse, type LiveChatSseEvent } from './liveChatSseParse';

const BACKOFF_START_MS = 1_000;
const BACKOFF_MAX_MS = 15_000;

type StreamResult = 'closed' | 'auth' | 'error';

type Signal = {
  cancelled: boolean;
  xhr: XMLHttpRequest | null;
  wake?: () => void;
};

function sleep(ms: number, signal: Signal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.cancelled) {
      resolve();
      return;
    }
    const timer = setTimeout(() => {
      signal.wake = undefined;
      resolve();
    }, ms);
    signal.wake = () => {
      clearTimeout(timer);
      resolve();
    };
  });
}

function openLiveChatSse(
  access: string,
  onEvent: (event: LiveChatSseEvent) => void,
  signal: Signal,
): Promise<StreamResult> {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    signal.xhr = xhr;
    let seen = 0;
    let carry = '';
    let settled = false;

    const finish = (result: StreamResult) => {
      if (settled) return;
      settled = true;
      if (signal.xhr === xhr) signal.xhr = null;
      resolve(result);
    };

    xhr.open('GET', `${API_BASE}/api/live-chat/events`);
    xhr.setRequestHeader('Authorization', `Bearer ${access}`);
    xhr.setRequestHeader('Accept', 'text/event-stream');
    xhr.setRequestHeader('Cache-Control', 'no-cache');
    xhr.setRequestHeader('Accept-Language', getStoredAppLanguage());
    xhr.timeout = 0;

    xhr.onprogress = () => {
      if (signal.cancelled) return;
      const chunk = xhr.responseText.slice(seen);
      seen = xhr.responseText.length;
      const drained = drainLiveChatSse(carry, chunk);
      carry = drained.carry;
      for (const event of drained.events) onEvent(event);
    };

    xhr.onerror = () => finish('error');
    xhr.onabort = () => finish('closed');
    xhr.onload = () => {
      if (carry.trim()) {
        const drained = drainLiveChatSse(carry, '\n\n');
        for (const event of drained.events) onEvent(event);
      }
      if (xhr.status === 401) {
        finish('auth');
        return;
      }
      finish(xhr.status >= 400 ? 'error' : 'closed');
    };

    xhr.send();
  });
}

/**
 * Long-lived Live Chat SSE (XHR GET — React Native has no EventSource).
 * Reconnects with backoff. On `connected`, callers should do one quiet catch-up fetch.
 */
export function useLiveChatEvents(opts: { enabled: boolean; onEvent: (event: LiveChatSseEvent) => void }) {
  const onEventRef = useRef(opts.onEvent);
  onEventRef.current = opts.onEvent;

  useEffect(() => {
    if (!opts.enabled) return;
    const signal: Signal = { cancelled: false, xhr: null };
    let delay = BACKOFF_START_MS;

    const run = async () => {
      while (!signal.cancelled) {
        const access = await ensureAccessToken();
        if (!access || signal.cancelled) return;
        const result = await openLiveChatSse(
          access,
          (event) => {
            if (event.type === 'connected') delay = BACKOFF_START_MS;
            onEventRef.current(event);
          },
          signal,
        );
        if (signal.cancelled) return;
        if (result === 'auth') {
          const refreshed = await refreshAccessToken();
          if (!refreshed) return;
          delay = BACKOFF_START_MS;
          continue;
        }
        await sleep(delay, signal);
        delay = Math.min(delay * 2, BACKOFF_MAX_MS);
      }
    };

    void run();
    const appSub = AppState.addEventListener('change', (state) => {
      if (state !== 'active' || signal.cancelled) return;
      delay = BACKOFF_START_MS;
      signal.xhr?.abort();
      signal.wake?.();
    });
    return () => {
      signal.cancelled = true;
      signal.wake?.();
      signal.xhr?.abort();
      appSub.remove();
    };
  }, [opts.enabled]);
}
