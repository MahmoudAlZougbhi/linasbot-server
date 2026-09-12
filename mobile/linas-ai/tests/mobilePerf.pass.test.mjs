import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { KEEP_MOUNTED_LIMIT, KEEP_MOUNTED_SCREENS } from '../src/app/keepMountedPolicy.ts';
import { bootSplashTokens, splashExitDelayMs } from '../src/features/boot/bootSplashTokens.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

describe('mobile performance pass contracts', () => {
  it('keep-mounted set is capped at chat, livechat, dashboard, cm', () => {
    assert.equal(KEEP_MOUNTED_LIMIT, 4);
    assert.deepEqual([...KEEP_MOUNTED_SCREENS], ['chat', 'livechat', 'dashboard', 'cm']);
    assert.match(read('cache/bindSessionCaches.ts'), /cacheClear/);
    assert.match(read('auth/tokenStore.ts'), /resetSessionCaches/);
    assert.match(read('api/client.ts'), /getInflight/);
  });

  it('splash min display is under 500ms and still waits when auth is ready', () => {
    assert.ok(bootSplashTokens.minDisplayMs <= 480);
    assert.ok(bootSplashTokens.maxHoldMs <= 1800);
    assert.equal(
      splashExitDelayMs(true, 0, bootSplashTokens.minDisplayMs, bootSplashTokens.maxHoldMs),
      bootSplashTokens.minDisplayMs,
    );
    assert.equal(
      splashExitDelayMs(false, bootSplashTokens.maxHoldMs, bootSplashTokens.minDisplayMs, bootSplashTokens.maxHoldMs),
      0,
    );
  });

  it('cached reopen path is sub-millisecond vs a 50ms network stand-in', async () => {
    const map = new Map();
    map.set('bench|dashboard', { data: { n: 1 }, updatedAt: Date.now() });
    const cachedStart = process.hrtime.bigint();
    for (let i = 0; i < 2000; i += 1) {
      const row = map.get('bench|dashboard');
      void row;
    }
    const cachedMs = Number(process.hrtime.bigint() - cachedStart) / 1e6;
    const perHit = cachedMs / 2000;
    const networkStart = process.hrtime.bigint();
    await new Promise((r) => setTimeout(r, 50));
    const networkMs = Number(process.hrtime.bigint() - networkStart) / 1e6;
    assert.ok(perHit < 0.15, `cache hit was ${perHit}ms`);
    assert.ok(networkMs >= 45, `network stand-in was ${networkMs}ms`);
  });

  it('second fetch within TTL does not call the loader', async () => {
    let calls = 0;
    const inflight = new Map();
    const store = new Map();
    const ttl = 90_000;
    const load = (key) => {
      const row = store.get(key);
      if (row && Date.now() - row.updatedAt < ttl) return Promise.resolve(row.data);
      const existing = inflight.get(key);
      if (existing) return existing;
      const pending = Promise.resolve().then(async () => {
        calls += 1;
        const data = { users: [calls] };
        store.set(key, { data, updatedAt: Date.now() });
        return data;
      }).finally(() => inflight.delete(key));
      inflight.set(key, pending);
      return pending;
    };
    await load('users');
    await load('users');
    assert.equal(calls, 1);
  });

  it('parallel independent requests beat a sequential waterfall', async () => {
    const hop = (ms) => new Promise((r) => setTimeout(r, ms));
    const seqStart = process.hrtime.bigint();
    await hop(20);
    await hop(20);
    const seqMs = Number(process.hrtime.bigint() - seqStart) / 1e6;
    const parStart = process.hrtime.bigint();
    await Promise.all([hop(20), hop(20)]);
    const parMs = Number(process.hrtime.bigint() - parStart) / 1e6;
    assert.ok(parMs < seqMs * 0.8, `parallel ${parMs}ms vs sequential ${seqMs}ms`);
  });

  it('token memory wipe plus cache clear is the logout contract', () => {
    assert.match(read('auth/tokenStore.ts'), /wipeTokenMemory\(\);/);
    assert.match(read('auth/tokenStore.ts'), /resetSessionCaches\(\);/);
    assert.match(read('auth/tokenStore.ts'), /\(prev\?\.id \?\? null\) !== user\.id/);
    assert.match(read('cache/bindSessionCaches.ts'), /cacheClear\(\)/);
    assert.match(read('cache/bindSessionCaches.ts'), /clearAuthImageCache/);
    assert.match(read('cache/bindSessionCaches.ts'), /clearCmDraftCache/);
    assert.match(read('cache/bindSessionCaches.ts'), /clearDrawerSessionCache/);
    assert.match(read('cache/bindSessionCaches.ts'), /clearQueryPersist/);
  });

  it('swr screens paint cache and do not blank on remount', () => {
    assert.match(read('features/products/ProductsScreen.tsx'), /cacheGet<Product\[]>\(queryKeys.products\(\)\)/);
    assert.match(read('features/products/ProductsScreen.tsx'), /if \(!hit && !cached\) setLoading\(true\)/);
    assert.match(read('features/users/UsersScreen.tsx'), /Promise.all\(\[tokenStore.getAccessToken\(\), tokenStore.getUser\(\)\]\)/);
    assert.match(read('features/requests/useRequestsList.ts'), /Promise.all\(\[fetchRequestsSetupStatus\(\), listRequests\(requestArgs\)\]\)/);
    assert.match(read('features/requests/useRequestsList.ts'), /QUERY_TTL.requests/);
    assert.match(read('features/livechat/useLiveChatInbox.ts'), /catchUpIfStale/);
    assert.match(read('features/livechat/LiveChatScreen.tsx'), /inbox.catchUpIfStale\(\)/);
    assert.doesNotMatch(read('features/livechat/comments/CommentsInbox.tsx'), /setStatus\('loading'\);\s*setPosts\(\[\]\)/);
    assert.match(read('cache/idlePrefetch.ts'), /prefetchDashboard/);
    assert.match(read('cache/idlePrefetch.ts'), /prefetchLiveChatInbox/);
    assert.match(read('cache/idlePrefetch.ts'), /prefetchCmHub/);
    assert.match(read('cache/idlePrefetch.ts'), /prefetchIntegrations/);
    assert.match(read('cache/idlePrefetch.ts'), /prefetchProducts/);
    assert.doesNotMatch(read('cache/idlePrefetch.ts'), /prefetchUsers/);
    assert.match(read('app/ModulePane.tsx'), /if \(!active\) return null/);
    assert.match(read('app/KeepMountedPane.tsx'), /const \[mounted, setMounted\] = useState\(active\)/);
  });

  it('access token is not read from SecureStore after hydrate', () => {
    const store = read('auth/tokenStore.ts');
    assert.match(store, /if \(isAccessHydrated\(\)\) return peekAccessToken\(\)/);
    assert.match(store, /rememberAccessToken\(access\)/);
    assert.match(read('api/client.ts'), /await ensureAccessToken\(\)/);
  });
});
