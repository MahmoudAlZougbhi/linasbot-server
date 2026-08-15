/**
 * Persisted owner session must survive process death. Guest rotate / SecureStore
 * throw must not skip restore. Explicit logout still clears.
 *
 * Executable copies stay in lockstep with src/auth/restoreOwnerSession.ts
 * (no expo-secure-store in node --test).
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

async function restoreOwnerSession(store, options = {}) {
  const attempts = options.attempts ?? 4;
  const delayMs = options.delayMs ?? 120;
  const sleep = options.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  for (let i = 0; i < attempts; i++) {
    try {
      const access = await store.getAccessToken();
      return Boolean(access);
    } catch {
      if (i < attempts - 1) {
        await sleep(delayMs);
      }
    }
  }
  return false;
}

async function bootPersistedAuth(store, rotateGuest) {
  const hasAccess = await restoreOwnerSession(store);
  if (!hasAccess) {
    try {
      await rotateGuest();
    } catch {
      /* guest mint failed */
    }
    return false;
  }
  void rotateGuest().catch(() => {});
  return true;
}

function memoryStore(access = null) {
  let token = access;
  return {
    async getAccessToken() {
      return token;
    },
    async setTokens(next) {
      token = next;
    },
    async clear() {
      token = null;
    },
  };
}

describe('restoreOwnerSession', () => {
  it('restores a persisted token after a simulated process restart', async () => {
    const store = memoryStore(null);
    await store.setTokens('owner-access-token');
    const hasAccess = await restoreOwnerSession(store);
    assert.equal(hasAccess, true);
  });

  it('stays logged out when no token is stored', async () => {
    const store = memoryStore(null);
    const hasAccess = await restoreOwnerSession(store);
    assert.equal(hasAccess, false);
  });

  it('retries when the first SecureStore reads throw, then restores', async () => {
    let calls = 0;
    const store = {
      async getAccessToken() {
        calls += 1;
        if (calls < 3) {
          throw new Error('User interaction is not allowed');
        }
        return 'owner-access-token';
      },
    };
    const hasAccess = await restoreOwnerSession(store, { sleep: async () => {} });
    assert.equal(hasAccess, true);
    assert.equal(calls, 3);
  });

  it('does not wait when SecureStore returns null (explicit logged-out)', async () => {
    let calls = 0;
    const store = {
      async getAccessToken() {
        calls += 1;
        return null;
      },
    };
    const hasAccess = await restoreOwnerSession(store, { attempts: 4, sleep: async () => {} });
    assert.equal(hasAccess, false);
    assert.equal(calls, 1);
  });
});

describe('bootPersistedAuth', () => {
  it('keeps owner access when guest rotate throws', async () => {
    const store = memoryStore('owner-access-token');
    let rotated = false;
    const hasAccess = await bootPersistedAuth(store, async () => {
      rotated = true;
      throw new Error('guest rotate failed');
    });
    assert.equal(hasAccess, true);
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(rotated, true);
  });

  it('rotates guest when there is no owner token', async () => {
    const store = memoryStore(null);
    let rotated = false;
    const hasAccess = await bootPersistedAuth(store, async () => {
      rotated = true;
    });
    assert.equal(hasAccess, false);
    assert.equal(rotated, true);
  });

  it('explicit logout clears tokens so the next boot is guest', async () => {
    const store = memoryStore('owner-access-token');
    assert.equal(await restoreOwnerSession(store), true);
    await store.clear();
    assert.equal(await restoreOwnerSession(store), false);
  });
});

describe('session persist source contracts', () => {
  it('AppShell restores via bootPersistedAuth and does not await getUser first', () => {
    const shell = read('app/AppShell.tsx');
    assert.match(shell, /bootPersistedAuth\(tokenStore, rotateGuestSessionOnAppLaunch\)/);
    assert.match(shell, /setHasAccess\(has\)/);
    const bootEffect = shell.slice(shell.indexOf('void (async () => {'), shell.indexOf('onAuthCleared'));
    assert.doesNotMatch(bootEffect, /getUser\(\)/);
    assert.doesNotMatch(bootEffect, /await rotateGuestSessionOnAppLaunch/);
    assert.match(shell, /finally \{\s*setAuthReady\(true\);/);
  });

  it('TS restore module matches the executable boot order', () => {
    const boot = read('auth/restoreOwnerSession.ts');
    assert.match(boot, /export async function restoreOwnerSession/);
    assert.match(boot, /export async function bootPersistedAuth/);
    assert.match(boot, /return Boolean\(access\)/);
    const restoreAt = boot.indexOf('const hasAccess = await restoreOwnerSession(store)');
    const rotateAt = boot.indexOf('await rotateGuest()');
    assert.ok(restoreAt >= 0 && rotateAt > restoreAt, 'owner restore must run before guest rotate');
    assert.match(boot, /void rotateGuest\(\)\.catch/);
  });

  it('owner tokens use AFTER_FIRST_UNLOCK SecureStore options', () => {
    const opts = read('auth/secureStoreOptions.ts');
    const tokens = read('auth/tokenStore.ts');
    assert.match(opts, /AFTER_FIRST_UNLOCK/);
    assert.match(tokens, /SECURE_STORE_OPTIONS/);
    assert.match(tokens, /getItemAsync\(ACCESS_KEY, SECURE_STORE_OPTIONS\)/);
  });

  it('logout still clears the token store before dropping hasAccess', () => {
    const shell = read('app/AppShell.tsx');
    const logout = shell.slice(shell.indexOf('async function logout'));
    const clearAt = logout.indexOf('tokenStore.clear()');
    const accessAt = logout.indexOf('setHasAccess(false)');
    assert.ok(clearAt >= 0 && accessAt > clearAt);
  });

  it('cold start still opens a new owner chat without touching auth restore', () => {
    const session = read('features/chat/useChatSession.ts');
    assert.match(session, /createOwnerConversation/);
    assert.doesNotMatch(session, /preferFresh/);
    assert.doesNotMatch(session, /listed\.conversations\.find/);
  });
});
