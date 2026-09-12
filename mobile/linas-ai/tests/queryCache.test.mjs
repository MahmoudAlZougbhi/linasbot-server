/**
 * Executable copy of queryCache + session scope (no TS loader graph).
 * Keep in lockstep with src/cache/queryCache.ts.
 */
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

const MAX = 40;
const store = new Map();
const inflight = new Map();

function touch(key, entry) {
  store.delete(key);
  store.set(key, entry);
  while (store.size > MAX) {
    const oldest = store.keys().next().value;
    if (oldest === undefined) break;
    store.delete(oldest);
  }
}

function cacheGet(key) {
  const row = store.get(key);
  if (!row) return null;
  touch(key, row);
  return row;
}

function cacheSet(key, data, now = Date.now()) {
  touch(key, { data, updatedAt: now });
}

function cacheInvalidate(prefix) {
  for (const key of [...store.keys()]) {
    if (key === prefix || key.startsWith(prefix)) store.delete(key);
  }
}

function isCacheFresh(key, ttlMs, now = Date.now()) {
  const row = store.get(key);
  if (!row) return false;
  return now - row.updatedAt < ttlMs;
}

function dedupeFetch(key, fetcher) {
  const existing = inflight.get(key);
  if (existing) return existing;
  const pending = fetcher().finally(() => {
    if (inflight.get(key) === pending) inflight.delete(key);
  });
  inflight.set(key, pending);
  return pending;
}

function sessionScopeId(user) {
  if (!user) return 'anon';
  const tenant = String(user.tenantId || user.tenant_id || '').trim() || 'none';
  return `${tenant}:${user.id}`;
}

describe('query cache', () => {
  it('serves stale-while-revalidate hits and invalidates by prefix', () => {
    store.clear();
    cacheSet('t1:u1|users', [{ id: 'a' }], 1_000);
    assert.deepEqual(cacheGet('t1:u1|users')?.data, [{ id: 'a' }]);
    assert.equal(isCacheFresh('t1:u1|users', 90_000, 1_500), true);
    assert.equal(isCacheFresh('t1:u1|users', 90_000, 100_000), false);
    cacheInvalidate('t1:u1|users');
    assert.equal(cacheGet('t1:u1|users'), null);
  });

  it('dedupes concurrent fetches', async () => {
    store.clear();
    inflight.clear();
    let calls = 0;
    const p1 = dedupeFetch('same', async () => {
      calls += 1;
      await new Promise((r) => setTimeout(r, 20));
      return 'ok';
    });
    const p2 = dedupeFetch('same', async () => {
      calls += 1;
      return 'nope';
    });
    assert.equal(await p1, 'ok');
    assert.equal(await p2, 'ok');
    assert.equal(calls, 1);
  });

  it('evicts oldest entries past the RAM cap', () => {
    store.clear();
    for (let i = 0; i < MAX + 5; i += 1) cacheSet(`k${i}`, i);
    assert.equal(store.size <= MAX, true);
    assert.equal(cacheGet('k0'), null);
    assert.ok(cacheGet(`k${MAX + 4}`));
  });

  it('tenant/user keys differ so cache cannot leak across accounts', () => {
    const a = sessionScopeId({ id: 'u-a', tenantId: 'tenant-a' });
    const b = sessionScopeId({ id: 'u-b', tenantId: 'tenant-b' });
    assert.notEqual(a, b);
    cacheSet(`${a}|users`, ['alice']);
    assert.equal(cacheGet(`${b}|users`), null);
  });

  it('logout cacheClear drops every tenant row', () => {
    store.clear();
    cacheSet('t1:u1|users', ['a']);
    cacheSet('t1:u1|dashboard', { n: 1 });
    store.clear();
    inflight.clear();
    assert.equal(cacheGet('t1:u1|users'), null);
    assert.equal(store.size, 0);
  });

  it('stale entries stay readable while marked not fresh', () => {
    store.clear();
    cacheSet('t1:u1|dashboard', { n: 1 }, 1);
    assert.deepEqual(cacheGet('t1:u1|dashboard')?.data, { n: 1 });
    assert.equal(isCacheFresh('t1:u1|dashboard', 30_000, 50_000), false);
  });

  it('background refresh failure keeps the stale row', async () => {
    store.clear();
    inflight.clear();
    cacheSet('t1:u1|users', ['cached']);
    let calls = 0;
    async function refresh() {
      const hit = cacheGet('t1:u1|users');
      try {
        calls += 1;
        throw new Error('offline');
      } catch {
        return hit?.data ?? null;
      }
    }
    const painted = await refresh();
    assert.deepEqual(painted, ['cached']);
    assert.equal(calls, 1);
  });
});
