/**
 * Auth refresh + owner stream retry contracts (no device required).
 * Root cause: stream XHR used raw getAccessToken and never refreshed on 401
 * after DASHBOARD_SESSION_TTL (~12h), then rotate-on-use refresh races wiped sessions.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (...p) => join(root, 'src', ...p);

function read(rel) {
  return readFileSync(src(...rel.split('/')), 'utf8');
}

/** Mirrors single-flight behavior of accessToken.refreshAccessToken. */
function createSingleFlightRefresh(refreshImpl) {
  let inFlight = null;
  return function refreshAccessToken() {
    if (inFlight) return inFlight;
    inFlight = Promise.resolve()
      .then(() => refreshImpl())
      .finally(() => {
        inFlight = null;
      });
    return inFlight;
  };
}

describe('single-flight refresh', () => {
  it('shares one in-flight refresh across parallel callers', async () => {
    let calls = 0;
    const refresh = createSingleFlightRefresh(async () => {
      calls += 1;
      await new Promise((r) => setTimeout(r, 20));
      return `token-${calls}`;
    });
    const [a, b, c] = await Promise.all([refresh(), refresh(), refresh()]);
    assert.equal(calls, 1);
    assert.equal(a, 'token-1');
    assert.equal(b, 'token-1');
    assert.equal(c, 'token-1');
  });

  it('allows a second refresh after the first settles', async () => {
    let calls = 0;
    const refresh = createSingleFlightRefresh(async () => {
      calls += 1;
      return `token-${calls}`;
    });
    assert.equal(await refresh(), 'token-1');
    assert.equal(await refresh(), 'token-2');
    assert.equal(calls, 2);
  });
});

describe('owner stream auth contracts', () => {
  it('useOwnerStream uses ensureAccessToken and refreshes once on 401', () => {
    const stream = read('features/chat/v2/useOwnerStream.ts');
    assert.match(stream, /ensureAccessToken/);
    assert.match(stream, /refreshAccessToken/);
    assert.doesNotMatch(stream, /tokenStore\.getAccessToken/);
    assert.match(stream, /auth_error/);
    assert.match(stream, /xhr\.status === 401/);
    assert.match(stream, /apiUpload/);
  });

  it('accessToken module exports single-flight refresh + auth-cleared notify', () => {
    const access = read('api/accessToken.ts');
    assert.match(access, /refreshInFlight/);
    assert.match(access, /onAuthCleared/);
    assert.match(access, /notifyAuthCleared/);
    assert.match(access, /\/api\/auth\/mobile\/refresh/);
  });

  it('ChatScreen tap-to-retry does not bootstrap on messageFailed', () => {
    const chat = read('features/chat/ChatScreen.tsx');
    assert.match(chat, /if \(err === 'messageFailed'\) return;/);
    assert.match(chat, /Message failed|messageFailed/);
  });

  it('App drops hasAccess when refresh clears tokens', () => {
    const shell = readFileSync(join(root, 'src/app/AppShell.tsx'), 'utf8');
    assert.match(shell, /onAuthCleared/);
    assert.match(shell, /setHasAccess\(false\)/);
  });

  it('i18n still exposes retry + messageFailed copy users see', () => {
    const en = read('i18n/locales/en.ts');
    assert.match(en, /Message failed\. You can retry\./);
    assert.match(en, /Could not load chat\. Tap Retry\./);
    assert.match(en, /tapToRetry:\s*'Tap to retry'/);
    const banners = read('features/chat/ChatStatusBanners.tsx');
    assert.match(banners, /tr\('tapToRetry'\)/);
  });
});
