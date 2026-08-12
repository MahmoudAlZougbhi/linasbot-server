/**
 * Apple account link / unlink / delete client surface.
 * Mirrors request shapes (no TS loader) + asserts source endpoints.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

/** Pure mirror of deleteAccount request body + success path used by tests. */
function buildDeleteBody(authorizationCode) {
  const body = {};
  const code = (authorizationCode || '').trim();
  if (code) body.authorization_code = code;
  return body;
}

async function deleteAccountMock({ authorizationCode, apiFetch, tokenStore }) {
  const body = buildDeleteBody(authorizationCode);
  await apiFetch('/api/auth/mobile/account/delete', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  await tokenStore.clear();
  return { ok: true };
}

async function linkAppleMock({ identityToken, nonce, authorizationCode, apiFetch }) {
  const body = { identity_token: identityToken, nonce };
  if (authorizationCode) body.authorization_code = authorizationCode;
  await apiFetch('/api/auth/mobile/apple/link', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return { ok: true };
}

async function unlinkAppleMock({ apiFetch }) {
  await apiFetch('/api/auth/mobile/apple/unlink', {
    method: 'POST',
    body: JSON.stringify({}),
  });
  return { ok: true };
}

describe('appleAccount API shapes', () => {
  it('calls link / unlink / delete endpoints with expected bodies', async () => {
    const calls = [];
    const apiFetch = async (path, opts) => {
      calls.push({ path, method: opts.method, body: JSON.parse(opts.body || '{}') });
      return { success: true };
    };
    const tokenStore = { cleared: false, async clear() { this.cleared = true; } };

    await linkAppleMock({
      identityToken: 'id-token',
      nonce: 'n1',
      authorizationCode: 'ac-1',
      apiFetch,
    });
    await unlinkAppleMock({ apiFetch });
    await deleteAccountMock({ authorizationCode: 'ac-del', apiFetch, tokenStore });

    assert.equal(calls[0].path, '/api/auth/mobile/apple/link');
    assert.equal(calls[0].body.authorization_code, 'ac-1');
    assert.equal(calls[0].body.identity_token, 'id-token');
    assert.equal(calls[1].path, '/api/auth/mobile/apple/unlink');
    assert.equal(calls[2].path, '/api/auth/mobile/account/delete');
    assert.equal(calls[2].body.authorization_code, 'ac-del');
    assert.equal(tokenStore.cleared, true);
  });

  it('omits authorization_code when absent', () => {
    assert.deepEqual(buildDeleteBody(null), {});
    assert.deepEqual(buildDeleteBody('  '), {});
    assert.deepEqual(buildDeleteBody('x'), { authorization_code: 'x' });
  });
});

describe('appleAccount + Settings source wiring', () => {
  it('exports linkApple / unlinkApple / deleteAccount against mobile endpoints', () => {
    const src = read('features/auth/appleAccount.ts');
    assert.match(src, /export async function linkApple/);
    assert.match(src, /export async function unlinkApple/);
    assert.match(src, /export async function deleteAccount/);
    assert.match(src, /\/api\/auth\/mobile\/apple\/link/);
    assert.match(src, /\/api\/auth\/mobile\/apple\/unlink/);
    assert.match(src, /\/api\/auth\/mobile\/account\/delete/);
    assert.match(src, /authorization_code/);
    assert.match(src, /tokenStore\.clear/);
  });

  it('Settings Account section wires link / unlink / delete with confirm', () => {
    const settings = read('features/settings/SettingsScreen.tsx');
    assert.match(settings, /linkApple|unlinkApple|deleteAccount/);
    assert.match(settings, /settingsLinkApple/);
    assert.match(settings, /settingsUnlinkApple/);
    assert.match(settings, /settingsDeleteAccount/);
    assert.match(settings, /Alert\.alert/);
    assert.match(settings, /onLogout/);
    assert.match(settings, /tokenStore|deleteAccount/);
  });

  it('sign-in sends authorization_code when Apple provides it', () => {
    const signIn = read('features/auth/appleSignIn.ts');
    assert.match(signIn, /authorizationCode/);
    assert.match(signIn, /authorization_code/);
  });
});
