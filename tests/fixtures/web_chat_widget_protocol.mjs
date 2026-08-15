#!/usr/bin/env node
/**
 * Drives shipped public/web-chat/widget-runtime.js against live HTTP routes.
 * No duplicated createApi — only browser simulation (DOM, localStorage, fetch Origin).
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const apiBase = (process.env.WEB_CHAT_API_BASE || '').replace(/\/$/, '');
const widgetKey = process.env.WEB_CHAT_WIDGET_KEY || '';
const origin = process.env.WEB_CHAT_ORIGIN || 'https://shop.example.com';
const scenario = process.env.WEB_CHAT_SCENARIO || 'bootstrap_followup_ack_reload';

if (!apiBase || !widgetKey) {
  console.error(JSON.stringify({ ok: false, error: 'missing_env' }));
  process.exit(1);
}

function makeStorage(seed) {
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

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function flushPromises(rounds = 6) {
  for (let i = 0; i < rounds; i += 1) {
    await new Promise((resolve) => setImmediate(resolve));
  }
}

function createBrowserFetch({ origin: pageOrigin, hooks = {}, pollResponses = [], ackRequests = [], ackAttempts = [] }) {
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

function createBrowserEnv({ localStorage, fetchImpl }) {
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

function loadRuntime(sandbox) {
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

function sessionKeys(runtime, key) {
  const digest = runtime.widgetStorageDigest(key);
  return {
    digest,
    sessionIdKey: `linas_web_chat_session_id_${digest}`,
    sessionAuthKey: `linas_web_chat_session_auth_${digest}`,
  };
}

function readStoredSession(localStorage, runtime, key) {
  const keys = sessionKeys(runtime, key);
  return {
    session_id: localStorage.getItem(keys.sessionIdKey) || '',
    session_authority: localStorage.getItem(keys.sessionAuthKey) || '',
    digest: keys.digest,
    sessionIdKey: keys.sessionIdKey,
    sessionAuthKey: keys.sessionAuthKey,
  };
}

function seedPresetSession(localStorage, runtime, key) {
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

function getRenderedMessages(document) {
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

async function waitFor(predicate, { timeoutMs = 15000, intervalMs = 40 } = {}) {
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

class WidgetDriver {
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

async function scenarioBootstrapFollowupAckReload() {
  const widget = await WidgetDriver.create(apiBase, widgetKey);
  await widget.openChat();
  if (!(process.env.WEB_CHAT_SESSION_ID && process.env.WEB_CHAT_SESSION_AUTHORITY)) {
    await widget.sendMessage('Hello acceptance');
  }
  await widget.tickPoll();
  await waitFor(() => widget.getMessages().some((m) => m.role === 'assistant'));
  const beforeAck = widget.getMessages();
  await widget.tickPoll();
  await sleep(80);
  await widget.tickPoll();
  const reloaded = await widget.reload(apiBase);
  await reloaded.openChat();
  await reloaded.tickPoll();
  const reloadMessages = reloaded.getMessages().filter((m) => m.role === 'assistant');
  const reloadIds = reloadMessages.map((m) => m.id).filter(Boolean);
  return {
    ok: true,
    scenario,
    session_id: widget.getStoredSession().session_id,
    assistant_before_reload: beforeAck.filter((m) => m.role === 'assistant').length,
    reload_assistant_messages: reloadMessages,
    reload_assistant_count: reloadMessages.length,
    reload_assistant_ids: reloadIds,
    reload_poll: reloadMessages,
  };
}

async function scenarioLostPollAck() {
  const widget = await WidgetDriver.create(apiBase, widgetKey, {
    fetchHooks: { failPollCount: 1, failAckCount: 1, ackDelayMs: 120 },
  });
  await widget.openChat();
  await sleep(80);
  await widget.tickPoll();
  const pollCountAfterLoss = widget.env.pollResponses.length;
  await widget.tickPoll();
  const successfulPolls = widget.env.pollResponses.filter((entry) => entry);
  const firstPollCount = pollCountAfterLoss === 0
    ? 0
    : (widget.env.pollResponses[pollCountAfterLoss - 1]?.messages || []).length;
  const retryPollCount = (successfulPolls[0]?.messages || []).length;
  await waitFor(() => widget.getMessages().some((m) => m.role === 'assistant'), { timeoutMs: 20000 });
  const preReloadAssistant = widget.getMessages().filter((m) => m.role === 'assistant');
  const preReloadIds = preReloadAssistant.map((m) => m.id).filter(Boolean);
  await sleep(250);
  await widget.tickPoll();
  const afterPoll = widget.env.pollResponses[widget.env.pollResponses.length - 1];
  const afterAckCount = (afterPoll?.messages || []).length;
  const ackRequests = widget.env.sandbox.fetch.ackRequests || [];
  const reloaded = await widget.reload(apiBase);
  await reloaded.openChat();
  await reloaded.tickPoll();
  const reloadMessages = reloaded.getMessages().filter((m) => m.role === 'assistant');
  const reloadIds = reloadMessages.map((m) => m.id).filter(Boolean);
  const uniqueReloadIds = [...new Set(reloadIds)];
  const delivered = preReloadAssistant.length === 1 && preReloadIds.length === 1;
  const stableIdMerge = reloadIds.length === 1 && reloadIds[0] === preReloadIds[0];
  const noDuplicateInsertion = reloadMessages.length === 1 && uniqueReloadIds.length === 1;
  const idempotentAck = ackRequests.length <= 2
    && ackRequests.every((ids) => ids.length <= 1)
    && (ackRequests.length === 0 || ackRequests[0][0] === preReloadIds[0]);
  return {
    ok: delivered && retryPollCount >= 1 && afterAckCount === 0 && stableIdMerge && noDuplicateInsertion && idempotentAck,
    scenario,
    first_poll_count: firstPollCount,
    retry_poll_count: retryPollCount,
    after_ack_count: afterAckCount,
    reload_assistant_count: reloadMessages.length,
    pre_reload_assistant_ids: preReloadIds,
    reload_assistant_ids: reloadIds,
    ack_requests: ackRequests,
    message_ids: preReloadIds,
  };
}

async function scenarioRepeatedAckFailureRecovery() {
  const widget = await WidgetDriver.create(apiBase, widgetKey, {
    fetchHooks: { failAckCount: 3 },
  });
  await widget.openChat();
  await sleep(80);
  await widget.tickPoll();
  await waitFor(() => widget.getMessages().some((m) => m.role === 'assistant'), { timeoutMs: 20000 });
  const assistant = widget.getMessages().filter((m) => m.role === 'assistant');
  const assistantIds = assistant.map((m) => m.id).filter(Boolean);
  for (let i = 0; i < 6; i += 1) {
    await widget.tickPoll();
    await sleep(80);
  }
  const ackRequests = widget.env.sandbox.fetch.ackRequests || [];
  const ackAttempts = widget.env.sandbox.fetch.ackAttempts || [];
  const afterPoll = widget.env.pollResponses[widget.env.pollResponses.length - 1];
  const afterAckCount = (afterPoll?.messages || []).length;
  const followupAssistant = assistant.filter((m) => m.content === 'Node harness follow-up');
  return {
    ok:
      followupAssistant.length === 1
      && assistantIds.length >= 1
      && ackAttempts.length >= 4
      && ackRequests.length >= 1
      && afterAckCount === 0
      && ackAttempts.every((ids) => ids.length <= 1),
    scenario,
    assistant_ids: assistantIds,
    ack_requests: ackRequests,
    ack_attempts: ackAttempts,
    after_ack_count: afterAckCount,
    followup_assistant_count: followupAssistant.length,
  };
}

async function scenarioTwoWidgetsSamePrefix() {
  const prefix = widgetKey.slice(0, 12);
  const keyA = `${prefix}aaaaaaaaaaaa`;
  const keyB = `${prefix}bbbbbbbbbbbb`;
  const sharedStorage = makeStorage();
  const runtimeProbe = loadRuntime(createBrowserEnv({ fetchImpl: createBrowserFetch({ origin }) }).sandbox);
  const digestA = runtimeProbe.widgetStorageDigest(keyA);
  const digestB = runtimeProbe.widgetStorageDigest(keyB);
  if (digestA === digestB) {
    return { ok: false, scenario, error: 'digest_collision' };
  }

  const widgetA = await WidgetDriver.create(apiBase, keyA, { localStorage: sharedStorage });
  await widgetA.openChat();
  const sessionA = widgetA.getStoredSession();

  const widgetB = await WidgetDriver.create(apiBase, keyB, { localStorage: sharedStorage });
  await widgetB.openChat();
  const sessionB = widgetB.getStoredSession();

  const reloadedA = await widgetA.reload(apiBase);
  await reloadedA.openChat();
  const sessionAAfterReload = reloadedA.getStoredSession();
  const reloadedB = await widgetB.reload(apiBase);
  await reloadedB.openChat();
  const sessionBAfterReload = reloadedB.getStoredSession();

  const dump = sharedStorage._dump();
  const idA = dump[sessionA.sessionIdKey] || '';
  const idB = dump[sessionB.sessionIdKey] || '';
  const crossRead =
    sessionAAfterReload.session_id === sessionB.session_id ||
    sessionBAfterReload.session_id === sessionA.session_id;
  const overwrite = idA !== sessionA.session_id || idB !== sessionB.session_id;

  return {
    ok:
      sessionA.session_id &&
      sessionB.session_id &&
      sessionA.session_id !== sessionB.session_id &&
      sessionAAfterReload.session_id === sessionA.session_id &&
      sessionBAfterReload.session_id === sessionB.session_id &&
      !crossRead &&
      !overwrite,
    scenario,
    prefix,
    session_a: sessionA.session_id,
    session_b: sessionB.session_id,
    digest_a: digestA,
    digest_b: digestB,
    storage_keys: Object.keys(dump),
    shared_prefix_collision: false,
    cross_read: crossRead,
    overwrite,
  };
}

async function main() {
  let result;
  if (scenario === 'bootstrap_followup_ack_reload') {
    result = await scenarioBootstrapFollowupAckReload();
  } else if (scenario === 'lost_poll_ack') {
    result = await scenarioLostPollAck();
  } else if (scenario === 'repeated_ack_failure_recovery') {
    result = await scenarioRepeatedAckFailureRecovery();
  } else if (scenario === 'two_widgets_same_prefix') {
    result = await scenarioTwoWidgetsSamePrefix();
  } else {
    result = { ok: false, error: 'unknown_scenario', scenario };
  }
  console.log(JSON.stringify(result));
}

main().catch((err) => {
  console.error(JSON.stringify({ ok: false, error: String(err), scenario }));
  process.exit(1);
});
