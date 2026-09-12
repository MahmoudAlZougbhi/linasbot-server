/**
 * Token memory is importable: no RN / SecureStore graph.
 */
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  __resetTokenMemoryForTests,
  isAccessHydrated,
  peekAccessToken,
  rememberAccessToken,
  rememberRefreshToken,
  wipeTokenMemory,
} from '../src/auth/tokenMemory.ts';

describe('in-memory access token', () => {
  it('hydrates once then returns memory without a store read', () => {
    __resetTokenMemoryForTests();
    assert.equal(isAccessHydrated(), false);
    rememberAccessToken('access-1');
    assert.equal(isAccessHydrated(), true);
    assert.equal(peekAccessToken(), 'access-1');
    rememberAccessToken('rotated');
    assert.equal(peekAccessToken(), 'rotated');
  });

  it('wipe clears tokens immediately for logout', () => {
    __resetTokenMemoryForTests();
    rememberAccessToken('access-1');
    rememberRefreshToken('refresh-1');
    wipeTokenMemory();
    assert.equal(peekAccessToken(), null);
    assert.equal(isAccessHydrated(), true);
  });

  it('hydrate-once means a second peek does not need a store', () => {
    __resetTokenMemoryForTests();
    rememberAccessToken('tok');
    const a = peekAccessToken();
    const b = peekAccessToken();
    assert.equal(a, 'tok');
    assert.equal(b, 'tok');
  });
});
