/**
 * Google Sign-In must not call expo-auth-session on iOS when iosClientId is missing.
 * Mirrors isGoogleAuthConfiguredForPlatform (no TS/RN loader).
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

function isGoogleAuthConfiguredForPlatform(ids, platform) {
  if (!ids.web) return false;
  if (platform === 'ios') return Boolean(ids.ios);
  if (platform === 'android') return Boolean(ids.android);
  return true;
}

const empty = { web: '', ios: '', android: '' };
const webOnly = { web: 'web.apps.googleusercontent.com', ios: '', android: '' };
const webIos = {
  web: 'web.apps.googleusercontent.com',
  ios: 'ios.apps.googleusercontent.com',
  android: '',
};
const allIds = {
  web: 'web.apps.googleusercontent.com',
  ios: 'ios.apps.googleusercontent.com',
  android: 'android.apps.googleusercontent.com',
};

describe('isGoogleAuthConfiguredForPlatform', () => {
  it('is false on iOS when ios client id is missing', () => {
    assert.equal(isGoogleAuthConfiguredForPlatform(empty, 'ios'), false);
    assert.equal(isGoogleAuthConfiguredForPlatform(webOnly, 'ios'), false);
  });

  it('is true on iOS only when web + ios client ids are set', () => {
    assert.equal(isGoogleAuthConfiguredForPlatform(webIos, 'ios'), true);
    assert.equal(isGoogleAuthConfiguredForPlatform(allIds, 'ios'), true);
  });

  it('is false on Android when android client id is missing', () => {
    assert.equal(isGoogleAuthConfiguredForPlatform(webOnly, 'android'), false);
    assert.equal(isGoogleAuthConfiguredForPlatform(webIos, 'android'), false);
    assert.equal(isGoogleAuthConfiguredForPlatform(allIds, 'android'), true);
  });

  it('uses web client id on web', () => {
    assert.equal(isGoogleAuthConfiguredForPlatform(empty, 'web'), false);
    assert.equal(isGoogleAuthConfiguredForPlatform(webOnly, 'web'), true);
  });
});

describe('SocialAuthButtons Google hook gating', () => {
  it('does not call useGoogleIdTokenAuthRequest from SocialAuthButtons itself', () => {
    const src = read('features/auth/SocialAuthButtons.tsx');
    const parentStart = src.indexOf('export function SocialAuthButtons');
    const parent = src.slice(parentStart);
    assert.ok(parentStart >= 0);
    assert.match(src, /function GoogleAuthButton/);
    assert.match(src, /googleEnabled \? \(/);
    assert.match(src, /<GoogleAuthButton /);
    assert.doesNotMatch(parent, /useGoogleIdTokenAuthRequest/);
    const child = src.slice(src.indexOf('function GoogleAuthButton'), parentStart);
    assert.match(child, /useGoogleIdTokenAuthRequest/);
  });

  it('keeps Apple Sign-In on iOS regardless of Google client ids', () => {
    const src = read('features/auth/SocialAuthButtons.tsx');
    assert.match(src, /signInWithApple/);
    assert.match(src, /appleEnabled = Platform\.OS === 'ios'/);
    assert.match(src, /socialContinueApple/);
  });

  it('login and register still mount social + email/password forms', () => {
    const login = read('features/auth/LoginScreen.tsx');
    const register = read('features/auth/RegisterScreen.tsx');
    assert.match(login, /SocialAuthButtons/);
    assert.match(login, /mobileLogin/);
    assert.match(register, /SocialAuthButtons/);
    assert.match(register, /password/);
  });
});

describe('googleSignIn source contracts', () => {
  it('requires platform client id before treating Google as configured', () => {
    const src = read('features/auth/googleSignIn.ts');
    assert.match(src, /export function isGoogleAuthConfiguredForPlatform/);
    assert.match(src, /platform === 'ios'/);
    assert.match(src, /platform === 'android'/);
    assert.match(src, /isGoogleAuthConfiguredForPlatform\(clientIds\(\), Platform\.OS\)/);
    assert.doesNotMatch(src, /fake.*iosClientId|dummy.*iosClientId/i);
  });
});
