/** Shared browser/widget harness for web_chat_widget_protocol.mjs. */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

export const apiBase = (process.env.WEB_CHAT_API_BASE || '').replace(/\/$/, '');
export const widgetKey = process.env.WEB_CHAT_WIDGET_KEY || '';
export const origin = process.env.WEB_CHAT_ORIGIN || 'https://shop.example.com';
export const scenario = process.env.WEB_CHAT_SCENARIO || 'bootstrap_followup_ack_reload';

export function makeStorage(seed) {
  const store = seed ? { ...seed } : {};
  return {
    getItem(k) {
      return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null;
    },
    setItem(k, v) {
      store[k] = String(v);
    },
    removeItem(k) {
      delete store[k];
    },
    _dump() {
      return { ...store };
    },
  };
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function flushPromises(rounds = 6) {
  for (let i = 0; i < rounds; i += 1) {
    await new Promise((resolve) => setImmediate(resolve));
  }
}

export function createBrowserFetch({ origin: pageOrigin, hooks = {}, pollResponses = [], ackRequests = [], ackAttempts = [] }) {
  let pollFailuresLeft = hooks.failPollCount || 0;
  let ackFailuresLeft = hooks.failAckCount || 0;
  let ackDelayMs = hooks.ackDelayMs || 0;

  return async function browserFetch(url, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (!headers.Origin && !headers.origin) {
      headers.Origin = pageOrigin;
    }
    const path = String(url).replace(apiBase, '');
    if (path.includes('/session/poll') && pollFailuresLeft > 0) {
      pollFailuresLeft -= 1;
      throw new Error('simulated_poll_failure');
    }
    if (path.includes('/session/ack') && opts.body) {
      try {
        const payload = JSON.parse(String(opts.body));
        const ids = Array.isArray(payload.message_ids) ? [...payload.message_ids] : [];
        ackAttempts.push(ids);
      } catch (_err) {
        ackAttempts.push([]);
      }
    }
    if (path.includes('/session/ack') && ackFailuresLeft > 0) {
      ackFailuresLeft -= 1;
      return {
        ok: false,
        status: 500,
        json: async () => ({ error: 'simulated_ack_failure', message: 'simulated_ack_failure' }),
      };
    }
    if (path.includes('/session/ack') && ackDelayMs > 0) {
      await sleep(ackDelayMs);
    }
    if (path.includes('/session/ack') && opts.body) {
      try {
        const payload = JSON.parse(String(opts.body));
        ackRequests.push(Array.isArray(payload.message_ids) ? [...payload.message_ids] : []);
      } catch (_err) {
        ackRequests.push([]);
      }
    }
    const response = await fetch(url, { ...opts, headers });
    if (path.includes('/session/poll') && response.ok) {
      const clone = response.clone();
      try {
        pollResponses.push(await clone.json());
      } catch (_err) {
        pollResponses.push(null);
      }
    }
    return response;
  };
}

export function createBrowserEnv({ localStorage, fetchImpl }) {
  const elementsById = new Map();
  const intervals = new Map();
  let nextTimerId = 1;

  function register(el) {
    if (el.id) {
      elementsById.set(el.id, el);
    }
  }

  function createElement(tag) {
    const el = {
      tagName: String(tag || '').toUpperCase(),
      _id: '',
      className: '',
      classList: {
        _classes: new Set(),
        add(cls) {
          this._classes.add(cls);
          el.className = [...this._classes].join(' ');
        },
        remove(cls) {
          this._classes.delete(cls);
          el.className = [...this._classes].join(' ');
        },
        contains(cls) {
          return this._classes.has(cls);
        },
      },
      style: {},
      textContent: '',
      innerHTML: '',
      value: '',
      src: '',
      alt: '',
      children: [],
      parentNode: null,
      _listeners: {},
      setAttribute(name, value) {
        if (name === 'id') {
          el.id = String(value);
          return;
        }
        if (name === 'data-message-id') {
          el._messageId = String(value);
          return;
        }
        if (name === 'class') {
          el.className = String(value);
          el.classList._classes = new Set(el.className.split(/\s+/).filter(Boolean));
        }
        if (name === 'aria-label') {
          el._ariaLabel = String(value);
        }
      },
      getAttribute(name) {
        if (name === 'data-message-id') {
          return el._messageId || null;
        }
        if (name === 'id') {
          return el.id || null;
        }
        return null;
      },
      appendChild(child) {
        child.parentNode = el;
        el.children.push(child);
        register(child);
        return child;
      },
      addEventListener(type, fn) {
        if (!el._listeners[type]) {
          el._listeners[type] = [];
        }
        el._listeners[type].push(fn);
      },
      dispatch(type, event) {
        const listeners = el._listeners[type] || [];
        for (const fn of listeners) {
          fn(event);
        }
      },
      querySelector(selector) {
        if (selector.startsWith('#') && elementsById.has(selector.slice(1))) {
          return elementsById.get(selector.slice(1));
        }
        const walk = (node) => {
          if (selector === '.linas-web-chat-msg' && node.className && node.className.includes('linas-web-chat-msg')) {
            return node;
          }
          for (const child of node.children || []) {
            const hit = walk(child);
            if (hit) {
              return hit;
            }
          }
          return null;
        };
        for (const node of elementsById.values()) {
          const hit = walk(node);
          if (hit) {
            return hit;
          }
        }
        return null;
      },
      querySelectorAll(selector) {
        const hits = [];
        const walk = (node) => {
          if (selector === '.linas-web-chat-msg' && node.className && node.className.includes('linas-web-chat-msg')) {
            hits.push(node);
          }
          for (const child of node.children || []) {
            walk(child);
          }
        };
        for (const node of elementsById.values()) {
          walk(node);
        }
        return hits;
      },
    };
    Object.defineProperty(el, 'id', {
      enumerable: true,
      get() {
        return el._id;
      },
      set(value) {
        el._id = String(value || '');
        if (el._id) {
          register(el);
        }
      },
    });
    Object.defineProperty(el, 'innerHTML', {
      enumerable: true,
      get() {
        return '';
      },
      set(value) {
        if (!value) {
          el.children = [];
        }
      },
    });
    register(el);
    return el;
  }

  const document = {
    head: createElement('head'),
    body: createElement('body'),
    createElement,
    getElementById(id) {
      return elementsById.get(id) || null;
    },
  };

  const sandbox = {
    window: null,
    document,
    localStorage: localStorage || makeStorage(),
    navigator: { language: 'en' },
    matchMedia: () => ({ matches: false }),
    setInterval(fn, _ms) {
      const id = nextTimerId;
      nextTimerId += 1;
      intervals.set(id, fn);
      return id;
    },
    clearInterval(id) {
      intervals.delete(id);
    },
    fetch: fetchImpl,
    console,
  };
  sandbox.window = sandbox;

  return { sandbox, intervals, pollResponses: fetchImpl.pollResponses };
}

export function loadRuntime(sandbox) {
  const here = dirname(fileURLToPath(import.meta.url));
  const publicRoot = join(here, '..', '..', 'public', 'web-chat');
  const sharedPath = join(publicRoot, 'widget-runtime-shared.js');
  const runtimePath = join(publicRoot, 'widget-runtime.js');
  vm.runInNewContext(readFileSync(sharedPath, 'utf8'), sandbox, { filename: sharedPath });
  vm.runInNewContext(readFileSync(runtimePath, 'utf8'), sandbox, { filename: runtimePath });
  if (!sandbox.LinasWebChat || typeof sandbox.LinasWebChat.init !== 'function') {
    throw new Error('widget runtime did not export LinasWebChat.init');
  }
  return sandbox.LinasWebChat;
}

export function sessionKeys(runtime, key) {
  const digest = runtime.widgetStorageDigest(key);
  return {
    digest,
    sessionIdKey: `linas_web_chat_session_id_${digest}`,
    sessionAuthKey: `linas_web_chat_session_auth_${digest}`,
  };
}

export function readStoredSession(localStorage, runtime, key) {
  const keys = sessionKeys(runtime, key);
  return {
    session_id: localStorage.getItem(keys.sessionIdKey) || '',
    session_authority: localStorage.getItem(keys.sessionAuthKey) || '',
    digest: keys.digest,
    sessionIdKey: keys.sessionIdKey,
    sessionAuthKey: keys.sessionAuthKey,
  };
}

export function seedPresetSession(localStorage, runtime, key) {
  const presetId = process.env.WEB_CHAT_SESSION_ID || '';
  const presetAuth = process.env.WEB_CHAT_SESSION_AUTHORITY || '';
  if (!presetId || !presetAuth) {
    return false;
  }
  const keys = sessionKeys(runtime, key);
  localStorage.setItem(keys.sessionIdKey, presetId);
  localStorage.setItem(keys.sessionAuthKey, presetAuth);
  return true;
}

export function getRenderedMessages(document) {
  const container = document.getElementById('linas-web-chat-messages');
  if (!container) {
    return [];
  }
  return container.children
    .filter((node) => node.className && node.className.includes('linas-web-chat-msg'))
    .map((node) => ({
      id: node.getAttribute('data-message-id') || '',
      role: node.className.includes('user') ? 'user' : 'assistant',
      content: node.textContent || '',
    }));
}

export async function waitFor(predicate, { timeoutMs = 15000, intervalMs = 40 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await flushPromises();
    if (predicate()) {
      return;
    }
    await sleep(intervalMs);
  }
  throw new Error('waitFor_timeout');
}

export class WidgetDriver {
  constructor(env, runtime, widgetKeyValue) {
    this.env = env;
    this.runtime = runtime;
    this.widgetKey = widgetKeyValue;
    this.sandbox = env.sandbox;
    this.document = env.sandbox.document;
    this.intervals = env.intervals;
  }

  static async create(apiBaseUrl, key, { localStorage, fetchHooks } = {}) {
    const pollResponses = [];
    const ackRequests = [];
    const ackAttempts = [];
    const fetchImpl = createBrowserFetch({
      origin,
      hooks: fetchHooks || {},
      pollResponses,
      ackRequests,
      ackAttempts,
    });
    fetchImpl.pollResponses = pollResponses;
    fetchImpl.ackRequests = ackRequests;
    fetchImpl.ackAttempts = ackAttempts;
    const env = createBrowserEnv({ localStorage: localStorage || makeStorage(), fetchImpl });
    const runtime = loadRuntime(env.sandbox);
    seedPresetSession(env.sandbox.localStorage, runtime, key);
    runtime.init({ apiBase: apiBaseUrl, widgetKey: key });
    await flushPromises();
    return new WidgetDriver({ sandbox: env.sandbox, intervals: env.intervals, pollResponses }, runtime, key);
  }

  clickLauncher() {
    const launcher = this.document.getElementById('linas-web-chat-launcher');
    if (!launcher) {
      throw new Error('launcher_missing');
    }
    launcher.dispatch('click', { preventDefault() {} });
  }

  async openChat() {
    this.clickLauncher();
    await flushPromises();
    await waitFor(() => {
      const stored = readStoredSession(this.sandbox.localStorage, this.runtime, this.widgetKey);
      return Boolean(stored.session_id && stored.session_authority);
    });
    await flushPromises();
  }

  async sendMessage(text) {
    const input = this.document.getElementById('linas-web-chat-input');
    const sendBtn = this.document.getElementById('linas-web-chat-send');
    if (!input || !sendBtn) {
      throw new Error('send_controls_missing');
    }
    input.value = text;
    sendBtn.dispatch('click', { preventDefault() {} });
    await waitFor(() => !this.document.querySelector('.linas-web-chat-typing'));
    await flushPromises();
  }

  async tickPoll() {
    for (const fn of this.intervals.values()) {
      const pending = fn();
      if (pending && typeof pending.then === 'function') {
        await pending;
      }
    }
    await sleep(100);
    await flushPromises(10);
  }

  getMessages() {
    return getRenderedMessages(this.document);
  }

  getStoredSession() {
    return readStoredSession(this.sandbox.localStorage, this.runtime, this.widgetKey);
  }

  async reload(apiBaseUrl) {
    for (const id of [...this.intervals.keys()]) {
      this.sandbox.clearInterval(id);
    }
    this.intervals.clear();
    const storageDump = this.sandbox.localStorage._dump();
    return WidgetDriver.create(apiBaseUrl, this.widgetKey, { localStorage: makeStorage(storageDump) });
  }
}
