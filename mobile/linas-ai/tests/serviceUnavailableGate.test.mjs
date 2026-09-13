/**
 * Deploy drain / 502 must not look like a missing subscription.
 * Run: node --import ./tests/resolveTsSibling.mjs --experimental-strip-types --test tests/serviceUnavailableGate.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import { isTransientServiceError } from '../src/api/transientError.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (rel) => readFileSync(join(root, 'src', rel), 'utf8');

test('502/503/timeout and network errors are service unavailable, not billing denial', () => {
  assert.equal(isTransientServiceError({ status: 502 }), true);
  assert.equal(isTransientServiceError({ status: 503 }), true);
  assert.equal(isTransientServiceError({ status: 504 }), true);
  assert.equal(isTransientServiceError({ status: 500 }), true);
  assert.equal(isTransientServiceError({ status: 408 }), true);
  assert.equal(isTransientServiceError(new TypeError('Network request failed')), true);
  assert.equal(isTransientServiceError(new SyntaxError('Unexpected token <')), true);
});

test('401/402/403 stay fail-closed as billing/auth, not maintenance', () => {
  assert.equal(isTransientServiceError({ status: 401 }), false);
  assert.equal(isTransientServiceError({ status: 402 }), false);
  assert.equal(isTransientServiceError({ status: 403 }), false);
});

test('subscription gate treats transient errors as unavailable and does not deny entitlement', () => {
  const src = read('features/billing/useSubscriptionGate.ts');
  assert.match(src, /isTransientServiceError/);
  assert.match(src, /setUnavailable\(true\)/);
  assert.match(src, /UNAVAILABLE_RETRY_MS = 30_000/);
  assert.match(src, /!unavailable && access !== null && !access\.allowed/);
  assert.doesNotMatch(src, /catch \{\s*if \(gen !== requestGen/);
});

test('app shell prefers maintenance screen over subscribe wall', () => {
  const shell = read('app/AppShell.tsx');
  const tree = read('app/AppScreenTree.tsx');
  assert.match(shell, /showServiceUnavailable/);
  assert.match(shell, /!subGate\.unavailable/);
  assert.match(tree, /ServiceUnavailableScreen/);
  assert.match(tree, /showServiceUnavailable/);
});

test('maintenance copy asks to retry in about 5 minutes', () => {
  const en = readFileSync(join(root, 'src/i18n/locales/subscriptionEn.ts'), 'utf8');
  const screen = read('features/billing/ServiceUnavailableScreen.tsx');
  assert.match(en, /serviceUnavailableTitle:\s*'We’re updating the service'/);
  assert.match(en, /Please try again in about 5 minutes/);
  assert.match(screen, /tr\('serviceUnavailableTitle'\)/);
  assert.match(screen, /tr\('serviceUnavailableRetry'\)/);
  assert.doesNotMatch(screen, /subscribeGateViewPlans/);
  assert.doesNotMatch(en, /STAGING|BOC Staging/i);
});
